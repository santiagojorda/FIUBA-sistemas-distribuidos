# Ejercicios Prácticos de los Integradores — Sistemas Distribuidos I (75.74)

Extraído de la carpeta `INTEGRADORES/` (principalmente `RESUELTOS.pdf`, que compila los exámenes hasta el 20/02/2025, más los exámenes sueltos posteriores en foto/PDF). En cada examen las **últimas 3 preguntas** (a veces 4, cuando el examen tiene 11 puntos) son las prácticas; las primeras son teóricas y no se incluyen acá.

Los ejercicios están agrupados por la clase/tema de la materia al que corresponden (según `Presentaciones/Resumenes/`). Varios ejercicios se repiten (idénticos o con variantes) entre exámenes de distintas fechas — se listan todas las apariciones.

Exámenes relevados: **2022-08-02, 2022-08-09, 2023-07-25, 2024-07-08, 2024-07-16, 2024-12-19, 2025-02-13, 2025-02-20, 2025-02-27, 2025-03-06, 2025-07-03, 2025-07-17, 2025-07-24**.

---

## Clase 02 — Multitasking y Comunicaciones (Barreras / sincronización)

Todos son variantes del mismo problema (sincronizar 3 procesos en un punto de ejecución), cambiando el mecanismo de IPC usado.

- **[2024-07-16]** Utilizando *blocking-queues*, implemente una barrera para que 3 procesos llamados *workers* puedan sincronizarse en cierto punto del algoritmo que ejecutan. Detalle supuestos de ser necesario. Utilice pseudocódigo o diagrama UML (secuencia, colaboración o actividades).

- **[2024-12-19]** Utilizando *request-reply*, implemente una barrera para que 3 procesos llamados *workers* puedan sincronizarse en cierto punto del algoritmo que ejecutan. Detalle supuestos de ser necesario. Utilice pseudocódigo o diagrama UML.
  - Request-reply **sincrónico** (los procesos esperan la respuesta).
  - El server devuelve ACK únicamente cuando tiene encoladas tantas requests como procesos en el sistema (3).

- **[2025-02-20]** Utilizando *blocking-queues*, implemente un procesamiento con arquitectura productor-consumidor donde exista una barrera para que 3 procesos consumidores se esperen entre sí luego de haber procesado 2 ítems cada uno. Utilice pseudocódigo o diagrama UML.

- **[2025-07-03]** Utilizando *MOMs*, implemente una barrera para que 3 procesos llamados *workers* puedan sincronizarse en cierto punto del algoritmo que ejecutan. Detalle supuestos de ser necesario. Utilice pseudocódigo o diagrama UML.

---

## Clase 05 — Grupos, Middlewares, MOMs y RabbitMQ

- **[2025-07-24]** Dada una librería basada en MOMs, realice un pequeño sistema que procese encuestas recibiendo los datos por un *stream* infinito de mail+calificación. El sistema debe ser escalable y permitir:
  - a) enviar un mail de disculpas a todo usuario detractor (calificación < 7)
  - b) enviar un mail de agradecimiento a todo usuario promotor (calificación > 8)
  - Utilice pseudocódigo o diagrama UML (secuencia, colaboración o actividades) e indique supuestos de ser necesario.

---

## Clase 07 — Patrones de Comunicación (Request-Reply, Producer-Consumer, Publisher-Subscriber, Pipelines y DAGs)

**Publisher-Subscriber**

- **[2022-08-02]** Utilizando una arquitectura Publisher-Subscriber, calcule la suma de todos los enteros incluidos en un vector de tamaño N, optimizando el uso de P procesos conocidos como disponibles. Utilice pseudocódigo o diagrama UML (secuencia, colaboración o actividades).

- **[2025-02-27]** Dada una librería de publisher-subscriber, escriba un sistema que imprima por consola la suma de un gran vector de enteros leídos por entrada estándar, distribuyendo la carga entre N servidores conocidos. Utilice pseudocódigo.

- **[2025-07-24]** Utilizando una arquitectura Publisher-Subscriber, calcule el promedio de ventas de todos los registros de pasajes de colectivo recibidos en modo *streaming* (id, valor). Optimice el uso de P procesos conocidos y entregue resultados en ventanas de 1M registros. Utilice pseudocódigo.

**Request-Reply / Producer-Consumer**

- **[2022-08-09]** Utilizando una arquitectura Request-Reply, ejecute de forma remota la productoria de un arreglo de enteros de manera asincrónica. Mientras la ejecución transcurre, calcule la sumatoria. Por último, imprima ambos resultados. Utilice pseudocódigo o diagrama UML.

- **[2024-07-08]** Dada una librería basada en request-reply, realice un pequeño sistema que calcule el hash de un archivo binario leyendo sus bloques de 4 bytes y aplicando sucesivamente la operación XOR a medida que se leen más bloques. Distribuya la carga de cómputo entre N servidores conocidos. Utilice pseudocódigo o diagrama UML e indique supuestos de ser necesario.

- **[2025-03-06]** Dada una librería basada en request-reply, desarrolle un sistema que capture por STDIN las líneas de log de un servidor Nginx y las distribuya entre N nodos de cómputo conocidos para ejecutar una colección de RegEx para detectar ataques de robots conocidos. Frente a un resultado positivo de al menos una RegEx, el nodo debe reportar "NOK" y el sistema debe imprimir "NOK - {log}". Si no se encontraron problemas, el sistema debe imprimir "OK - {log}". Utilice pseudocódigo e indique supuestos de ser necesario.

**Pipelines y DAGs**

- **[2022-08-09]** Ejemplifique el uso de Direct Acyclic Graphs (DAGs) al diseñar el procesamiento de datos de todas las ventas diarias de una cadena de tiendas de ropa. Cada venta posee ID de tienda y un arreglo con: monto unitario, cantidad y código de producto. Se pretende obtener: Q1) los 10 códigos de producto más vendidos, Q2) el monto promedio de venta, Q3) la cantidad de ventas con más de 3 productos.

- **[2025-02-20]** Ejemplifique el uso de Direct Acyclic Graphs (DAGs) al diseñar el procesamiento de datos de todas las ventas diarias de una cadena de tiendas de ropa (mismo esquema que arriba). Se pretende obtener los 10 códigos de producto más vendidos, montos min-max-avg de ventas, y la cantidad de ventas que incluían más de 3 productos.

---

## Clase 09 — Arquitecturas Distribuidas Simples (Distributed Objects)

- **[2023-07-25]** Defina con pseudocódigo los pasos para extraer $1000 de una cuenta bancaria de número CA-1234 y acreditarlos en otra de número CA-S673, asumiendo la existencia de una plataforma de Distributed Objects. Realice un gráfico que ejemplifique la arquitectura de Distributed Objects y el estado de la operación luego de ejecutarla.

- **[2024-07-16]** Defina con pseudocódigo los pasos para consultar el estado de una suscripción de Netflix con número NF-1234, obtener todos los serial numbers de dispositivos permitidos en la suscripción y dar de alta otra suscripción número NF-12345, asumiendo la existencia de una plataforma de Distributed Objects. Realice un gráfico que ejemplifique dicha arquitectura y el estado de los objetos.

- **[2025-07-03]** Defina con pseudocódigo los pasos para extraer $1000 de una cuenta bancaria de número CA-1234 y acreditarlos en otra de número CA-5678, asumiendo la existencia de una plataforma de Distributed Objects. Realice un gráfico que ejemplifique la arquitectura de Distributed Objects y estado de las instancias luego de ejecutar la operación.

---

## Clase 10 — Distribución y Coordinación de Procesos (MapReduce)

- **[2023-07-25]** Utilizando map-reduce para distribuir la carga, procese los eventos de log de una aplicación Web mediante un listado de tuplas (email, url_navegada, fecha) y calcule:
  - a) Cantidad de navegaciones detectadas por día de semana (lu, ma, ..., do)
  - b) Listado de emails con más de 10 navegaciones registradas.
  - Utilice pseudo-código e indique supuestos de ser necesario.

- **[2024-12-19]** Utilizando map-reduce, procese los eventos de mensajes recibidos en un chatbot mediante un listado de tuplas (messageId, clientPhoneNumber, text, date, time) y calcule:
  - a) cantidad de clientes atendidos por día del mes (1, 2, …, 30 ó 31)
  - b) listado de teléfonos con más de 10 mensajes recibidos en un mismo día. Utilice pseudocódigo.

- **[2025-02-13]** Detalle cómo sería una implementación de map-reduce que reciba las llamadas que ocurren por día en una compañía telefónica. Cada llamada cuenta con nro_origen, nro_destino, timestamp, duracion (en segundos). Resuelva:
  - a) Duración total de las llamadas para cada nro_origen
  - b) Determinar el nro_destino que recibió más llamadas
  - c) Duración promedio de cada llamada

- **[2025-03-06]** Ejemplifique el uso de Map-Reduce al diseñar el procesamiento de todas las compras de moneda extranjera de un banco a lo largo del mes. Cada compra posee fecha, num-cuenta, cod-divisa, cantidad-divisas, tasa-cambio-AR$. Se pretende obtener:
  - a) monto promedio de AR$ utilizado para compra de divisas "USD" por día del mes
  - b) el listado de números de cuenta que compraron divisas "USD" durante 2 o más días consecutivos
  - c) el listado de números de cuenta que compraron más divisas "USD" que la media.

- **[2025-07-17]** Utilizando map-reduce para distribuir la carga, procese los eventos de log de una aplicación Web mediante un listado de tuplas (email, url_navegada, fecha) y calcule:
  - Cantidad de navegaciones detectadas por día de semana (lu, ma,..., do)
  - URL con más navegaciones registradas
  - Listado de emails con más de 10 navegaciones registradas. Utilice pseudo-código e indique supuestos de ser necesario.


---

## Clase 19 — Algoritmos de Consenso

- **[2024-07-08]** Detalle un algoritmo de consenso que permita que 3 procesos concuerden en el valor de altitud de un dron en pleno vuelo. Muestre paso a paso cómo funciona el algoritmo considerando que los procesos A, B miden 10m mientras que C mide 9m. *(Usar Generales Bizantinos)*.

- **[2025-02-27]** Detalle un algoritmo de consenso que permita que 4 servicios concuerden en el valor de tasa de cambio dólar a publicar, luego de obtener mediciones independientes de distintas fuentes de datos. ¿Cómo funciona cada paso del algoritmo considerando las mediciones: a. 1010, b. 1000, c. 1000, d. 1030?

---

## Clase 20 — Tiempo, Relojes, Sincronismo, Orden y Cortes de Estado

- **[2022-08-02]** Dado el siguiente diagrama de tiempo, calcule el valor de relojes lógicos para cada evento. Utilizando únicamente los vectores de relojes, establezca la relación entre b y g, y entre d y g. Justifique. *(requiere el diagrama del examen original en PDF)*.

- **[2025-07-17]** Reconstruya el diagrama de tiempo de los eventos a, b, c, d, e, f, g para la comunicación de 3 procesos dados los siguientes vectores de relojes indicados. Establezca la relación entre los pares de eventos a-d y entre a-f.
  - Vectores de relojes: a-[0,1,0]  b-[1,1,0]  c-[2,1,0]  d-[2,2,0]  e-[0,0,1]  f-[3,1,1]  g-[2,3,0]


---

## Arquitecturas de gran escala (Diseño escalable / NALSD)

Estos son, por lejos, los ejercicios prácticos más repetidos (siempre la última pregunta del examen). Corresponden a **Clase 15 — Diseño de Arquitecturas de Gran Escala** (NALSD: Non-Abstract Large-Scale System Design), y todos piden resolver mediante análisis de volumen, endpoints/lista de endpoints y vista física con su explicación.

- **[2022-08-02] Smart TV — canales LG:** Diseñe una arquitectura que asegure la escalabilidad para un sistema con los siguientes requisitos:
  - a) Recibir usuario, timestamp y cambios de canales realizados en Argentina y Brasil por usuarios que poseen Smart TV de la marca LG y aceptó los términos y condiciones que incluyen monitoreo de uso.
  - b) Consultar la cantidad de usuarios actualmente sintonizando cierto canal.
  - c) Consultar los 5 canales más visualizados por los usuarios (mayor cantidad de minutos) en cierto rango de días.
  - d) Consultar cantidad de usuarios con más de 1 visualización por día.

- **[2022-08-09] / [2025-02-13] Trenes de larga distancia:** Diseñe una arquitectura que asegure la escalabilidad para un sistema con los siguientes requisitos:
  - a) Recolectar la información de ventas de pasajes de trenes de larga distancia de toda Argentina, desde las distintas estaciones que funcionan como puntos de venta.
  - b) Recibir listado actualizado de servicios a prestar indicando origen, destino, fecha y cant. de asientos.
  - c) Recibir pedido de compra con destino, fecha de partida, nombre de cada pasajero y foto de cada DNI.
  - d) Permitir consultar fotos de DNI de pasajeros incluyendo origen y destino si se posee la fecha de partida.

- **[2023-07-25] / [2025-07-03] WhatsApp — canal oficial Anses:** Diseñe una arquitectura que asegure la escalabilidad para un sistema con los siguientes requisitos:
  - a) Recibir mensajes WhatsApp incluyendo campos con tipo (texto o audio), contenido (string o binario), teléfono origen y nombre de usuario para procesar las consultas del canal oficial de Anses.
  - b) Procesar todos los mensajes de audio para obtener el texto a partir del audio recibido.
  - c) Identificar palabras clave y usar tablas p/calc. área, siendo: i) Jubilaciones y Pensiones, ii) Asignaciones Familiares, iii) Otras.
  - d) Crear un ticket con el contenido mediante POST en sistema externo y retornar ID al usuario.
  - e) Permitir la consulta de tickets por número, palabra clave y/o área dentro de un rango de fechas.

- **[2024-07-08] Aires acondicionados inteligentes (LATAM):** Diseñe una arquitectura que asegure la escalabilidad para un sistema con los siguientes requisitos:
  - a) Permitir la asignación de Aires Acondicionados inteligentes en LATAM para la captura de datos: fecha última medición, minutos en uso desde última medición, temperatura medida, ubicación aproximada (lat, long).
  - b) Asegurar la captura de datos con una frecuencia de 10 minutos.
  - c) Permitir la consulta de un reporte con ciudades conocidas y temperatura min, max, avg, medidas en las últimas 24hs.
  - d) Permitir la generación de una alarma y reporte por email al dueño del dispositivo si se detecta uso excesivo: más de 12 horas de uso durante las últimas 24 horas.

- **[2024-07-16] Reporte ciudadano de infracciones (CABA):** Diseñe una arquitectura que asegure la escalabilidad para un sistema con los siguientes requisitos:
  - 1) Permitir el reporte ciudadano de infracciones de tránsito presenciadas en vía pública en CABA.
  - 2) El reporte consta de una foto e indica el tipo de infracción ("vehículo mal estacionado", "cruce en rojo", "choque con fuga") y una descripción de lo ocurrido.
  - 3) Reconocer el vehículo del reporte y los datos de su titular, dejando registro.
  - 4) Analizar automáticamente la foto para el tipo "cruce en rojo" y emitir una multa por email al titular en caso de validar la infracción.
  - 5) Permitir consulta para evaluación manual de los tipos restantes y para auditoría en general por 10 años.
  - 6) Notificar por email al ciudadano sobre el estado de su reporte a los 7 días.

- **[2024-12-19] Cadena de café/cookies (autoservicio):** Diseñe una arquitectura que asegure la escalabilidad para un sistema con los siguientes requisitos:
  - a) Tomar los pedidos de café y cookies en terminales AUTOSERVICIO de una cadena multinacional con sucursales en las capitales de todos los países, para que empleados preparen y cobren pedidos en caja.
  - b) Emitir una comanda de pedido con cantidad y producto en las terminales COCINA y un ticket de cobro con precio unitario y total en las terminales CAJA de la sucursal.
  - c) Recibir de forma centralizada la lista de productos y fotos a vender en cada sucursal.
  - d) Recibir de forma centralizada los pedidos de cambio de precio unitario para cada sucursal.
  - e) Permitir consultar ventas totales por día y sucursal.

- **[2025-02-20] Aulas virtuales (escuelas primarias):** Diseñe una arquitectura que asegure la escalabilidad para un sistema con los siguientes requisitos:
  - a) Permitir al administrador la creación de aulas virtuales para escuelas primarias argentinas con sus correspondientes archivos multimedia: N videos incluyendo título y resumen.
  - b) Permitir a los alumnos el ingreso a cualquier aula y reproducción de video.
  - c) Permitir a los alumnos ver y crear comentarios sobre cualquiera de los videos.
  - d) Permitir ver un ranking de los videos más reproducidos con información actualizada cada hora como mínimo.

- **[2025-02-27] Cámaras de ingreso/egreso (cadena de shoppings):** Diseñe una arquitectura que asegure la escalabilidad para un sistema con los siguientes requisitos:
  - Recibir capturas de cámaras de ingreso/egreso en puertas de acceso de una cadena de Shoppings.
  - Detectar ingreso o egreso de los empleados considerando una base con fotos de legajo previa.
  - Determinar cant. de minutos trabajados por cada empleado utilizando la info de ingreso/egreso.
  - Cada 60 minutos se debe imprimir los legajos y nombres de todos los empleados presentes.
  - Resuelva mediante lista de endpoints, análisis de volumen y vista física con su explicación.

- **[2025-03-06] Contenedores de basura con QR (CABA):** Diseñe una arquitectura que asegure la escalabilidad para un sistema con los siguientes requisitos:
  - Asignar tags QR a los contenedores de basura de CABA y permitir su lectura durante la recolección.
  - Reportar el peso medido, timestamp, coordenadas GPS, ID contenedor e ID camión de recolección.
  - Permitir subir al personal un audio de comentario al observar daños o mal uso del contenedor.
  - Generar un reporte diario con todos los contenedores reportados fuera de su posición habitual.
  - Permitir buscar el listado de contenedores que poseen peso medido superior al P90 por rango de fechas.

- **[2025-07-17] TikTok (visualización de videos):** Diseñe una arquitectura que asegure la escalabilidad para un sistema con los siguientes requisitos:
  - Recibir user_id, timestamp, video_id y evento (PLAY|STOP|ABORT) para usuarios de TikTok.
  - Consultar la cantidad de usuarios que están actualmente visualizando cualquier video de cierto canal.
  - Consultar los canales con más videos reproducidos durante los últimos 7 días.
  - Consultar los 5 videos más visualizados (por mins. totales de visualización) en un rango de días.
  - Cada 1 hora, enviar *push-notification* a todo usuario que no visualizó videos durante las últimas 24hs.
  - Considere distribución geográfica de la solución y particionamiento de datos.

- **[2025-07-24] Smart TV — canales LG (variante con perfiles):** Diseñe una arquitectura que asegure la escalabilidad para un sistema con los siguientes requisitos:
  - Recibir usuario, timestamp y canal sintonizado por usuarios que poseen Smart TV LG en Arg. y Brasil.
  - Consultar la cantidad de usuarios actualmente sintonizando cierto canal.
  - Consultar los 5 canales más visualizados (por mins. totales de visualización) en un rango de días.
  - Cada 1 hora, por cada usuario que interactuó, realizar un POST a la plataforma de perfiles para actualizar el horario de última conexión.

---

