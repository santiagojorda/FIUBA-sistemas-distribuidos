# Flashcards — Clase 06: Práctica de Diseño Multicomputing

> Formato: pregunta primero, respuesta debajo. Tapá las respuestas y probate.

---

**1. En el ejercicio del Web Crawler, ¿cuáles son los requerimientos funcionales principales?**

<details>
<summary>Respuesta</summary>

Dada una URL, obtener el HTML y analizarlo; detectar nuevas URLs e identificar archivos multimedia, documentos y otras páginas Web; descargar los archivos multimedia (.jpg, .png, .mp3, .ogg, etc.) y documentos (.pdf, .odt, etc.); agendar el procesamiento de las nuevas páginas encontradas; y detener el análisis de nuevos links luego de N anidaciones.
</details>

---

**2. ¿Cuáles son los requerimientos no funcionales del Web Crawler?**

<details>
<summary>Respuesta</summary>

Las descargas y el análisis se deben ejecutar en paralelo, y se debe realizar un monitoreo constante en un archivo de texto con: cantidad de URLs analizadas, archivos descargados por extensión, y procesos en cada estado (Obteniendo HTML, Procesando HTML, Descargando recurso).
</details>

---

**3. ¿Qué patrón de diseño conviene para modelar la naturaleza recursiva/arbórea del Web Crawler?**

<details>
<summary>Respuesta</summary>

Un patrón tipo fork-join o productor-consumidor con una cola de URLs pendientes, limitando la profundidad con un contador de anidación (N), ya que cada página descubierta genera nuevas URLs a procesar.
</details>

---

**4. ¿Por qué conviene desacoplar el análisis de HTML de la descarga de recursos en distintos tipos de workers?**

<details>
<summary>Respuesta</summary>

Porque tienen naturaleza distinta: el análisis de HTML es CPU-bound (parsear y extraer links) mientras que la descarga de recursos es I/O-bound (red), por lo que conviene paralelizarlos con workers especializados para cada tarea.
</details>

---

**5. ¿Qué mecanismo se necesita para el monitoreo constante del Web Crawler sin frenar el pipeline?**

<details>
<summary>Respuesta</summary>

Algún mecanismo de sincronización para actualizar contadores compartidos, ya sea semáforos/mutex sobre el archivo de métricas o un proceso dedicado que centralice las métricas, evitando frenar el pipeline de procesamiento.
</details>

---

**6. En el ejercicio del Shopping Cart, ¿cuáles son los requerimientos funcionales principales?**

<details>
<summary>Respuesta</summary>

Aceptar pedidos de compra (con usuario, tipo de producto y cantidad), mantener el stock por tipo de producto, aceptar modificaciones de stock (administradores), consultas del estado de pedidos (compradores) y notificación de entrega (empleados). Controlar el estado de cada pedido: Recibido, Aceptado, Rechazado, Entregado.
</details>

---

**7. ¿Cuáles son los requerimientos no funcionales del Shopping Cart?**

<details>
<summary>Respuesta</summary>

Catálogo de productos reducido (10 aprox.) pero gran volumen de pedidos; todo pedido debe almacenarse como entrada de Log ordenada para auditoría; los pedidos son aceptados o rechazados en su totalidad (atomicidad); la aplicación debe soportar gran cantidad de usuarios concurrentes; y el monitoreo de los flujos de información es clave para la performance.
</details>

---

**8. En el Shopping Cart, ¿por qué el stock por producto es el principal punto de contención y qué se sugiere para resolverlo?**

<details>
<summary>Respuesta</summary>

Porque hay pocos productos (bajo número) pero alta concurrencia de pedidos compitiendo por ellos. Conviene usar mecanismos de sincronización finos, como un lock o actor por producto, en vez de un lock global, para no serializar todo el sistema.
</details>

---

**9. ¿Qué implica la atomicidad del pedido en el Shopping Cart y qué riesgo evita?**

<details>
<summary>Respuesta</summary>

Implica validar y reservar el stock de todos los ítems del pedido como una operación conjunta (similar a una transacción), aceptando o rechazando el pedido en su totalidad. Esto evita condiciones de carrera entre pedidos concurrentes que compiten por el mismo stock.
</details>

---

**10. ¿Qué implica el requerimiento de Log ordenado para auditoría en el Shopping Cart?**

<details>
<summary>Respuesta</summary>

Que las escrituras de eventos de pedidos deben mantener un orden consistente aún con múltiples procesos/threads escribiendo de forma concurrente, siendo candidato un proceso centralizado de logging o una cola FIFO.
</details>

---

**11. Los tres roles del Shopping Cart (compradores, administradores, empleados) interactúan con el mismo estado compartido. ¿Cómo conviene diseñar las interfaces de entrada?**

<details>
<summary>Respuesta</summary>

Conviene diseñar interfaces/colas separadas por tipo de operación (compra, modificación de stock, consulta, notificación de entrega) que confluyan en el mismo núcleo de sincronización del stock y los pedidos.
</details>

---
