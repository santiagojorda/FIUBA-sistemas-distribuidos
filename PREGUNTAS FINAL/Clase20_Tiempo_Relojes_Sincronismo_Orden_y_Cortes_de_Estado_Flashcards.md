# Flashcards — Clase 20: Tiempo, Relojes, Sincronismo, Orden y Cortes de Estado

> Formato: pregunta primero, respuesta debajo. Tapá las respuestas y probate.

---

**1. ¿Qué es el efecto de *drift* en los relojes físicos y cómo se corrige?**

<details>
<summary>Respuesta</summary>

Es la descalibración de un reloj físico causada por cambios de temperatura, presión y humedad, que hace que los relojes no sean confiables para compararse entre sí. Por eso hay que sincronizarlos periódicamente: medir el desvío respecto de un reloj de referencia (UTC, GPS, etc.) y aplicar una corrección o compensación lineal cambiando la frecuencia del reloj local, nunca atrasándolo de golpe.

![Drift: reloj adelantado, ideal y atrasado respecto de la referencia](../Presentaciones/Resumenes/Clase20_imagenes/pag-08.png)
</details>

---

**2. Diferenciá las referencias globales de tiempo GMT, UTC, GPS time y TAI.**

<details>
<summary>Respuesta</summary>

GMT (Greenwich Mean Time): basado en el tiempo de rotación terrestre (tiempo astronómico). UTC (Universal Time Coordinated): basado en relojes atómicos, con diferencia de +/-1 segundo respecto del GMT y ajustes periódicos. GPS time: basado en relojes atómicos en la Tierra, no recibe ajustes pero permite ajustar satélites. TAI (Temps Atomique International): 200 relojes atómicos en 70 países, no recibe ajustes astronómicos.

![Referencias globales de tiempo (GMT, UTC, GPS, TAI)](../Presentaciones/Resumenes/Clase20_imagenes/pag-07.png)
</details>

---

**3. Describí el Algoritmo de Cristian para sincronización de tiempo y su fórmula.**

<details>
<summary>Respuesta</summary>

Realiza una compensación del delay de red al obtener la medida de tiempo. El cliente envía un request en T0 y recibe la respuesta en T1; asumiendo delays de red constantes y sin tiempo de procesamiento, el nuevo tiempo se calcula como `T_new = T_server + (T1 - T0) / 2`.

![Algoritmo de Cristian](../Presentaciones/Resumenes/Clase20_imagenes/pag-09.png)
</details>

---

**4. ¿Cómo se organiza NTP (Network Time Protocol) en estratos (stratums)?**

<details>
<summary>Respuesta</summary>

Estrato 0: master clocks. Estrato 1: servidores conectados directamente a master clocks. Estrato 2: servidores sincronizados con servidores en estrato 1. Estrato N: servidores sincronizados con servidores en estrato N-1. Los servidores del mismo estrato pueden sincronizarse entre sí mediante conexiones peer-to-peer, con mensajes enviados de forma no confiable (UDP puerto 123).

![NTP - estructura de servidores por estratos](../Presentaciones/Resumenes/Clase20_imagenes/pag-11.png)
</details>

---

**5. Nombrá los tres modos de sincronización de NTP.**

<details>
<summary>Respuesta</summary>

Multicast/broadcast: usado en LANs de alta velocidad, eficiente pero de baja precisión. Cliente-Servidor (RPC): grupos de aplicaciones se conectan formando un grupo, sin sincronizarse entre sí. Simétrico (Peer Mode): peers sincronizados entre sí para proveer backup mutuo, utilizado en estratos 1 y 2.
</details>

---

**6. Definí la relación "ocurre antes" (happened before) entre eventos.**

<details>
<summary>Respuesta</summary>

a → b si a y b pertenecen al mismo proceso P<sub>i</sub> y a ocurre antes que b. a → b si a es un evento de P<sub>i</sub>, b es un evento de P<sub>j</sub>, a es el envío de un mensaje m a P<sub>j</sub> y b es la recepción de m desde P<sub>i</sub>. Además vale la transitividad: si a → b y b → c, entonces a → c.
</details>

---

**7. ¿Qué es un reloj lógico y qué propiedad debe garantizar respecto de la relación "ocurre antes"?**

<details>
<summary>Respuesta</summary>

Dado S (el conjunto de todos los estados locales posibles del sistema) y → la relación 'ocurre antes', un reloj lógico es una función C monotónica creciente que mapea estados con un número Natural y garantiza: ∀ s,t ∈ S: s → t ⇒ C(s) < C(t).
</details>

---

**8. Describí el Algoritmo de Lamport: cómo se actualiza el contador en un send event, un receive event y un internal event.**

<details>
<summary>Respuesta</summary>

Cada proceso P<sub>i</sub> mantiene un contador `c`. Send event (s, send, t): se incluye `t.c` en el mensaje enviado, y `t.c := s.c + 1`. Receive event (s, receive(u), t): al recibir un mensaje de u, `t.c := max(s.c, u.c) + 1`. Internal event (s, internal, t): `t.c := s.c + 1`.

![Algoritmo de Lamport - ejemplo de ejecución entre dos procesos](../Presentaciones/Resumenes/Clase20_imagenes/pag-16.png)
</details>

---

**9. ¿Cuál es el principal inconveniente de los relojes de Lamport y qué sí se puede detectar con ellos?**

<details>
<summary>Respuesta</summary>

Garantizan `s → t ⇒ C(s) < C(t)`, pero no a la inversa: `C(s) < C(t)` no implica `s → t`, ya que capturan muy poca información al almacenar un único escalar. Sin embargo, sí permiten detectar eventos paralelos (concurrentes): cuando ni `C(s) < C(t)` ni `C(t) < C(s)` se cumplen, ninguno de los eventos ocurre antes que el otro (`s || t`).

![Relojes de Lamport - inconveniente: C(s)<C(t) no implica causalidad](../Presentaciones/Resumenes/Clase20_imagenes/pag-17.png)
</details>

---

**10. ¿En qué se diferencia un Vector de Relojes (Vector Clocks) de un reloj de Lamport?**

<details>
<summary>Respuesta</summary>

Un vector de relojes mapea todo estado del sistema (con k procesos) a un vector de k números Naturales, y garantiza `s → t ⇔ s.v < t.v` (una equivalencia, no solo una implicación como en Lamport). Esto permite determinar con certeza si existe relación causal entre dos eventos comparando componente a componente, y también detectar concurrencia cuando ningún vector domina completamente al otro.

![Vector de relojes - pseudocódigo e implementación](../Presentaciones/Resumenes/Clase20_imagenes/pag-21.png)
</details>

---

**11. Diferenciá los algoritmos/protocolos Sincrónico, Parcialmente sincrónico y Asincrónico en sistemas distribuidos.**

<details>
<summary>Respuesta</summary>

Sincrónico: la entrega de un mensaje posee un timeout conocido. Parcialmente sincrónico: la entrega no posee un timeout conocido, o el mismo es variable. Asincrónico: la entrega de un mensaje no posee timeout asociado.
</details>

---

**12. Definí Steadiness (σ) y Tightness (τ) en el contexto de sincronismo.**

<details>
<summary>Respuesta</summary>

Steadiness (σ): máxima diferencia entre el mínimo y máximo tiempo de delivery de cualquier mensaje recibido por un proceso, definiendo qué tan constante es la recepción de mensajes (`σ = max(T_Dmax - T_Dmin)`). Tightness (τ): máxima diferencia entre los tiempos de delivery de un mismo mensaje m entre distintos procesos, definiendo la simultaneidad con la que un mensaje es recibido por múltiples procesos.

![Sincronismo - steadiness y tightness](../Presentaciones/Resumenes/Clase20_imagenes/pag-27.png)
</details>

---

**13. ¿Qué es la hold-back queue y para qué se usa en el delivery de mensajes?**

<details>
<summary>Respuesta</summary>

El envío de un mensaje no es lo mismo que su delivery (procesar el mensaje, provocando cambios en el estado del proceso). Los mensajes se mantienen en una cola (hold-back queue) que permite controlar el momento en que se libera el mensaje hacia la cola de delivery, permitiendo demorarlo o incluso reordenar mensajes.

![Hold-back queue para controlar el delivery de mensajes](../Presentaciones/Resumenes/Clase20_imagenes/pag-33.png)
</details>

---

**14. Diferenciá los cuatro tipos de orden de mensajes: Sincrónico, FIFO, Causal y Total.**

<details>
<summary>Respuesta</summary>

Orden Sincrónico: todo mensaje posee el mismo timestamp tanto en el emisor como en el receptor (transmisión de tiempo nulo). Orden FIFO: todo par de mensajes desde un mismo emisor a un mismo receptor se entrega en el orden en que fueron enviados. Orden Causal: todo mensaje que implique la generación de un nuevo mensaje se entrega manteniendo la secuencia de causalidad, sin importar el receptor. Orden Total: todo par de mensajes entregado a los mismos receptores es recibido en el mismo orden por esos receptores, independientemente del orden de envío o causalidad.

![Orden causal](../Presentaciones/Resumenes/Clase20_imagenes/pag-36.png)
</details>

---

**15. ¿Cuándo se considera consistente un corte (cut) de un sistema distribuido?**

<details>
<summary>Respuesta</summary>

Un corte es consistente si, por cada evento que contiene, también contiene a aquellos eventos que "ocurren antes" que dicho evento: ∀ evento e ∈ C: f→e ⇒ f ∈ C. Es decir, no puede incluir el efecto de un evento sin incluir también su causa.

![Corte consistente vs. inconsistente](../Presentaciones/Resumenes/Clase20_imagenes/pag-44.png)
</details>

---

**16. ¿Cuál es el objetivo del Algoritmo de Chandy & Lamport y qué hipótesis asume?**

<details>
<summary>Respuesta</summary>

El objetivo es obtener snapshots de estados globales consistentes en sistemas distribuidos, almacenando estados de procesos y de canales aunque no hayan ocurrido al mismo tiempo. Hipótesis: los procesos y canales no fallan, los canales son unidireccionales con orden FIFO, el grafo de procesos es fuertemente conexo, y cada proceso puede iniciar un snapshot en cualquier momento.
</details>

---

**17. Describí las reglas de Envío y Recepción de Marcador en el Algoritmo de Chandy & Lamport.**

<details>
<summary>Respuesta</summary>

Envío de Marcador: al almacenar su estado local en `corte_i`, el proceso envía un Marcador por todos sus canales de salida. Recepción de Marcador: al recibir un Marcador, si el proceso P<sub>i</sub> aún no grabó su estado, lo graba (`corte_i := estado de P_i`) y activa el registro de mensajes entrantes por ese canal; si ya lo había grabado, agrega los mensajes recibidos por ese canal antes del marcador al corte y deja de registrar ese canal.

![Algoritmo de Chandy & Lamport - marcadores y snapshot de canales](../Presentaciones/Resumenes/Clase20_imagenes/pag-46.png)
</details>

---

**18. ¿Qué tres propiedades debe garantizar una comunicación Reliable (Confiable), y qué desafío adicional surge en la comunicación Uno a Muchos?**

<details>
<summary>Respuesta</summary>

Debe garantizar integridad, validez y atomicidad en el delivery de mensajes. En comunicación Uno a uno es trivial de lograr con protocolos sobre TCP/IP y una red segura. En comunicación Uno a Muchos (grupal), el grupo debe proveer las 3 propiedades; bajo TCP/IP la atomicidad requiere atención especial, y además debe definirse el orden entre mensajes garantizado (FIFO, causal, total, etc.) según las necesidades de la aplicación.
</details>

---
