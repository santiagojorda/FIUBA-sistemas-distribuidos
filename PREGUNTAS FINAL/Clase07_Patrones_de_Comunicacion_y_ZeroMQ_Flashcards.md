# Flashcards — Clase 07: Patrones de Comunicación y MOM Distribuido (ZeroMQ)

> Formato: pregunta primero, respuesta debajo. Tapá las respuestas y probate.

---

**1. ¿Cómo funciona el protocolo Request-Reply por defecto y cómo se implementan los ACKs?**

<details>
<summary>Respuesta</summary>

Es sincrónico (bloqueante) por defecto: el cliente envía un Request Message, el servidor lo recibe, procesa el mensaje y envía un Reply; el cliente queda bloqueado hasta recibir el Reply. Los ACKs son triviales, ya que el propio Reply message funciona como ACK.

![Cliente envía Request, espera, y recibe Reply del Servidor](../Presentaciones/Resumenes/Clase07_imagenes/pat4-04.png)
</details>

---

**2. ¿Cómo se implementa una operación asincrónica usando Request-Reply?**

<details>
<summary>Respuesta</summary>

Se necesitan 2 Request-Reply sincrónicos: 1° el cliente envía la acción a realizar, el servidor la encola y responde inmediatamente con un ACK sin esperar a que termine de procesarse; 2° el cliente pregunta el estado de la operación en otro momento, y el servidor obtiene y envía el estado actual.

![Cliente envía la acción, el servidor la encola y responde con un ACK](../Presentaciones/Resumenes/Clase07_imagenes/pat5-05.png)
![Cliente pregunta el estado, el servidor lo obtiene y responde](../Presentaciones/Resumenes/Clase07_imagenes/pat6-06.png)
</details>

---

**3. ¿Qué campos suelen ser obligatorios en la estructura de mensajes de Request-Reply?**

<details>
<summary>Respuesta</summary>

messageID (0 = Request, 1 = Reply), requestID (identifica unívocamente al mensaje, auto-incremental o UUID), operationID (identifica la acción/operación a realizar) y args (atributos asociados a la acción/operación).
</details>

---

**4. En Request-Reply, ¿qué estrategia de tolerancia a fallos se usa para decidir cuánto esperar por un Reply?**

<details>
<summary>Respuesta</summary>

Timeouts con reintentos (retries), usando algoritmos de Backoff + Jitter (por ejemplo, la estrategia de la API de Amazon).
</details>

---

**5. Compará las tres estrategias frente a la pérdida de un Request o Reply: Sin control, Re-ejecución y Retransmisión.**

<details>
<summary>Respuesta</summary>

Sin control: no hay retry ni filtro de duplicados, el mensaje recibido es "Maybe". Re-ejecución: hay retry pero no filtro de duplicados, garantiza "At Least Once". Retransmisión: hay retry y filtro de duplicados, garantiza "Exactly Once".
</details>

---

**6. Diferenciá el modelo Producer-Consumer del modelo Publisher-Subscriber.**

<details>
<summary>Respuesta</summary>

Producer-Consumer: comunicación por tareas; los Producers generan información como materia prima para procesamiento posterior, y los Consumers esperan esa información para procesarla. Publisher-Subscriber: comunicación por eventos; los Publishers generan elementos de interés y los Subscribers esperan eventos de su interés para efectuar una acción.
</details>

---

**7. ¿Qué dos arquitecturas posibles existen para Publisher-Subscriber y en qué se diferencian?**

<details>
<summary>Respuesta</summary>

Basada en tópicos: publicación y suscripción indicando el tipo de evento, tópico o tag. Basada en Canales: publicaciones y suscripciones orientadas a canales específicos.

![Publishers y Subscribers conectados a través de un Message Broker](../Presentaciones/Resumenes/Clase07_imagenes/pat13-13.png)
</details>

---

**8. Al implementar Publisher-Subscriber con MOMs, ¿cómo se diferencian el modelo Bus y el modelo de Colas?**

<details>
<summary>Respuesta</summary>

Bus (basado en topics): todos los participantes comparten un Message Bus único, publicando (V) o suscribiéndose (S) a ciertos tópicos. Colas (basado en canales): cada participante tiene su propia cola dedicada (q1, q2, q3) dentro del sistema de mensajería.

![Bus basado en tópicos vs Colas basadas en canales](../Presentaciones/Resumenes/Clase07_imagenes/pat14-14.png)
</details>

---

**9. ¿Qué es el patrón Pipelines and Filters y en qué está inspirado?**

<details>
<summary>Respuesta</summary>

Los datos de entrada forman un flujo donde distintos filters (o processors) se conectan entre sí para procesarlos de manera secuencial. Está inspirado en patrones de procesamiento de señales, muy utilizado en entornos Unix (ej. `cat in | grep pattern | sort | uniq > out`).
</details>

---

**10. Diferenciá los modelos de procesamiento Worker por Filter y Worker por Item en un pipeline.**

<details>
<summary>Respuesta</summary>

Worker por Filter: se asigna una unidad de procesamiento a cada etapa del pipeline, que recibe items, los procesa y los envía a la próxima etapa. Worker por Item: se asigna una unidad de procesamiento a cada item, que lo acompaña hasta el final del pipeline aplicándole los filters paso a paso.

![Pipeline con Source, Filter 1-3 y Sink](../Presentaciones/Resumenes/Clase07_imagenes/pat18-18.png)
</details>

---

**11. ¿Qué diferencia a una etapa Paralela de una etapa Secuencial dentro de un pipeline?**

<details>
<summary>Respuesta</summary>

Paralela: cada item a procesar es independiente de los anteriores y posteriores, por lo que admite paralelismo. Secuencial: no puede procesar más de un item a la vez, y una vez procesados los puede retornar ordenados o desordenados.

![Etapas paralelas y secuenciales en un pipeline procesando items](../Presentaciones/Resumenes/Clase07_imagenes/pat19-19.png)
</details>

---

**12. ¿Cuáles son las dos ventajas principales de los Pipelines?**

<details>
<summary>Respuesta</summary>

Algoritmos Online: permiten iniciar el procesamiento antes de que estén disponibles todos los datos. Información Infinita: permiten trabajar con flujos ilimitados de información con cantidades constantes de memoria, gracias al procesamiento encadenado con un buffer mínimo.
</details>

---

**13. ¿Qué es un DAG (Direct Acyclic Graph) y qué representan sus nodos y aristas?**

<details>
<summary>Respuesta</summary>

Es un modelo de instrucciones mediante un grafo de flujo de datos donde los nodos indican tareas y las aristas el flujo de información. Es acíclico: para todo nodo, no existe un camino que inicie y termine en él. Permite calcular el trabajo total de una secuencia de tareas y el camino crítico.

![Ejemplo de DAG con nodos A, B, C, D, E](../Presentaciones/Resumenes/Clase07_imagenes/pat22-22.png)
</details>

---

**14. ¿Cuáles son las ventajas de modelar con DAGs?**

<details>
<summary>Respuesta</summary>

Es una representación natural para dataflows, la carga de procesamiento se puede paralelizar (ej. procesar A, B, C, E en un proceso P0 mientras D se procesa en paralelo en P1), y admite Lazy Loading de las operaciones, procesando solo los nodos requeridos por dependencias.

![DAG procesado de forma serial vs paralela en distintos procesos](../Presentaciones/Resumenes/Clase07_imagenes/pat23-23.png)
</details>

---

**15. ¿Qué relación hay entre los DAGs y la detección de deadlocks?**

<details>
<summary>Respuesta</summary>

Los DAGs también se usan para modelar dependencias entre procesos, donde las dependencias implican posibilidad de bloqueo frente al pedido de un recurso de un proceso a otro. Si el grafo de espera (wait-for) es cíclico, existe posibilidad de deadlock; esto sirve para detectar y recuperar sistemas frente a deadlocks.

![Wait-for graph: DAG (sin ciclos) vs non-DAG con deadlock (cíclico)](../Presentaciones/Resumenes/Clase07_imagenes/pat24-24.png)
</details>

---

**16. ¿Qué es ZeroMQ y qué lo diferencia de un MOM tradicional con broker?**

<details>
<summary>Respuesta</summary>

ZeroMQ describe sus sockets como una evolución "sobrecargada" de un socket TCP convencional ("sockets on steroids"), agregando funcionalidades de alto nivel para mensajería distribuida. Es altamente performante y útil para crear brokerless middlewares (sin un broker central); la serialización queda a cargo del usuario.

![Diagrama humorístico: TCP socket + ingredientes mágicos = ZeroMQ Socket](../Presentaciones/Resumenes/Clase07_imagenes/zmq3-03.png)
</details>

---

**17. Nombrá los tipos de conexiones que soporta ZeroMQ y para qué escenario sirve cada uno.**

<details>
<summary>Respuesta</summary>

TCP: Multicomputing, Unicast (Point to Point). IPC: Multiprocessing, comunicación a través de Unix sockets. Inproc: Multithreading, queue entre threads. Otras: Multicast a través del protocolo PGM.
</details>

---

**18. ¿Cómo funciona el patrón Request-Reply en ZeroMQ (sockets REQ/REP) y qué particularidades tiene respecto al modelo Cliente-Servidor convencional?**

<details>
<summary>Respuesta</summary>

No posee primitiva accept: la primitiva bind funciona como bind + accept. La primitiva send es no bloqueante. El cliente no necesita esperar a que el servidor esté corriendo para enviar mensajes. Por debajo usa I/O threads (1 thread por GB/s de entrada o salida) y buffering.

![Cliente REQ y Servidor REP intercambiando Hello/World](../Presentaciones/Resumenes/Clase07_imagenes/zmq6-06.png)
</details>

---

**19. ¿Cómo funciona el patrón Producer-Consumer (Push-Pull) en ZeroMQ?**

<details>
<summary>Respuesta</summary>

Comunica tareas de un productor a un consumidor usando los sockets PUSH/PULL para marcar el rol de cada extremo. Admite múltiples consumidores y/o múltiples productores, garantizando fairness en la entrega de mensajes mediante round robin.

![Sockets PUSH distribuyendo tareas de forma fair a múltiples PULL Workers](../Presentaciones/Resumenes/Clase07_imagenes/zmq7-07.png)
</details>

---

**20. ¿Cómo funciona el patrón Publisher-Subscriber en ZeroMQ y qué patrón se usa para múltiples publishers?**

<details>
<summary>Respuesta</summary>

Un socket ZMQ PUB publica mensajes con el message pattern `id field1 field2 ...fieldN`. N sockets ZMQ SUB se registran a los eventos que desean recibir, suscribiéndose al ID del evento (la suscripción puede cancelarse en cualquier momento), y el mensaje se envía a todos los suscriptos a ese evento. Para múltiples publishers se utiliza el patrón XPUB-XSUB.

![Publisher PUB conectado a múltiples Subscribers SUB](../Presentaciones/Resumenes/Clase07_imagenes/zmq8-08.png)
</details>

---

**21. ¿Cómo se arma un patrón Pipeline (Push-Pull) en ZeroMQ y qué combinaciones admite?**

<details>
<summary>Respuesta</summary>

Es un chaining de Producer-Consumer: un Ventilator (PUSH) distribuye tareas a Workers (PULL/PUSH) que envían resultados a un Sink (PULL), consumiendo los mensajes de forma equitativa (fairness). Admite combinaciones de 1 PUSH → N PULL, o N PUSH → 1 PULL.

![Ventilator (PUSH) distribuye tareas a Workers (PULL/PUSH) que envían resultados a un Sink (PULL)](../Presentaciones/Resumenes/Clase07_imagenes/zmq9-09.png)
</details>

---

**22. ¿Qué rol cumplen los sockets ROUTER y DEALER en el patrón Router-Dealer (Broker) de ZeroMQ?**

<details>
<summary>Respuesta</summary>

ROUTER: agrega al mensaje recibido un ID de destinatario. DEALER: rutea los mensajes de forma justa (fair), propagando el ID de origen del mensaje. Ambos permiten recibir mensajes de múltiples sockets a la vez y son asincrónicos (se necesita Poll para recibir mensajes). Este patrón permite construir un broker intermedio entre múltiples clientes (REQ) y múltiples servicios (REP).

![Clientes REQ conectados a un broker ROUTER-DEALER que distribuye a servicios REP](../Presentaciones/Resumenes/Clase07_imagenes/zmq10-10.png)
</details>

---
