# Sistemas Distribuidos I (75.74) — Clase 15: Diseño de Arquitecturas de Gran Escala

## NALSD (Non-Abstract Large-Scale System Design)

Esta clase aplica la metodología **NALSD** (*Non-Abstract Large-Scale System Design*), propuesta por Google SRE, para diseñar la arquitectura concreta (no abstracta) de sistemas a gran escala. La idea central es que, dado un enunciado de requerimientos, el diseño debe ser **tangible**: especificar componentes reales, estimar volúmenes de datos/tráfico, elegir tecnologías concretas (bases de datos, colas, balanceadores, etc.) y justificar las decisiones de particionamiento, replicación, caching y escalabilidad — no quedarse en diagramas genéricos tipo "Cliente → Servidor → Base de Datos".

Referencia: [Introducing Non-Abstract Large System Design](https://sre.google/workbook/non-abstract-design/).

La clase consiste en dos ejercicios prácticos de diseño para aplicar esta metodología.

---

## Ejercicio 1: Traffic Lights Violations Detector

### Requerimientos

- Se requiere un sistema de **detección de infracciones** para la ciudad.
- Se cuenta con las **imágenes de las patentes** capturadas por las cámaras en cada semáforo.
- Los semáforos a su vez **emiten señales** que indican su estado: **verde, amarillo o rojo**.
- Se debe **emitir una infracción** a ser enviada al propietario del vehículo y al **ente regulador** para su procesamiento.
- Las infracciones deben soportar su **inspección y administración** por parte del personal del gobierno.

### Puntos clave de diseño a considerar

- El sistema combina dos flujos de eventos que deben **correlacionarse en tiempo**: el estado del semáforo (verde/amarillo/rojo) y la captura de imágenes de patentes. Una infracción solo debe generarse cuando una patente es detectada cruzando **durante el rojo**, por lo que conviene pensar en una ventana de tiempo (*time window*) que vincule ambos eventos por semáforo/cámara.
- Al tratarse de muchos semáforos distribuidos geográficamente generando eventos de forma continua, es un buen caso de uso para un **pipeline de streaming** (similar a los patrones vistos en clases anteriores: Pipelines, Pub-Sub, MOM) en lugar de un procesamiento batch.
- El procesamiento de imágenes (reconocimiento de patente) es la etapa más costosa computacionalmente: conviene desacoplarla del resto del flujo (ej. como una etapa paralela de un pipeline) para no bloquear la ingestión de eventos de los semáforos.
- Las infracciones generadas requieren **persistencia duradera** (para inspección y administración posterior) y **dos destinos de notificación** distintos (propietario del vehículo y ente regulador), lo que sugiere un patrón de notificación tipo Publisher-Subscriber o el envío a colas separadas por destinatario.
- Hay que estimar volúmenes: cantidad de semáforos en una ciudad, frecuencia de detecciones, para dimensionar el throughput esperado del sistema (parte central de la metodología NALSD: no quedarse en lo abstracto).

---

## Ejercicio 2: Shared Code Snippets

### Requerimientos

- Los usuarios deben poder **compartir pequeños bloques de código**.
- Los bloques compartidos son de **acceso público** siempre que se conozca su **ruta de acceso**.
- Se debe **formatear el código** de acuerdo con un lenguaje indicado por el usuario.
- Los distintos *snippets* deben ser **almacenados por tiempo indefinido**.
- Dado el auge en entornos de trabajo compartido, se espera **gran cantidad de accesos diarios** con nuevos *snippets*.
- El sistema debe mostrar **disponibilidad constante**.

### Puntos clave de diseño a considerar

- Es un sistema de **lectura intensiva** (alta disponibilidad y gran cantidad de accesos) con datos relativamente pequeños e **inmutables una vez creados** (el snippet no cambia, solo se lee), lo cual favorece fuertemente el uso de **caching** y **réplicas de solo lectura**.
- El acceso "siempre que se conozca su ruta" sugiere un esquema de identificación por URL/ID único (similar a los conceptos de identidad de entidades vistos en RESTful), sin necesidad de un índice de búsqueda completo.
- El **almacenamiento por tiempo indefinido** de un gran volumen de bloques pequeños es un buen caso de uso para almacenamiento tipo *blob storage* / objeto, en lugar de una base de datos relacional tradicional.
- El **formateo de código según el lenguaje** es una operación de CPU que puede resolverse en el momento de creación (una sola vez) o "al vuelo" en cada lectura; conviene pensar el trade-off entre precomputar el formato (más storage, menos cómputo por request) vs. formatear en cada acceso (menos storage, más carga de CPU repetida).
- La **disponibilidad constante** exigida, combinada con el patrón de alta lectura/baja escritura, es un caso típico para priorizar **Availability** sobre **Consistency** estricta en términos del Teorema CAP, ya que los snippets no requieren consistencia fuerte entre réplicas (son de solo lectura una vez creados).
