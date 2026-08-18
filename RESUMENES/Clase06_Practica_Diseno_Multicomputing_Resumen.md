# Sistemas Distribuidos I (75.74) — Clase 06: Práctica de Diseño Multicomputing

Esta clase consiste en dos ejercicios prácticos de diseño de sistemas distribuidos (multicomputing), donde se debe diseñar la arquitectura (procesos, comunicación, sincronización) para cumplir los requerimientos funcionales y no funcionales dados.

## Parte 1: Web Crawler

### Requerimientos Funcionales

- Dada una URL, obtener el HTML y analizarlo.
- Detectar nuevas URLs e identificar archivos multimedia, documentos y otras páginas Web.
- Descargar los archivos multimedia (`.jpg`, `.png`, `.mp3`, `.ogg`, etc.).
- Descargar los documentos (`.pdf`, `.odt`, etc.).
- Agendar el procesamiento de las nuevas páginas Web encontradas.
- Detener el análisis de nuevos links luego de **N anidaciones**.

### Requerimientos No Funcionales

- Las descargas y el análisis se deben ejecutar **en paralelo**.
- Realizar un **monitoreo constante** en un archivo de texto con cantidades de:
  - URLs analizadas.
  - Archivos descargados por extensión.
  - Procesos en cada uno de los siguientes estados:
    - Obteniendo HTML.
    - Procesando HTML.
    - Descargando recurso.

**Puntos clave de diseño a considerar:**
- El problema tiene una naturaleza recursiva/arbórea (cada página descubre nuevas URLs), por lo que conviene pensar en un patrón tipo *fork-join* o *productor-consumidor* con una cola de URLs pendientes, limitando la profundidad con un contador de anidación (N).
- Se necesita paralelismo entre el **análisis de HTML** (CPU-bound: parsear y extraer links) y la **descarga de recursos** (I/O-bound: red), lo cual sugiere desacoplar ambos en distintos tipos de workers/procesos.
- El monitoreo constante en un archivo de texto implica algún mecanismo de sincronización para actualizar contadores compartidos (ej. semáforos/mutex o un proceso dedicado que centralice las métricas) sin frenar el pipeline de procesamiento.

## Parte 2: Shopping Cart

### Requerimientos Funcionales

- Realizar un sistema que acepte **pedidos de compra** por productos.
- Los pedidos cuentan con **usuario, tipo de producto y cantidad**.
- El sistema debe mantener el **stock** por tipo de producto.
- Además de los pedidos de compra, el sistema debe aceptar:
  - **Modificaciones de stock** (administradores).
  - **Consultas del estado de los pedidos** (compradores).
  - **Notificación de la entrega** al comprador (empleados).
- Se debe controlar el **estado de cada pedido**, pudiendo ser: **Recibido, Aceptado, Rechazado, Entregado**.

### Requerimientos No Funcionales

- El catálogo de productos es **reducido** (10 aprox.) pero se espera un **gran volumen de pedidos**.
- Todo pedido de compra debe ser almacenado como una **entrada de Log ordenada** con fines de auditoría.
- Los pedidos pueden contener unidades de distintos tipos. Los pedidos son **aceptados o rechazados en su totalidad** (atomicidad del pedido completo).
- La aplicación debe estar preparada para una **gran cantidad de usuarios concurrentes**.
- El **monitoreo de los flujos de información** es clave para garantizar la performance del sistema.

**Puntos clave de diseño a considerar:**
- Bajo número de productos pero alta concurrencia de pedidos sugiere que el **stock por producto** es el principal punto de contención: conviene pensar en mecanismos de sincronización finos (ej. un lock o actor por producto, en vez de un lock global) para no serializar todo el sistema.
- La **atomicidad del pedido** (acepta o rechaza todas las unidades pedidas) requiere validar y reservar stock de todos los ítems del pedido como una operación conjunta (similar a una transacción), evitando condiciones de carrera entre pedidos concurrentes que compiten por el mismo stock.
- El requerimiento de **Log ordenado** para auditoría implica que las escrituras de eventos de pedidos deben mantener un orden consistente, aún con múltiples procesos/threads escribiendo de forma concurrente (posible candidato para un proceso centralizado de logging o una cola FIFO).
- Los tres roles (compradores, administradores, empleados) interactúan con el mismo estado compartido (stock y pedidos) desde distintas operaciones (compra, modificación de stock, consulta, notificación de entrega), por lo que conviene diseñar interfaces/colas separadas por tipo de operación que confluyan en el mismo núcleo de sincronización del stock y los pedidos.
