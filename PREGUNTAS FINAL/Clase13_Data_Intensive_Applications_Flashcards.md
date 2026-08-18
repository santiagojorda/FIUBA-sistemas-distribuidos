# Flashcards — Clase 13: Data Intensive Applications

> Formato: pregunta primero, respuesta debajo. Tapá las respuestas y probate.

---

**1. ¿Qué componentes suele combinar el flujo de datos de un sistema de gran escala típico?**

<details>
<summary>Respuesta</summary>

Un Cache (lookups/writes rápidos), un MOM para encolar operaciones asíncronas, tres tipos de almacenamiento de datos —Master Data, Transactional Data y Search Indexes— alimentados por servicios que detectan cambios y populan índices, y un punto de integración con servicios externos.

![Flujo de datos: Services consultan Cache y bases (Master Data, Transactional Data, Search Indexes), encolan tareas asíncronas en un MOM y se integran con servicios externos](../Presentaciones/Resumenes/Clase13_imagenes/pag-03.png)
</details>

---

**2. Diferenciá el almacenamiento Relacional del No Relacional (NoSQL) y para qué modelos de datos favorece cada uno.**

<details>
<summary>Respuesta</summary>

Relacional: predomina hasta 2010 con la estandarización de SQL, almacena en tablas y filas, y tiene buen soporte para joins y relaciones many-to-one o many-to-many. NoSQL (Not Only SQL): a partir de 2010 se imponen otros almacenamientos (clave-valor, documentales, orientados a grafos, columnares), con beneficios claros para modelos sin relaciones, one-to-many jerárquicos, alta conectividad (grafos), y esquemas cambiantes o no definidos.
</details>

---

**3. Diferenciá OLTP de OLAP en cuanto a patrón de lectura, escritura, uso principal y tamaño de datos.**

<details>
<summary>Respuesta</summary>

OLTP (Online Transaction Processing): orientado a transacciones (grupos de reads/writes), no necesariamente ACID. Lectura de pocos registros por clave, escritura de acceso aleatorio con registros pequeños, uso principal como info maestra/transaccional para usuarios, con datos como instantánea actual (MBs-GBs). OLAP (Online Analytical Processing): orientado a analizar el conjunto de los datos. Lectura por agregación de muchos registros, escritura por importaciones batch (ETLs) o streams, uso principal para exploración/análisis estadístico, con datos históricos (TBs-PBs).
</details>

---

**4. ¿Cómo difiere el almacenamiento Columnar del Relacional, y qué beneficios trae?**

<details>
<summary>Respuesta</summary>

El modelo relacional normalmente usa un archivo de almacenamiento por tabla, leyendo la fila completa para retornar proyecciones. El modelo columnar usa un archivo por columna, almacenando cada columna como una secuencia contigua de valores, lo cual trae grandes beneficios para compresión, lectura y agregaciones, favoreciendo mucho las consultas analíticas.
</details>

---

**5. ¿Qué son los Cubos de Información y qué operaciones se consultan sobre ellos?**

<details>
<summary>Respuesta</summary>

Normalmente mantienen vistas materializadas con pre-cálculos estadísticos, creando grillas agrupadas por diferentes dimensiones (ej. un cubo cruzando date_id x product_id x quantity). Se consultan operaciones como SUM, COUNT, MAX, MIN y AVG sobre estos cubos.

![Cubo de información cruzando date_id x product_id x quantity con totales](../Presentaciones/Resumenes/Clase13_imagenes/pag-08.png)
</details>

---

**6. Describí la Replicación Leader-based: qué réplicas aceptan escrituras/lecturas y qué problemas presenta.**

<details>
<summary>Respuesta</summary>

Una réplica se designa como master/leader, y las demás como mirrors/slaves/followers. Solo se aceptan escrituras en el leader; tanto el leader como los followers aceptan lecturas. La replicación puede ser síncrona o asíncrona. Presenta problemas de Read your own writes y Monotonic reads.

![Leader Replica recibe Read/Writes y replica vía Mirroring a Follower Replicas, que solo aceptan lecturas](../Presentaciones/Resumenes/Clase13_imagenes/pag-10.png)
</details>

---

**7. ¿En qué escenario se usa la Replicación Multi-leader y qué problema adicional presenta respecto de Leader-based?**

<details>
<summary>Respuesta</summary>

Es el modelo normal en escenarios de múltiples data-centers, donde frente a la caída de uno se puede promover al otro como líder global. Presenta los mismos problemas que Leader-based, más la posibilidad de conflictos por concurrencia, además de otros inconvenientes como el manejo de triggers, claves incrementales e integridad de relaciones.

![Dos Leader Replicas en distintos data-centers replicándose mutuamente con resolución de conflictos, cada uno con sus Follower Replicas](../Presentaciones/Resumenes/Clase13_imagenes/pag-11.png)
</details>

---

**8. ¿Cómo funciona la Replicación Leaderless y qué topologías de sincronización puede usar?**

<details>
<summary>Respuesta</summary>

Es un sistema de replicación totalmente distribuido donde las réplicas deben sincronizarse mutuamente, pudiendo definirse topologías en anillo, jerárquicas, o todos contra todos. Los conflictos son muy frecuentes a menos que se particione; otra alternativa es conseguir un consenso entre las réplicas para aplicar escrituras.

![Cuatro réplicas sincronizándose mutuamente todas contra todas, todas aceptando Read/Writes](../Presentaciones/Resumenes/Clase13_imagenes/pag-12.png)
</details>

---

**9. Diferenciá el Particionamiento Horizontal del Vertical.**

<details>
<summary>Respuesta</summary>

Horizontal: la información se segrega por registros entre cada partición, y el registro se encuentra en UNA sola partición a la vez (ej. la tabla Sales dividida por `date_id`). Vertical: la información se segrega respecto de sus atributos/dimensiones/campos, y el registro se encuentra en TODAS las particiones (ej. una partición con `date_id, product_id, qty, price` y otra con `date_id, product_id, disc`).
</details>

---

**10. Nombrá las funciones de partición vistas y qué son las estrategias mixtas.**

<details>
<summary>Respuesta</summary>

Por Value-of-Key, por Range-of-Keys, y por Hash-of-Key. Las estrategias mixtas incluyen generar N shards por cada key, o particionar por claves secundarias.
</details>

---

**11. Nombrá las tres estrategias de enrutamiento hacia particiones y en qué se diferencian.**

<details>
<summary>Respuesta</summary>

Cualquier partición + redirección: el cliente contacta cualquier partición y, si no tiene los datos, esta lo redirige a la partición correcta. Router centralizado: el cliente siempre consulta a un componente Router, que conoce la ubicación de cada dato y lo redirige. Cliente con conocimiento directo: el cliente ya sabe en qué partición están los datos y accede directamente, sin intermediarios.

![Tres estrategias de enrutamiento: contactar cualquier partición y redirigir, usar un Router central, o que el cliente sepa directamente a qué partición ir](../Presentaciones/Resumenes/Clase13_imagenes/pag-17.png)
</details>

---

**12. ¿Cuál es el objetivo de Distributed Shared Memory (DSM) y cuáles son sus principales ventajas y desventajas?**

<details>
<summary>Respuesta</summary>

Su objetivo es brindar la ilusión de una memoria compartida centralizada. Ventajas: es muy intuitivo para el desarrollo de sistemas distribuidos (los algoritmos no distribuidos se traducen fácilmente) y permite compartir información entre nodos sin que se conozcan entre sí. Desventajas: desalienta la distribución, genera latencia, cuello de botella y punto único de falla (arquitectura cliente-servidor).
</details>

---

**13. Describí el enfoque Naive de DSM y por qué garantiza consistencia fácilmente.**

<details>
<summary>Respuesta</summary>

La información se almacena en memoria por el servidor, y los clientes acceden mediante requests para escribir o leer las páginas. El servidor puede garantizar la consistencia muy fácilmente serializando los requests, aunque esto resulta en muy baja performance para las aplicaciones cliente.

![Server centraliza las Memory Pages; Clients piden locks que pueden ser aceptados o denegados](../Presentaciones/Resumenes/Clase13_imagenes/pag-20.png)
</details>

---

**14. En DSM con Migración de Memory Pages, ¿qué sucede si dos clientes piden la misma página?**

<details>
<summary>Respuesta</summary>

La información se almacena en el servidor y se delega en los clientes, que pueden optimizar la localidad de acceso pidiendo una memory page prestada. Otros clientes que piden la misma página quedan bloqueados, salvo que se permita una sub-delegación. Esto garantiza consistencia, ya que no se accede concurrentemente a las páginas.

![Server delega Page A a un Client mediante Page migration; otros clientes que piden la misma página quedan bloqueados (Page request)](../Presentaciones/Resumenes/Clase13_imagenes/pag-21.png)
</details>

---

**15. Diferenciá la Replicación de Memory Pages de solo lectura de la de lectura-escritura en DSM.**

<details>
<summary>Respuesta</summary>

Solo lectura: favorece escenarios con muchas lecturas y pocas escrituras; las escrituras son coordinadas por el servidor, las lecturas implican replicar la página en modo read-only, y el servidor invalida las réplicas frente a cambios. Lectura-escritura: el servidor mantiene las páginas hasta que los clientes las requieren, los clientes toman control total de las réplicas, y el servidor se transforma en un Write Sequencer que propaga las actualizaciones (Page update) a las demás réplicas, aplicando los cambios también ante caídas de clientes.

![Write Sequencer mantiene las páginas hasta que los clientes las requieren, propagando Page updates entre réplicas](../Presentaciones/Resumenes/Clase13_imagenes/pag-23.png)
</details>

---

**16. ¿Cuáles son los factores de diseño de transparencia que debe cumplir un Distributed File System (DFS)?**

<details>
<summary>Respuesta</summary>

Acceso (obtención de recursos con credenciales usuales), Localización (operación de archivos como si fueran locales), Movilidad (el movimiento interno de archivos no debe ser percibido) y Performance y Escala (las optimizaciones no deben afectar al cliente). Además debe soportar Concurrencia sin operaciones particulares al cliente, Heterogeneidad de Hardware y Tolerancia a Fallos.
</details>

---

**17. Describí la arquitectura de NFS: origen, abstracción de kernel requerida y protocolo de comunicación.**

<details>
<summary>Respuesta</summary>

Diseñado para ser independiente de plataformas (aunque desarrollado sobre UNIX), su primera versión es de 1984 por Sun Microsystems. Requiere una nueva abstracción en el kernel: el Virtual File System (VFS). Usa arquitectura cliente-servidor con RPC sobre TCP o UDP; las aplicaciones acceden a los archivos a través del VFS, lo que implica una invocación remota, y los servidores proveen operaciones idénticas a las de Posix.

![Arquitectura NFS: App1/App2 acceden vía Virtual FS y NFS Client (Client), que se comunica vía NFS Protocol/RPC con el NFS Server (Server)](../Presentaciones/Resumenes/Clase13_imagenes/pag-28.png)
</details>

---

**18. ¿Cuáles son los principales factores de diseño de HDFS (Hadoop DFS)?**

<details>
<summary>Respuesta</summary>

Tolerancia a Fallos (los fallos de HW son normales, es más económico adaptarse que defenderse), Volumen y Latencia (favorece streaming y archivos volumétricos frente a baja latencia de usuarios finales), Portabilidad (preparado para hardware de bajo costo, usa TCP entre servidores y RPC con clientes), y Performance (favorece lectura, política write-once-read-many). No soporta POSIX, por lo que se lo considera un Data Storage más que un FS, y sigue el principio de "Moving Computation is Cheaper than Moving Data".
</details>

---

**19. Describí la arquitectura maestro-esclavo de HDFS: rol del Namenode y de los Datanodes.**

<details>
<summary>Respuesta</summary>

Namenode: contiene la metadata de archivo y coordina a los Datanodes. Datanodes: almacenan los datos de archivo. Los clientes consultan al Namenode por el 'File system' y la ubicación de los datos, y luego se comunican directamente con los Datanodes para obtener la información.

![Arquitectura maestro-esclavo de HDFS: Client consulta al Namenode (metadata) y luego a los Datanodes (File Blocks)](../Presentaciones/Resumenes/Clase13_imagenes/pag-32.png)
</details>

---

**20. ¿Cómo se almacenan los datos en HDFS y cómo se mantiene la metadata?**

<details>
<summary>Respuesta</summary>

Los archivos se particionan en bloques de 128MB, que son replicados en distintos Datanodes. El Namenode mantiene el listado de Datanodes para cada archivo, con la metadata en memoria para optimizar el acceso y un log de transacciones (Edit Log). El cluster de Datanodes permite re-balanceo de bloques.

![Un archivo se particiona en bloques de 128MB que se replican entre distintos Datanodes, con metadata en el Namenode y un Edit Log](../Presentaciones/Resumenes/Clase13_imagenes/pag-33.png)
</details>

---

**21. ¿Cómo favorece HDFS la localidad de datos al acceder a los bloques desde un cliente?**

<details>
<summary>Respuesta</summary>

El Namenode favorece el principio de localidad de datos para el cliente: este recibe el listado de Datanodes para cada bloque y sus réplicas, intentando obtener los bloques desde el mismo rack; si no es posible, desde el mismo datacenter.

![Client A en el mismo Rack que sus Datanodes; Namenode y Client B en otro Rack del mismo Data Center](../Presentaciones/Resumenes/Clase13_imagenes/pag-34.png)
</details>

---
