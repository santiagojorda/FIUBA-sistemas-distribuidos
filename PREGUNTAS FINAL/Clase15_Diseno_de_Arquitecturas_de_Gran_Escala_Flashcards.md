# Flashcards — Clase 15: Diseño de Arquitecturas de Gran Escala

> Formato: pregunta primero, respuesta debajo. Tapá las respuestas y probate.

---

**1. ¿Qué es la metodología NALSD (Non-Abstract Large-Scale System Design) y quién la propone?**

<details>
<summary>Respuesta</summary>

Es una metodología propuesta por Google SRE para diseñar la arquitectura concreta (no abstracta) de sistemas a gran escala. Dado un enunciado de requerimientos, el diseño debe ser tangible: especificar componentes reales, estimar volúmenes de datos/tráfico, elegir tecnologías concretas (bases de datos, colas, balanceadores, etc.) y justificar decisiones de particionamiento, replicación, caching y escalabilidad, en lugar de quedarse en diagramas genéricos tipo "Cliente → Servidor → Base de Datos".
</details>

---

**2. En el ejercicio de Traffic Lights Violations Detector, ¿por qué conviene pensar en una ventana de tiempo (time window) para generar una infracción?**

<details>
<summary>Respuesta</summary>

Porque el sistema combina dos flujos de eventos que deben correlacionarse en el tiempo: el estado del semáforo (verde/amarillo/rojo) y la captura de imágenes de patentes. Una infracción solo debe generarse cuando una patente es detectada cruzando durante el rojo, por lo que se necesita vincular ambos eventos por semáforo/cámara dentro de una ventana temporal.
</details>

---

**3. ¿Por qué el ejercicio de Traffic Lights Violations Detector es un buen caso de uso para un pipeline de streaming en lugar de procesamiento batch?**

<details>
<summary>Respuesta</summary>

Porque hay muchos semáforos distribuidos geográficamente generando eventos de forma continua, lo cual es similar a los patrones de Pipelines, Pub-Sub y MOM vistos en clases anteriores, y requiere procesar los eventos a medida que ocurren en lugar de esperar a acumular lotes.
</details>

---

**4. En el diseño del detector de infracciones, ¿por qué conviene desacoplar el procesamiento de imágenes (reconocimiento de patente) del resto del flujo?**

<details>
<summary>Respuesta</summary>

Porque es la etapa más costosa computacionalmente del pipeline; desacoplarla (por ejemplo, como una etapa paralela) evita que bloquee la ingestión de eventos de los semáforos, permitiendo que el resto del sistema siga recibiendo y procesando eventos sin esperar a que termine el reconocimiento de cada imagen.
</details>

---

**5. ¿Qué patrón de notificación se sugiere para enviar las infracciones generadas, y por qué?**

<details>
<summary>Respuesta</summary>

Un patrón de notificación tipo Publisher-Subscriber o el envío a colas separadas por destinatario, ya que las infracciones requieren persistencia duradera (para inspección y administración posterior) y deben notificarse a dos destinos distintos: el propietario del vehículo y el ente regulador.
</details>

---

**6. En el ejercicio de Shared Code Snippets, ¿qué característica de los datos favorece fuertemente el uso de caching y réplicas de solo lectura?**

<details>
<summary>Respuesta</summary>

Es un sistema de lectura intensiva (alta disponibilidad y gran cantidad de accesos) con datos relativamente pequeños e inmutables una vez creados: el snippet no cambia una vez compartido, solo se lee, lo cual favorece fuertemente caching y réplicas read-only.
</details>

---

**7. ¿Qué tipo de almacenamiento conviene usar para los snippets de código y por qué?**

<details>
<summary>Respuesta</summary>

Almacenamiento tipo blob storage / objeto, en lugar de una base de datos relacional tradicional, dado que se requiere guardar por tiempo indefinido un gran volumen de bloques de código pequeños, sin necesidad de relaciones complejas entre ellos.
</details>

---

**8. ¿Qué trade-off existe respecto al formateo de código según el lenguaje en el ejercicio de Shared Code Snippets?**

<details>
<summary>Respuesta</summary>

El formateo puede resolverse en el momento de creación (precomputado una sola vez, con más costo de storage pero menos cómputo por request) o "al vuelo" en cada lectura (menos storage, pero más carga de CPU repetida en cada acceso). Hay que evaluar ese trade-off según el patrón de acceso esperado.
</details>

---

**9. En el ejercicio de Shared Code Snippets, ¿qué esquema de identificación se sugiere para el acceso a un snippet, y cómo se relaciona con el Teorema CAP?**

<details>
<summary>Respuesta</summary>

Se sugiere un esquema de identificación por URL/ID único (similar a los conceptos de identidad de entidades en RESTful), sin necesidad de un índice de búsqueda completo, ya que el acceso es "siempre que se conozca su ruta". Respecto del CAP, al ser un sistema de alta lectura/baja escritura con disponibilidad constante exigida, conviene priorizar Availability sobre Consistency estricta, dado que los snippets no requieren consistencia fuerte entre réplicas al ser de solo lectura una vez creados.
</details>

---
