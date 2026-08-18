# TP1 Distribuidos

## Requisitos previos

- Docker y Docker Compose instalados
- Python 3 con entorno virtual (para correr el cliente localmente)
- Dataset: carpeta `datasets/` con los archivos CSV de transacciones y cuentas

## Configuración inicial

```bash
make venv
make install
```

## Generar el docker-compose

El `docker-compose.yml` se genera a partir de los archivos de configuración en `config/queries/`. Hay 5 queries disponibles (1 a 5). Indicá cuáles querés incluir:

```bash
make generar 1 2 5      # genera solo las queries 1, 2 y 5
make generar 1 2 3 4 5  # genera todas las queries
```

Esto configura automáticamente el Gateway y los workers correspondientes.

## Levantar el lado del servidor (Docker)

Una vez generado el compose:

```bash
make start            # levanta RabbitMQ, Gateway y workers en segundo plano (detached)
make start --verbose  # levanta mostrando los logs en consola
```

Para detener:

```bash
make down
```

## Levantar el lado del cliente

### Opción A — clientes en contenedores Docker

```bash
make run-clients            # lanza 2 clientes (por defecto)
make run-clients SCALE=N    # lanza N clientes en paralelo
```

Cada cliente escribe sus resultados en `output/<hostname>/`.

### Opción B — cliente local (sin Docker)

Útil para desarrollo o debug. Requiere levantar el gateway localmente primero.

**Terminal 1 — Gateway:**
```bash
make gateway
```

**Terminal 2+ — Clientes:**
```bash
make client OUTPUT_DIR=output/c1
make client OUTPUT_DIR=output/c2   # cada cliente en su propia terminal
```

#### Variables configurables del cliente

| Variable           | Default       | Descripción                         |
|--------------------|---------------|-------------------------------------|
| `TRANSACTIONS_FILE`| —             | Path al CSV de transacciones        |
| `ACCOUNTS_FILE`    | —             | Path al CSV de cuentas              |
| `OUTPUT_DIR`       | `output`      | Carpeta donde se guardan resultados |
| `SERVER_HOST`      | `127.0.0.1`   | Host del Gateway                    |
| `SERVER_PORT`      | `5678`        | Puerto del Gateway                  |
| `BATCH_SIZE`       | `10000`       | Tamaño del batch de envío           |

Ejemplo con parámetros posicionales (con los mismos atajos sin carpeta ni extensión):
```bash
make client HI-Large_Trans_sample_30 HI-Large_accounts OUTPUT_DIR=output/prueba
```

## Validación de Soluciones

Para validar el correcto funcionamiento de las queries contra datasets de prueba, se disponen de comandos para generar soluciones locales y contrastar iterativamente los resultados.

### Generar solución de referencia (Notebook)
Ejecuta la lógica de pandas de referencia para crear los archivos CSV de soluciones esperadas.
```bash
make solucionar <dataset> <dir>
```
* **`<dataset>`**: Nombre del archivo del dataset en la carpeta `datasets/` (no requiere indicar el directorio ni la extensión `.csv`).
* **`<dir>`**: Carpeta de destino de soluciones bajo `solutions/` (no requiere escribir el prefijo `solutions/`). Si ya existe la carpeta de destino, se borra por completo y se vuelve a crear.

*Ejemplo:*
```bash
make solucionar HI-Large_Trans_sample_30 Hi-Large-30
```

### Iterar y comparar resultados del cliente
Ejecuta el cliente iterativamente y contrasta sus resultados CSV con las soluciones de referencia de forma automatizada.
```bash
make iterar [iteraciones] [transacciones] [cuentas] [soluciones]
```
* **`[iteraciones]`**: Número de iteraciones a ejecutar (opcional, default `1`).
* **`[transacciones]`**: Nombre del dataset de transacciones (opcional, busca en `datasets/` por defecto).
* **`[cuentas]`**: Nombre del dataset de cuentas (opcional, busca en `datasets/` por defecto).
* **`[soluciones]`**: Nombre de la carpeta de soluciones esperadas bajo `solutions/` (opcional, default `Hi-Large-30`).

*Ejemplo:*
```bash
make iterar 5 HI-Large_Trans_sample_30 HI-Large_accounts Hi-Large-30
```

## Tolerancia a Fallos y Pruebas de Caos

El sistema cuenta con un mecanismo de tolerancia a fallos autocurativo y herramientas para simular caídas:

### Componentes del Sistema (Objetos)
* **Gateway**: Punto de entrada que recibe las transacciones y cuentas del cliente, distribuye batches a la cola de entrada de RabbitMQ, consolida los resultados de las queries en archivos temporales por cliente y realiza deduplicación de lotes duplicados mediante hash MD5.
* **Workers**: Nodos de procesamiento del pipeline (filtros, conversores de monedas, proyecciones, agregadores y acumuladores) configurados de forma dinámica y con logs detallados de inicialización.
* **Coordinador Distribuido**: Gestiona las barreras de sincronización EOF a nivel de etapa a través de colas de control dedicadas, garantizando una finalización ordenada incluso ante caídas de workers.
* **Watchdog**: Monitorea de forma centralizada la llegada de heartbeats de cada worker y reporta fallos al actuador ante la pérdida reiterada de señales.
* **Actuador**: Escucha reportes del watchdog e interactúa con el daemon de Docker (`docker.sock`) para reiniciar automáticamente las réplicas caídas.

### Simulación de Caos (Chaos Monkey)
Para validar la tolerancia a fallos, se dispone de un script Chaos Monkey que apaga de forma aleatoria contenedores de workers durante el procesamiento.

#### Pruebas en dos terminales independientes (Recomendado)
Para probar tolerancia a fallos de forma independiente en dos terminales mientras los clientes corren de manera secuencial:

**Terminal 1 (Clientes Secuenciales):**
```bash
make test-secuencial [cant_clientes] # Por defecto 5
```

**Terminal 2 (Chaos Monkey):**
```bash
make tirar-nodos                   # Caos continuo aleatorio cada 10s
make tirar-nodos [segundos]        # Caos continuo aleatorio con intervalo personalizado
make tirar-nodos [seg] todos       # Loop continuo: mata todos los workers activos cada [seg] segundos
make tirar-nodos [seg] etapa       # Loop continuo: mata una etapa al azar cada [seg] segundos
make tirar-nodos [seg] etapa <p>   # Loop continuo: mata la etapa <p> específica cada [seg] segundos
```

#### Pruebas integradas
Para ejecutar la simulación de caos continuo (Chaos Monkey) y clientes automatizados de manera conjunta:
```bash
make caos [min] [max] [cant_clientes] [--todos] [--etapa <pref>]
```
* **`[min]`** y **`[max]`**: Intervalo de tiempo al azar en segundos antes de apagar contenedores (opcional, default `10` y `20`).
* **`[cant_clientes]`**: Cantidad de clientes a lanzar en paralelo para someter a estrés (opcional, default `3`).
* **`--todos`**: Detiene de forma masiva e inmediata todos los workers de procesamiento.
* **`--etapa <prefijo>`**: Detiene inmediatamente todos los nodos activos que pertenezcan a la etapa indicada (ej. `q4_sumador`).

*Ejemplo:*
```bash
make caos 5 15 4              # 4 clientes, con Chaos Monkey cada 5 a 15 segundos
make caos 5 5 2 --todos       # 2 clientes, espera 5 segundos y mata todos los workers activos
make caos 2 8 3 --etapa counter # 3 clientes, tiempo al azar de 2-8s y mata etapa counter
```

## Suite de Tests Automatizados

Todos los tests end-to-end comparten tres variables de dataset que se definen una sola vez en el Makefile:

| Variable   | Default             | Descripción                                    |
|------------|---------------------|------------------------------------------------|
| `TEST_TX`  | `trans_sample`      | Archivo de transacciones (en `datasets/`)      |
| `TEST_ACC` | `LI-Small_accounts` | Archivo de cuentas (en `datasets/`)            |
| `TEST_SOL` | `sample`            | Carpeta de soluciones esperadas (en `solutions/`) |

Para cambiar el dataset de toda la suite basta con sobreescribir las variables:
```bash
make test-todos TEST_TX=LI-Small_Trans TEST_ACC=LI-Small_accounts TEST_SOL=LI-Small
```

### 1. Suite Completa (Test Todos)
```bash
make test-todos
```
Ejecuta secuencialmente las 15 etapas de validación del sistema. Se detiene al primer error.

| # | Test | Descripción |
|---|------|-------------|
| 1 | `test-unitarios` | Tests unitarios y de persistencia en Python |
| 2 | `test-crash-caso6` | Crash post-flush / pre-confirmación |
| 3 | `test-crash-caso7` | Crash pre-disparo de barrera |
| 4 | `test-crash-leader` | Caída del watchdog líder mid-election |
| 5 | `test-crash-flush` | Crash post-flush / pre-barrera_completada (caso 8) |
| 6 | `test-caos-todos` | Mata todos los workers simultáneamente |
| 7 | `test-caos-aleatorio` | Chaos monkey aleatorio (5-15s) |
| 8 | `test-caos-etapa` | Caída de etapa `q2_agregador_shard` |
| 9 | `test-caos-etapa` | Caída de etapa `q4_sumador` |
| 10 | `test-caos-etapa` | Caída de etapa `q3_format_shard` |
| 11 | `test-caos-cliente` | Cliente cae a mitad de envío |
| 12 | `test-caos-gateway` | Gateway cae en caliente |
| 13 | `test-caos-gateway-resultados` | Gateway cae mientras el cliente recibe resultados |
| 14 | `test-stress-crash` | Stress de casos de frontera (2 iteraciones) |
| 15 | `test-stress-caos` | Stress de caídas masivas (2 iteraciones) |

### 2. Tests Unitarios y de Persistencia
```bash
make test-unitarios
```

### 3. Tests de Caos en Docker
* **`make test-caos-todos [cant_cli] [tx] [acc] [sol]`**: Mata todos los workers simultáneamente durante el procesamiento.
* **`make test-caos-aleatorio [min] [max] [cant_cli]`**: Aplica fallas aleatorias continuas usando Chaos Monkey mientras los clientes transmiten datos.
* **`make test-caos-etapa <pref> [cant_cli] [tx] [acc] [sol]`**: Corta una etapa de procesamiento entera.
* **`make test-caos-cliente [cant_cli] [tx] [acc] [sol]`**: Simula la caída de un cliente a mitad de envío.
* **`make test-caos-gateway [cant_cli] [tx] [acc] [sol]`**: Simula la caída en caliente del Gateway.
* **`make test-caos-gateway-resultados [tx] [acc] [sol]`**: Simula la caída del Gateway mientras el cliente recibe resultados.

### 4. Tests de Casos de Frontera (Inyección de Falla por Estado)
* **`make test-crash-flush [etapa] [tx] [acc] [sol]`**: Valida el Caso 8 (crash tras flush de datos a disco, pre-barrera_completada).
* **`make test-crash-caso6 [cant_cli] [tx] [acc] [sol]`**: Valida el Caso 6 (falla pre-confirmación del fin de dataset al cliente).
* **`make test-crash-caso7 [cant_cli] [tx] [acc] [sol]`**: Valida el Caso 7 (falla pre-disparo de la barrera).
* **`make test-crash-leader [cant_cli] [tx] [acc] [sol]`**: Valida tolerancia a caída del watchdog líder de elección.

### 5. Tests de Stress (Bucles)
* **`make test-stress-caos [iter] [cant_cli] [tx] [acc] [sol]`**: Itera en bucle el test de caídas masivas para detectar condiciones de carrera.
* **`make test-stress-crash [iter] [cant_cli] [tx] [acc] [sol]`**: Itera en bucle los casos de frontera (caso6, caso7 y leader).

Todos los parámetros de dataset son opcionales — si no se pasan, usan `TEST_TX`/`TEST_ACC`/`TEST_SOL` del entorno o los defaults del Makefile.

## Limpiar todo

```bash
make clean
```

Detiene los contenedores, libera los puertos 5678, 5672 y 15672, y elimina caches y archivos temporales.

## Comandos útiles

```bash
make log gateway          # logs del gateway en tiempo real
make log filter_usd_01    # logs de un worker específico
make help                 # lista todos los targets disponibles con descripciones
```
