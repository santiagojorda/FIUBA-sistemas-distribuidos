# Flashcards nuevas — Integradores Resueltos (RESUELTOS.pdf)

> Extraídas de los 8 exámenes integradores resueltos en `INTEGRADORES/RESUELTOS.pdf` (2022-2025).
> Se filtraron todas las preguntas cuyo contenido YA está cubierto por las flashcards existentes en esta carpeta
> (por ejemplo: Multithreading vs Multiprocessing, Chandy-Lamport, Paxos, CAP, Replicación Activa/Pasiva, Cristian,
> NTP, DFS/HDFS, RPC, Work-Span, Pipeline-Filters, Atomicidad de mensajes, protocolos binario/texto, etc.).
> Acá quedan solo las preguntas con respuesta completa en el PDF que **no** tenían equivalente en el resto del mazo.
>
> Formato: pregunta primero, respuesta debajo. Tapá las respuestas y probate.

---

## Clase 02: Multitasking y Comunicaciones

**1. Implementando un protocolo de health-check de servidor a clientes mediante sockets, ¿qué condiciones deberían cumplirse para que sea más conveniente utilizar UDP frente a TCP?**

<details>
<summary>Respuesta</summary>

- Se necesita una lógica de reintentos cada cierto tiempo, en caso de no recibir una respuesta, para asegurar que los mensajes llegan efectivamente.
- Alcanza con esperar una respuesta del cliente que indique que está vivo (no se necesita transferir grandes volúmenes de datos ni garantizar orden).
- No es necesario mantener una conexión abierta estable entre cliente y servidor.

*(Fuente: Integrador 20240716, Ej. 1)*
</details>

---

**2. Utilizando blocking-queues, ¿cómo implementarías una barrera para que 3 procesos "workers" se sincronicen en cierto punto de un algoritmo?**

<details>
<summary>Respuesta</summary>

1. Se crea una blocking queue con capacidad igual al número total de procesos (3 en este caso).
2. Cuando un proceso llega al punto de sincronización, inserta un token en la cola (`put()`) y luego intenta remover un elemento (`take()`). Si la capacidad máxima de la queue aún no fue alcanzada (hay procesos que todavía no insertaron su token), el proceso queda bloqueado al hacer `take()`.
3. Cuando el último proceso llega al punto de sincronización e inserta su token, se alcanza la capacidad máxima de la queue. Esto desbloquea a todos los procesos que estaban esperando en `take()`, y el algoritmo avanza.

*(Fuente: Integrador 20240716, Ej. 8 — variante de "barrera" implementada concretamente con blocking queues, distinta del enfoque conceptual con Condition Variables ya cubierto en Clase 02)*
</details>

---

## Clase 05: Mensajes, Grupos, Middlewares y MOMs

**3. ¿Qué estrategias puede implementar un MOM para garantizar tolerancia a fallos?**

<details>
<summary>Respuesta</summary>

- ACK de mensajes para asegurar su entrega.
- Replicación de colas.
- Durabilidad de colas: en lugar de que los mensajes solo existan en memoria, se bajan a disco ante posibles caídas.

Ejemplo: RabbitMQ para la comunicación entre workers en un sistema distribuido.

*(Fuente: Integrador 20220802, Ej. 3)*
</details>

---

**4. Asumiendo un equipo de hasta 10 agentes de atención al cliente en una empresa telefónica, ¿cómo implementarías un middleware distribuido que permita a los agentes llamar al siguiente número en fila? ¿Dónde almacenarías la información del último número llamado?**

<details>
<summary>Respuesta</summary>

El middleware recibe requests vía sockets. Internamente tiene un load balancer que distribuye los pedidos entre las 10 colas asociadas a cada agente del sistema, con el objetivo de que ninguna cola se sature y el trabajo se distribuya de forma uniforme. El último número llamado podría guardarse en el propio middleware, para llevar un registro de la cantidad de requests recibidas/procesadas.

*(Fuente: Integradores 20240716 y 20241219, Ej. 4)*
</details>

---

## Clase 07: Patrones de Comunicación

**5. Utilizando una arquitectura Publisher-Subscriber, ¿cómo calcularías la suma de todos los enteros de un vector de tamaño N, optimizando el uso de P procesos disponibles?**

<details>
<summary>Respuesta</summary>

El Publisher lee números del arreglo compartido y los publica a una cola. Cada Consumer (hasta P) consume de a 2 elementos de la cola, los suma, y agrega el resultado parcial de vuelta al arreglo compartido. El Publisher repite el ciclo mientras haya más de un número en el arreglo; cuando queda un único número, ese es el resultado total y se devuelve.

Ejemplo con `[1,2,3,4,5,6,7,8]`:
- Ronda 1: se publican pares `(1,2)→3`, `(3,4)→7`, `(5,6)→11`, `(7,8)→15` → arreglo `[3,7,11,15]`.
- Ronda 2: `(3,7)→10`... hasta reducir a un único valor con la suma total, que el Publisher lee y devuelve.

*(Fuente: Integrador 20220802, Ej. 8 — diagrama de secuencia/actividades con Publisher leyendo y Consumers sumando de a pares)*
</details>

---

## Clase 09: Arquitecturas Distribuidas Simples

**6. Con pseudocódigo, ¿cómo extraerías $31000 de una cuenta bancaria (CA-1234) y los acreditarías en otra (CA-S673), asumiendo la existencia de una plataforma de Distributed Objects? ¿Cómo sería el gráfico de la arquitectura?**

<details>
<summary>Respuesta</summary>

```go
srv = getBankService()
account1 = srv.getAccount(CA-1234)

extracted, err = account1.Extract(31000)
if (err != nil) {
  throw("No hay suficiente dinero en la cuenta de origen")
}

account2 = srv.getAccount(CA-S673)

success = account2.SendMoney(extracted)
if (!success) {
  account1.SendMoney(extracted)
  throw("No se pudo realizar el depósito en la cuenta de destino")
}
```

Arquitectura: un Cliente local invoca `getAccount(string)`, `account.Extract(int)` y `account.SendMoney(Money)` sobre objetos remotos `Account` y `Money`, expuestos por un Dispatcher dentro del servidor remoto (patrón típico de Distributed Objects ya visto para RMI/CORBA, aplicado acá a un caso concreto de transferencia bancaria con rollback ante fallo del depósito).

*(Fuente: Integrador 20230725, Ej. 8)*
</details>

---

## Clase 10: Distribución y Coordinación de Procesos

**7. Utilizando map-reduce para distribuir la carga, ¿cómo procesarías eventos de log de una aplicación Web (tuplas `email, url_navegada, fecha`) para calcular (a) la cantidad de navegaciones detectadas por día de semana y (b) el listado de emails con más de 10 navegaciones registradas?**

<details>
<summary>Respuesta</summary>

```
# a) Navegaciones por día de la semana
def map(list values):
    # value -> (email, url_navegada, fecha)
    for v in values:
        day = getDay(v.fecha)   # MON, TUE, WED, THU, FRI, SAT, SUN
        emitIntermediate(day, 1)

def reduce(string key, list values):
    # key -> día de la semana ; values -> lista de 1s
    emit(key, len(values))

# b) Emails con más de 10 navegaciones
def map(list values):
    for v in values:
        emitIntermediate(v.email, 1)

def reduce(string key, list values):
    # key -> email
    if len(values) >= 10:
        emit(key, len(values))
```

*(Fuente: Integrador 20230725, Ej. 9 — ejemplo concreto de Map-Reduce distinto del Word Count ya cubierto en Clase 10)*
</details>

---

## Clase 11: Sistemas Elásticos y de Alta Disponibilidad

**8. ¿Qué es el throttling o descarte de paquetes? ¿Tiene efectos negativos?**

<details>
<summary>Respuesta</summary>

Ante una sobrecarga del sistema o de requests, el sistema recurre a disminuir la cantidad de requests procesadas o mensajes entregados, o bien a descartar paquetes, con el objetivo de liberar o disminuir el flujo de datos sobre el canal de comunicación.

Efectos negativos posibles:
- La información podría perderse (por ejemplo, si se utiliza un protocolo UDP "crudo").
- Los emisores tienen la responsabilidad de controlar no solo que el mensaje sea recibido, sino que sea enviado efectivamente, debiendo implementar una política de reintento ante la falta de respuesta.

*(Fuente: Integrador 20250213, Ej. 1)*
</details>

---

**9. ¿Cómo se calculan los "9s" de disponibilidad de un sistema con 2 nodos de frontend idénticos (accedidos por los usuarios) que se comunican con 2 nodos de backend idénticos, asumiendo P(availability) = 0,95 para cada nodo y que el balanceo de carga es transparente (los load balancers no se caen)?**

<details>
<summary>Respuesta</summary>

Primero se calcula la disponibilidad de un cluster de nodos redundantes (cualquiera sea, FE o BE, ya que son idénticos):

```
P(availability) = 1 - P(failure)
                = 1 - P(failure 1 & failure 2)
                = 1 - (0.05 * 0.05)
                = 1 - 0.0025
                = 0.9975   → disponibilidad de un cluster (FE o BE)
```

Como frontend y backend son clusters independientes y están encadenados (el usuario necesita a ambos), la disponibilidad del sistema es el producto de ambos clusters:

```
P(system availability) = P(frontend av.) * P(backend av.)
                        = 0.9975 * 0.9975 = 0.99500625 ≈ 0.9950
```

La disponibilidad del sistema es del 99,5%. (Combina en un mismo cálculo el caso de réplicas en paralelo dentro de cada tier con el caso de tiers encadenados entre sí.)

*(Fuente: Integrador 20250220, Ej. 4)*
</details>

---

## Clase 13: Data Intensive Applications

**10. Ejemplificá el uso de Direct Acyclic Graphs (DAGs) al diseñar el procesamiento de datos de todas las ventas diarias de una cadena de tiendas de ropa. Cada venta posee ID de tienda y un arreglo con: monto unitario, cantidad y código de producto (`venta = {id_tienda: [monto_unitario, cantidad, id_producto]}`). Se pretende obtener los 10 códigos de producto más vendidos, el monto promedio de venta y la cantidad de ventas con más de 3 productos.**

<details>
<summary>Respuesta</summary>

El nodo raíz `VENTAS` se ramifica en tres queries independientes que pueden calcularse en paralelo, ya que no tienen dependencias entre sí:

- **Q1 — 10 productos más vendidos**: `SELECT SUM(cantidad) FROM ventas GROUP BY id_producto` → Ordenar DESC → TOP 10.
- **Q2 — monto promedio de venta**: `SELECT SUM(monto_unitario * cantidad) / COUNT(*) FROM ventas`.
- **Q3 — ventas con más de 3 productos**: `for venta in ventas: if len(venta) > 3 then print(venta)`.

Las tres ramas confluyen finalmente en un nodo "Retornar Resultados". Al modelarlo como DAG, el trabajo se paraleliza naturalmente entre las tres queries, evidenciando la ventaja de representar el dataflow como grafo acíclico en vez de un pipeline puramente secuencial.

*(Fuente: Integrador 20220809, Ej. 9 — ejemplo aplicado de DAG distinto al conceptual ya cubierto en Clase 07)*
</details>

---

## Clase 15: Diseño de Arquitecturas de Gran Escala

**11. Diseñá una arquitectura escalable para un sistema que debe: (a) recibir usuario, timestamp y cambios de canal realizados en Argentina y Brasil por usuarios con Smart TV de la marca LG que aceptaron términos y condiciones que incluyen monitoreo de uso; (b) consultar la cantidad de usuarios sintonizando cierto canal; (c) consultar los 5 canales más visualizados (por minutos) en un rango de días; (d) consultar la cantidad de usuarios con más de 1 visualización por día.**

<details>
<summary>Respuesta</summary>

Endpoints:

```
POST /channel_change
  body: { userId: string (UUID), timestamp: datetime, channel: int,
          country: int, TVbrand: string, terms: bool }

GET /users?channel=...
  body: { total: int }

GET /topChannels?from=...&to=...
  body: { topChannels: string[] }

GET /frequentUsers
  body: { total: int }
```

Vista física: el `POST /channel_change` filtra por país, marca y términos/condiciones aceptados, y persiste los datos filtrados en un Storage Controller. A partir de esos datos filtrados se calculan de forma asíncrona/paralela dos resultados parciales — "cantidad de usuarios por canal" y "top 5 canales más visualizados" — cada uno con su propio almacenamiento de resultados parciales, que responde a los GETs correspondientes. La consulta de usuarios con más de 1 visualización/día se calcula sobre los mismos datos filtrados.

*(Fuente: Integrador 20220802, Ej. 10 — ejercicio de diseño NALSD no presente entre los ya cubiertos en Clase 15)*
</details>

---

## Clase 17: Tolerancia a Fallos

**12. ¿Cómo se clasifica la Redundancia como estrategia de tolerancia a fallos, y qué la diferencia de un ejemplo donde NO garantiza tolerancia a fallos?**

<details>
<summary>Respuesta</summary>

La redundancia puede ser:
- **Física** → hardware, disco rígido de backup.
- **De información** → réplica de datos, backup de información.
- **De tiempo** → lógica de reintentos.

Ejemplo donde SÍ garantiza tolerancia a fallos: 2 nodos replicados con un load balancer que distribuye requests y, ante la caída de uno, redirige las requests al otro disponible (replicación pasiva).

Ejemplo donde NO la garantiza: dos discos físicos donde uno debería servir de respaldo del otro; si el segundo disco no estaba siendo espejado correctamente y el primero se rompe de forma inesperada, se pierde toda la información — la redundancia existía en el papel, pero no era efectiva en la práctica.

*(Fuente: Integrador 20250213, Ej. 6 — clasificación física/información/tiempo no explícita en las flashcards de Clase 17)*
</details>

---

**13. Dentro de la Resiliencia de un sistema confiable (*dependable*), ¿qué es el Graceful Degradation?**

<details>
<summary>Respuesta</summary>

Es el comportamiento aceptable que un sistema mantiene en presencia de fallos, aun siendo distinto del comportamiento normal ("está mal, pero no está tan mal"). Es la forma concreta en que se materializa la propiedad de Resiliencia: en vez de una falla total, el sistema se mantiene en un estado degradado pero utilizable.

*(Fuente: Integrador 20230725, Ej. 6 — término no mencionado explícitamente en las flashcards de Clase 17, que listan las propiedades de dependability pero no "graceful degradation" como concepto aparte)*
</details>

---

## Clase 20: Tiempo, Relojes, Sincronismo, Orden y Cortes de Estado

**14. Dado un diagrama de tiempo con eventos entre tres procesos (P0, P1, P2) y mensajes cruzados entre ellos, ¿cómo se calculan los vectores de reloj y cómo se determina la relación entre dos eventos usando únicamente esos vectores?**

<details>
<summary>Respuesta</summary>

Cada componente del vector se actualiza como:
- Evento interno: `local += 1`.
- Recepción de un mensaje: `P_j = max(e_j, msg_j)` componente a componente.

Para determinar la relación entre dos eventos B y G usando únicamente sus vectores:

```
B → G  ⟺  C(B) < C(G)
```

Es decir, todas las componentes de `C(B)` deben ser ≤ a las de `C(G)`, y al menos una estrictamente menor. Por ejemplo, si `C(B) = (0,1,1)` y `C(G) = (2,2,1)`, entonces `C(B) < C(G)` componente a componente (con al menos un `<` estricto), por lo que `B → G`.

Si ninguno de los dos vectores domina completamente al otro (ej. `C(D) = (0,1,2)` vs `C(G) = (2,2,1)`: la primera componente de D es menor pero la tercera es mayor), los eventos son **concurrentes**, no puede establecerse una relación causal entre ellos.

*(Fuente: Integrador 20220802, Ej. 9 — ejemplo numérico aplicado del método ya descripto conceptualmente en Clase 20)*
</details>

---
