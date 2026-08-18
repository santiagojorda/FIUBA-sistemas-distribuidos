# Informe de Implementación entrega Escalabilidad — TP1 Distribuidos
## Sistema de Análisis de Transacciones Bancarias

---

## Introducción

El objetivo del trabajo práctico es desarrollar un sistema distribuido que procese un dataset de transacciones bancarias y responda cinco consultas analíticas en paralelo. El sistema fue diseñado como un **pipeline de procesamiento distribuido basado en mensajes**, donde los datos ingresan por un gateway TCP, fluyen a través de workers especializados conectados por colas RabbitMQ, y los resultados son devueltos al cliente original.

El sistema soporta múltiples clientes concurrentes, cada uno identificado por un `client_id` único que viaja en todos los mensajes. Todos los workers son procesos sin estado compartido entre sí; la sincronización se realiza exclusivamente mediante mensajes de control.

---

## Arquitectura General

```
  Cliente (TCP)
      │
      ▼
  Gateway (TCP + RabbitMQ)
      │
      ▼
  RabbitMQ ──── Workers Q1 ──── q1_results ──┐
      │    ├─── Workers Q2 ──── q2_results ──┤
      │    ├─── Workers Q3 ──── q3_results ──┼──▶ Gateway ──▶ Cliente
      │    ├─── Workers Q4 ──── q4_results ──┤
      │    └─── Workers Q5 ──── q5_results ──┘
```

Los componentes principales son:

| Componente | Descripción |
|---|---|
| **Cliente** | Envía el dataset por TCP al Gateway en batches y espera los resultados |
| **Gateway** | Acepta conexiones TCP, publica los datos en RabbitMQ y reenvía resultados al cliente |
| **Workers** | Procesan los mensajes según su tipo (filtrar, proyectar, agregar, unir) |
| **RabbitMQ** | Middleware de mensajería; desacopla productores de consumidores |

---

## Gateway

El Gateway es el único punto de entrada TCP al sistema. Sus responsabilidades son:

- Aceptar múltiples conexiones de clientes (un hilo por cliente).
- Asignar un `client_id` único a cada sesión.
- Deserializar los batches del protocolo externo (TCP) y publicarlos en las colas de entrada de RabbitMQ.
- Escuchar las colas de resultados (`q1_results`, …, `q5_results`) y reenviar cada resultado al cliente correspondiente vía TCP.
- Emitir mensajes `CLIENT_DISCONNECT` al pipeline cuando un cliente se desconecta, para que cada worker limpie el estado de ese cliente sin emitir resultados.

El Gateway no realiza ningún procesamiento analítico: es un traductor entre el protocolo TCP externo y el protocolo interno de mensajes RabbitMQ.

### Protocolo externo (TCP)

El cliente envía bloques de longitud prefijada (`4 bytes big-endian + payload`). El payload es binario compacto: los registros se codifican como listas de valores con tipos indicados por un byte de tipo por campo (entero, float, string). Los EOFs se marcan con un frame especial.

---

##  Modelo de Workers

### Jerarquía de clases

Todos los workers heredan de `BaseWorker` y sobreescriben los métodos que correspondan:

```
BaseWorker (abstracto)
├── procesar_payload()    ← lógica de negocio
├── al_completar_cliente()← flush de estado acumulado
├── al_cerrar()           ← limpieza de recursos
└── interceptar_eof()     ← override para manejo no estándar de EOF
```

`BaseWorker` orquesta dos componentes internos:

- **`MessageRouter`**: gestiona colas de entrada/salida y aplica las reglas de sharding y routing.
- **`DistributedCoordinator`**: implementa la barrera de sincronización distribuida entre réplicas del mismo tipo.

### Tipos de workers

| Tipo | Query | Función |
|---|---|---|
| `filter` | Q1, Q2, Q3, Q4 | Filtra registros por campo con operadores (`eq`, `lt`, `gt`, `between`, `in`) |
| `projection` | Q1–Q5 | Selecciona columnas y convierte tipos de datos |
| `bank_shard` | Q2 | Join transacciones + datos bancarios; agrega máximo por banco |
| `format_shard` | Q3 | Procesamiento en dos fases: calcula promedio del período temprano y filtra el período tardío |
| `group_distinct_counter` | Q4 | Agrupa y cuenta valores distintos con filtro de umbral mínimo |
| `joiner_q4` | Q4 | Join de tres vías A→B→C con filtro de degeneración |
| `converter` | Q5 | Convierte divisas vía API externa (`frankfurter.app`), filtra por monto |
| `counter` | Q5 | Conteo global final |

---

## Formato de Mensajes Interno

Los workers se comunican mediante batches JSON publicados en colas RabbitMQ:

```json
{
  "client_id": "abc123",
  "batches": [
    {
      "header": {
        "schema": ["From Bank", "Account", "Amount Paid"],
        "client_id": "abc123",
        "count": 2500
      },
      "payload": [
        [1001, 10001, 150.50],
        ...
      ]
    }
  ]
}
```

Los mensajes de control especiales son:

| Mensaje | Campo | Semántica |
|---|---|---|
| EOF | `"EOF": true` | Fin de datos para un cliente |
| Desconexión | `"CLIENT_DISCONNECT": true` | El cliente se desconectó; limpiar estado sin emitir resultados |

---

## Distribución de Mensajes (MessageRouter)

El `MessageRouter` implementa tres estrategias de ruteo configurables por JSON:

### Ruteo directo

El mensaje se envía sin modificación a todas las colas de salida directas. Los EOFs también se propagan por esta vía.

### Ruteo con sharding

Los registros del batch se particionan por hash MD5 de uno o más campos clave:

```
shard_id = (int(md5(campo_1 | campo_2 | …), 16) % total_shards) + 1
```

Cada shard recibe únicamente los registros que le corresponden. Los valores numéricos se normalizan (eliminando ceros a la izquierda) para garantizar que `"00394"` y `"394"` caigan en el mismo shard. Los EOFs se propagan a **todos** los shards.

### Ruteo condicional

Los registros se enrutan a colas distintas según el valor de un campo (por ejemplo, por rango de fecha). Dentro de cada caso condicional, se aplica sharding por otro campo. Los EOFs se propagadan a todas las colas de todos los casos.

---

## Coordinación Distribuida (DistributedCoordinator)

El problema central de coordinación es: dado un grupo de N réplicas del mismo worker, ¿cuándo puede cada réplica hacer flush de su estado acumulado y emitir sus resultados hacia downstream?

El flush sólo puede hacerse cuando:
1. Todos los datos de un cliente ya fueron procesados por esa réplica.
2. No hay mensajes downstream pendientes de confirmación (ACK).

### Protocolo de barrera en tres fases

Cada tipo de worker usa un exchange fanout de RabbitMQ (`control_<prefijo>_exchange`) exclusivo para sus réplicas:

**Fase 1 — EOF local**

Cada réplica trackea cuántas de sus colas de entrada enviaron EOF para un dado `client_id`. Cuando todas enviaron EOF, la réplica está lista para participar en la barrera.

**Fase 2 — Elección de originador**

La primera réplica en completar su EOF local se anuncia como originador difundiendo por el exchange de control:

```json
{ "type": "EOF_RECEIVED", "client_id": "X", "originator": "worker_id" }
```

Si dos réplicas se anuncian simultáneamente (condición de carrera), **gana la de menor `worker_id`**. La réplica que cede se encarga de limpiar su estado de originador.

**Fase 3 — Flush y finalización**

Cada réplica, cuando está lista para hacer flush (EOF local completado y originador conocido):
1. Espera a que el contador de mensajes en vuelo llegue a cero.
2. Ejecuta el flush de su estado local (`al_completar_cliente()`).
3. Emite `WORKER_FINISHED` al exchange de control.

El originador espera `WORKER_FINISHED` de las N réplicas. Al recibirlos todos, emite:

```json
{ "type": "BARRIER_COMPLETE", "client_id": "X" }
```

Todas las réplicas propagan el EOF hacia downstream y limpian su estado. El originador es además responsable del reenvío del mensaje EOF original.

### Tracking de mensajes en vuelo

Para evitar hacer flush mientras aún hay mensajes downstream procesándose, el coordinador mantiene un contador `_mensajes_en_vuelo` por `client_id`. Cada mensaje de datos incrementa el contador al ser recibido; el ACK del consumidor lo decrementa. El flush sólo procede cuando ese contador llega a cero.

### Casos especiales de EOF

- **Workers con múltiples entradas** (Q2, Q3, Q4): esperan EOF de todas sus colas de entrada antes de iniciar la barrera.
- **`FormatShard` (Q3)**: sobreescribe `interceptar_eof()` para gestionar manualmente las dos fases (período temprano / tardío). Evita hacer flush del promedio antes de que el período tardío haya sido procesado.
- **`JoinerQ4` (Q4)**: recibe dos streams con semánticas distintas (aristas scatter y transacciones crudas), cada uno con su propio tracking de EOF.
- **`CLIENT_DISCONNECT`**: propaga el mensaje downstream y limpia el estado del cliente sin emitir resultados parciales.

---

## Pipelines por Query

### Q1 — Transacciones pequeñas en USD

**Objetivo:** Transacciones en dólares con monto < $50.

```
raw_data
  └→ shared_filter_usd (3 réplicas) — filtra Payment Currency = "US Dollar"
      └→ q1_projection (2 réplicas) — selecciona From Bank, Account, To Bank, Account, Amount Paid
          └→ q1_minor_than_50 (3 réplicas) — filtra Amount Paid < 50
              └→ q1_results
```

Pipeline lineal sin sharding. El filtro compartido upstream (`shared_filter_usd`) también alimenta Q2, Q3 y Q4, evitando duplicar el trabajo de filtrado por moneda.

---

### Q2 — Monto máximo por banco en USD

**Objetivo:** Para cada banco, el monto máximo de las transacciones recibidas en dólares.

```
raw_data → shared_filter_usd (3 réplicas)
             └→ q2_projection (6 réplicas, shard por "From Bank")
                 └→ q2_shard_transactions_1..6

datos_bancarios (del cliente)
  └→ q2_bank_projection (3 réplicas, shard por "Bank ID")
      └→ q2_shard_banks_1..6

q2_shard_transactions_{id} + q2_shard_banks_{id}
  └→ q2_agregador_shard (6 réplicas) — join + max por banco
      └→ q2_results
```

**Diseño clave:** Dos flujos de datos independientes (transacciones y datos bancarios) se shardean por la misma clave (`Bank`). Esto garantiza que el agregador de cada shard reciba toda la información necesaria para hacer el join localmente, sin comunicación cruzada entre shards. La barrera distribuida coordina el flush de los 6 agregadores antes de emitir resultados.

---

### Q3 — Transacciones tardías menores al 1% del promedio temprano

**Objetivo:** Del 1 al 14 de septiembre de 2022, transacciones del período tardío (6-14/9) cuyo monto es menor al 1% del promedio del período temprano (1-5/9), agrupado por Payment Format.

```
raw_data → shared_filter_usd
  └→ q3_filter_fechas (4 réplicas)
      ├→ q3_temprano_1..2 (shard por "Payment Format") — período 1-5/9
      └→ q3_tardio_1..2   (shard por "Payment Format") — período 6-14/9

q3_temprano_{id} + q3_tardio_{id}
  └→ q3_format_shard (2 réplicas) — procesamiento en dos fases
      └→ q3_results
```

**Diseño clave:** Routing condicional por rango de fecha seguido de sharding por Payment Format. Cada `format_shard` acumula el período temprano para calcular el promedio por formato; cuando recibe el EOF de esa fase, comienza a filtrar el período tardío contra esos promedios. La coordinación de los dos EOFs se maneja manualmente en `interceptar_eof()`.

---

### Q4 — Caminos A→B→C con alta dispersión

**Objetivo:** Encontrar pares `(A, C)` tal que exista algún B con A→B (A transfiere a ≥5 B distintos) y B→C. Se reportan los `(A, C)` con más de 5 intermediarios B distintos.

```
raw_data → shared_filter_usd → q4_projection → q4_filter_period (1-5/9)
  ├→ q4_to_sumador_1..3 (shard por From Bank + Account)
  └→ q4_to_joiner_1..3  (mismo shard key)

q4_to_sumador_{id}
  └→ q4_sumador (3 réplicas) — cuenta destinos distintos por origen
      si |{B}| ≥ 5 → emite aristas A→B válidas
      └→ q4_scatter_edges_1..3 (shard por to_bank + to_account)

q4_scatter_edges_{id} + q4_to_joiner_{id}
  └→ q4_joiner (3 réplicas) — join A→B con B→C
      filtra degeneración (A≠B, B≠C, A≠C)
      └→ q4_paths_1..3 (shard por A + C)

q4_paths_{id}
  └→ q4_contador (3 réplicas) — cuenta B's distintos por par (A, C)
      filtra donde count > 5
      └→ q4_results
```

**Diseño clave (scatter-gather):** Cada transacción se envía simultáneamente al `sumador` (stream A, para detectar alta dispersión) y al `joiner` (stream B, para ser encontrado como destino B→C). El sharding por `(From Bank, Account)` garantiza que todas las aristas del mismo origen van al mismo sumador. Las aristas validadas se reshardean por `(to_bank, to_account)` para que el joiner pueda hacer el join con B→C localmente. El joiner maneja dos semánticas de EOF distintas.

---

### Q5 — Transacciones Wire/ACH menores a $1 USD

**Objetivo:** Conteo de transacciones en formato Wire o ACH del 1-5/9 cuyo monto, convertido a USD, es menor a $1.

```
raw_data
  └→ q5_projection (4 réplicas) — selecciona Timestamp, Currency, Format, Amount
      └→ q5_filter_period (4 réplicas) — filtra 1-5/9
          └→ q5_filter_format (2 réplicas) — filtra Format in {Wire, ACH}
              └→ q5_converter (2 réplicas) — convierte a USD vía API, filtra < $1
                  └→ q5_counter (1 réplica) — conteo global
                      └→ q5_results
```

**Diseño clave:** Pipeline lineal con reducción progresiva del volumen de datos. Se usan 2 workers de conversión en paralelo para tolerar la latencia de la API externa. El counter final es único para garantizar un conteo global consistente sin necesidad de barrera distribuida.

---

## Infraestructura y Despliegue

### Generación dinámica del docker-compose

La topología de cada query se describe en archivos JSON en `config/queries/`. El script `generar_compose.py` los lee y genera el `docker-compose.yml` completo, instanciando cada servicio con sus variables de entorno (colas de entrada, colas de salida, ID de nodo, total de réplicas).

```bash
make generar 1 2 3 4 5  # genera el compose para todas las queries
make start              # levanta RabbitMQ, Gateway y todos los workers
make run-clients        # lanza los clientes en contenedores
```

### Prefetch de RabbitMQ

Para evitar que un worker acumule demasiados mensajes en memoria cuando los batches son grandes, se configura `prefetch_count = 150`. Esto limita cuántos mensajes puede tener un worker pendientes de ACK en un momento dado.

### Escalabilidad

El número de réplicas de cada tipo de worker se configura en los JSON de topología. Agregar réplicas no requiere modificar el código; sólo se ajusta el parámetro `total_workers` y se regenera el compose. La barrera distribuida del coordinador se adapta automáticamente al nuevo total.

---

## Patrones de Diseño Utilizados

| Patrón | Queries | Descripción |
|---|---|---|
| Pipeline lineal | Q1, Q5 | Workers en serie sin sharding cruzado |
| Sharding por clave | Q2, Q4 | Hash de campo garantiza que datos relacionados van al mismo shard |
| Routing condicional | Q3 | Registros enrutados a colas distintas según valor de un campo |
| Barrera distribuida | Q2, Q3, Q4 | Workers se sincronizan vía canal de control fanout antes de hacer flush |
| Scatter-Gather | Q4 | Mismo dato enviado a dos streams; reunificado posteriormente por join shard |
| Join inter-stream | Q2, Q4 | Dos fuentes de datos que convergen por sharding en la misma clave |
| Procesamiento en dos fases | Q3 | Primer stream calcula estadísticas; segundo stream las consume para filtrar |
| Filtro compartido upstream | Q1, Q2, Q3, Q4 | Un único conjunto de workers de filtrado alimenta múltiples queries |
