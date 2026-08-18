# Flashcards — Clase 21: Introducción a Sistemas de Tiempo Real

> Formato: pregunta primero, respuesta debajo. Tapá las respuestas y probate.

---

**1. ¿Qué define a un Sistema de Tiempo Real (RT) y cuándo se considera correcto?**

<details>
<summary>Respuesta</summary>

Son sistemas cuya evolución se especifica en términos de requerimientos temporales requeridos por el entorno. La correctitud del sistema depende de que entregue respuestas correctas y en el tiempo correcto. Un sistema es RT si tiene al menos un servicio RT.
</details>

---

**2. Diferenciá Hard RT de Soft RT.**

<details>
<summary>Respuesta</summary>

Hard RT: se debe evitar todo fallo relacionado con el tiempo de delivery; perder un deadline es un fallo total (ej. marcapasos). Soft RT: los fallos relacionados con el tiempo de delivery pueden ser admitidos ocasionalmente (con cierta frecuencia documentada); la utilidad de un resultado disminuye tras el deadline (ej. aeronaves).

![Hard RT (marcapasos) vs Soft RT (aeronave)](../Presentaciones/Resumenes/Clase21_imagenes/pag-04.png)
</details>

---

**3. ¿Por qué se dice que "RT implica previsibilidad, no performance"?**

<details>
<summary>Respuesta</summary>

Porque un sistema veloz pero sin previsibilidad no es RT, mientras que un sistema previsible con tiempos característicos lentos sí lo es. Lo importante es hacer un correcto scheduling para que se cumplan los deadlines previstos por diseño, no la velocidad en sí.
</details>

---

**4. ¿Por qué TCP/IP no es adecuado para comunicación en sistemas RT, y qué alternativas existen?**

<details>
<summary>Respuesta</summary>

RT requiere comunicación fiable y sincrónica con deadlines bien definidos, algo que TCP/IP no permite asegurar. Alternativas: Comunicación Serial (permite control sobre estos aspectos, ej. Profibus) y Ethernet usado en capa física evitando no-determinismos de protocolos superiores, con switching determinístico para colisiones (ej. Profinet).

![Comunicación en automatización industrial](../Presentaciones/Resumenes/Clase21_imagenes/pag-07.png)
</details>

---

**5. Dá un ejemplo de estrategia de Fault Tolerance en Soft RT y en Hard RT.**

<details>
<summary>Respuesta</summary>

Soft RT (ej. sistemas web de gran escala): el 99% de los requests deben responderse en 2 seg, el 1% restante en 10 seg, admitiendo 1 outlier cada 1M de requests. Hard RT (ej. misión crítica): el 100% de los requests debe resolverse en 1 seg; frente a errores se asume un fallo catastrófico y se recomienda hard reset, siendo muy importante revisar el factor de Maintainability.
</details>

---

**6. Diferenciá los paradigmas de trabajo Event-Triggered y Time-Triggered.**

<details>
<summary>Respuesta</summary>

Event-Triggered: el servidor procesa cada evento a medida que el cliente lo envía, respondiendo de forma asincrónica según llegan los requests. Time-Triggered: el procesamiento ocurre en instantes de tiempo predefinidos (slots fijos), independientemente de cuándo llega cada evento.

![Paradigmas de trabajo: Event-Triggered vs Time-Triggered](../Presentaciones/Resumenes/Clase21_imagenes/pag-10.png)
</details>

---

**7. Definí: Control, Proceso, Variable controlada, Variable manipulada, Perturbación, Planta, Controlador y Actuador.**

<details>
<summary>Respuesta</summary>

Control: capacidad de actuar para garantizar el comportamiento de un suceso. Proceso: toda sucesión de operaciones que se desea controlar. Variable controlada: cantidad o condición que se mide o controla (salida del sistema). Variable manipulada: cantidad o condición que se modifica para afectar la variable controlada. Perturbación: señal que afecta negativamente la salida del sistema. Planta: cualquier sistema físico que se desea controlar. Controlador: sistema que determina la actuación para conseguir el objetivo del proceso. Actuador: elemento físico de la planta que opera sobre el proceso frente a señales del controlador.
</details>

---

**8. ¿Cuál es la diferencia entre control a lazo abierto y control a lazo cerrado (feedback)?**

<details>
<summary>Respuesta</summary>

En lazo abierto, la salida del sistema no afecta la acción de control: el Controlador genera una Entrada hacia la Planta sin recibir información de la Salida. En lazo cerrado (feedback), se utiliza información sobre el estado del sistema (la Salida, realimentada) comparándola contra la Referencia para generar una señal de Error que alimenta al Controlador, llevando la salida a los valores deseados.

![Control a lazo cerrado (feedback)](../Presentaciones/Resumenes/Clase21_imagenes/pag-15.png)
</details>

---

**9. ¿Qué dos fallas causaron los reinicios continuos del Mars Pathfinder?**

<details>
<summary>Respuesta</summary>

Un Watchdog que reiniciaba el sistema al perderse el deadline de una tarea crítica, y una Inversión de prioridades: una tarea de alta prioridad era bloqueada indirectamente por una tarea de baja prioridad que retenía un lock, mientras era constantemente desalojada por tareas de prioridad intermedia.

![Mars Pathfinder - inversión de prioridades](../Presentaciones/Resumenes/Clase21_imagenes/pag-17.png)
</details>

---

**10. ¿Qué dos causas de software provocaron las sobredosis de radiación del Therac-25?**

<details>
<summary>Respuesta</summary>

Race Conditions: la interfaz de usuario mostraba un modo erróneo al operador durante el bootstrapping del magnetrón. Overflow: se usaba 1 byte para el contador de errores detectados, que hacía overflow a 0 al detectar 256 chequeos fallidos. Las fallas ya existían en el equipo anterior (Therac-20) pero se manifestaron al eliminar controles por hardware y confiar solo en el software.

![Therac-25 - interfaz del sistema de control](../Presentaciones/Resumenes/Clase21_imagenes/pag-18.png)
</details>

---

**11. ¿Qué dos fallos provocaron la explosión del Ariane 5 en su despegue de 1996?**

<details>
<summary>Respuesta</summary>

Cast Overflow: el algoritmo de navegación (heredado del Ariane 4 sin testing adecuado) asumía la posibilidad de castear valores de 64 bits a variables de 16 bits sin chequear overflow. Error in Redundant Systems: los sistemas redundantes reprodujeron exactamente las mismas condiciones, por lo que ambos fallaron de la misma manera y la redundancia no evitó el desastre.

![Ariane 5 - arquitectura del sistema de navegación](../Presentaciones/Resumenes/Clase21_imagenes/pag-19.png)
</details>

---

**12. ¿Qué ocurrió en el caso Mt. Gox y por qué se lo clasifica como un caso Non-RT?**

<details>
<summary>Respuesta</summary>

En 2011 un glitch en el software de generación de transacciones de Bitcoin introdujo un hash erróneo de la dirección del receptor. Las transacciones de Bitcoin pueden ser incobrables (unredeemable) por definición y no había mecanismo para detectar este tipo de errores, por lo que cerca de 2.500 bitcoins quedaron en transacciones incobrables hasta detectarse el error. Se lo clasifica como Non-RT porque la falla no está relacionada con el cumplimiento de deadlines temporales, sino con la falta de validación/detección de errores en el sistema.

![Mt. Gox - transacción esperada vs. transacción real generada](../Presentaciones/Resumenes/Clase21_imagenes/pag-20.png)
</details>

---
