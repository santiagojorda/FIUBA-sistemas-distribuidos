# Flashcards — Clase 19: Algoritmos de Consenso

> Formato: pregunta primero, respuesta debajo. Tapá las respuestas y probate.

---

**1. ¿Cuáles son las propiedades de Safety y Liveness en el problema de Elección de Líder?**

<details>
<summary>Respuesta</summary>

Safety: un proceso participante P<sub>i</sub> posee el estado *elected<sub>i</sub> = P* (un identificador) o *elected<sub>i</sub> = @* (indefinido), y en ningún momento puede haber más de un líder. Liveness: todos los procesos participan de la elección y bien terminan con un estado *elected<sub>i</sub> != @*, o comienzan una nueva elección de líder.
</details>

---

**2. Describí la lógica del Algoritmo del Anillo para elección de líder cuando un proceso recibe un mensaje de elección.**

<details>
<summary>Respuesta</summary>

Si el proceso está en estado *no participando*: cambia a *participando*, compara el ID recibido con el suyo, lo reemplaza si es mayor, y reenvía el mensaje al siguiente nodo. Si está en estado *participando*: si el ID recibido es menor al suyo, no reenvía el mensaje; si es mayor, lo reenvía; si es igual al suyo, es el líder (se autoproclama al recibir su propio mensaje de vuelta) y envía un mensaje de líder elegido.

![Anillo - condiciones iniciales](../Presentaciones/Resumenes/Clase19_imagenes/pag-05.png)
</details>

---

**3. En el Algoritmo del Anillo, ¿qué ocurre si se inician dos elecciones simultáneas?**

<details>
<summary>Respuesta</summary>

Los mensajes se propagan en paralelo en direcciones opuestas del anillo; cuando los mensajes de mayor y menor ID se cruzan, el mensaje de menor ID es descartado por el proceso con mayor ID. Finalmente, solo el mensaje del proceso con mayor ID completa la vuelta y la elección finaliza correctamente con un único líder.

![Anillo - caso particular: dos elecciones simultáneas](../Presentaciones/Resumenes/Clase19_imagenes/pag-19.png)
</details>

---

**4. Nombrá los tres tipos de mensajes del Bully Algorithm y qué información transmite cada uno.**

<details>
<summary>Respuesta</summary>

Election Message: inicia una elección de líder. Answer Message: ACK de un Election Message. Coordinator Message: informa quién fue el proceso líder elegido.
</details>

---

**5. Describí el algoritmo Bully paso a paso: ¿qué hace un proceso al detectar que el líder está caído, y qué hace si no recibe respuestas?**

<details>
<summary>Respuesta</summary>

Si un proceso detecta que el líder está caído, envía Election Messages a los procesos que tengan un ID mayor al suyo. Si recibe Election Messages de otros, responde con Answer Message y comienza su propia elección. Si tras el timeout `T = 2*Tmax + Tprocess` no recibe Answer Messages, se autoproclama líder y envía un Coordinator Message a todos.

![Bully - P1 detecta que P4 está caído](../Presentaciones/Resumenes/Clase19_imagenes/pag-28.png)
</details>

---

**6. ¿Por qué se llama "Bully" al algoritmo, y qué pasa si el proceso líder original vuelve a la vida?**

<details>
<summary>Respuesta</summary>

Se llama Bully porque el proceso de mayor ID siempre "avasalla" al resto: si un proceso caído vuelve a la vida y comienza una nueva elección, y posee el mayor ID del sistema, será elegido como nuevo líder sin importar quién fuera el líder anterior.

![Bully - P4 vuelve a la vida y se autoproclama líder por tener mayor ID](../Presentaciones/Resumenes/Clase19_imagenes/pag-34.png)
</details>

---

**7. Enunciá las tres propiedades requeridas del problema de Consenso (Agreement, Integrity, Termination).**

<details>
<summary>Respuesta</summary>

Agreement: el valor de la decision variable es el mismo en todos los procesos correctos. Integrity: si los procesos correctos propusieron el mismo valor, entonces el valor de su decision variable es el mismo. Termination: eventualmente todos los procesos activos setean su decision variable. La fórmula de Quorum para mayoría es N >= 2f + 1.
</details>

---

**8. Describí el Algoritmo de Consenso Sincrónico por rondas.**

<details>
<summary>Respuesta</summary>

En cada ronda, cada proceso difunde (broadcast) los nuevos valores que conoce y agrega los valores recibidos de los demás. Tras f+1 rondas (siendo f la cantidad máxima de fallas a tolerar), cada proceso decide aplicando una función de agregación sobre el conjunto de valores acumulado.

![Algoritmo de consenso sincrónico - pseudocódigo](../Presentaciones/Resumenes/Clase19_imagenes/pag-44.png)
</details>

---

**9. Planteá el problema de los Generales Bizantinos: ¿qué actores participan y en qué puede consistir la traición de cada uno?**

<details>
<summary>Respuesta</summary>

Un Comandante envía una orden (Atacar/Retirarse) a dos o más Generales, que deben coordinarse para decidir una acción común. Un General traidor puede informar al resto una orden distinta a la que realmente recibió del comandante. Un Comandante traidor puede enviar órdenes distintas a cada General, generando confusión sobre cuál es la decisión correcta. Un proceso traicionero emula una falla de tipo byzantine (arbitraria).

![Generales Bizantinos - Comandante traidor envía órdenes distintas](../Presentaciones/Resumenes/Clase19_imagenes/pag-50.png)
</details>

---

**10. ¿Cuál es la fórmula de Quorum para el problema de los Generales Bizantinos y en qué se diferencia de la del consenso simple?**

<details>
<summary>Respuesta</summary>

N >= 3f + 1, a diferencia del consenso simple que requería N >= 2f + 1. Esto es porque además de Agreement y Termination, se requiere Integrity (si el comandante no es traicionero, todos los procesos deben setear su decision variable al valor enviado por él), lo cual exige mayor redundancia para distinguir información confiable de maliciosa.
</details>

---

**11. ¿Por qué con N <= 3f (por ejemplo, 3 procesos con 1 traidor) es imposible resolver el problema de los Generales Bizantinos?**

<details>
<summary>Respuesta</summary>

Porque un General correcto no puede distinguir de forma confiable entre dos escenarios: que el Comandante sea honesto pero un General mienta sobre lo que recibió, o que el Comandante mismo sea el traidor y envíe valores distintos a cada General. En ambos casos el General correcto recibe información contradictoria, y ambos escenarios son indistinguibles desde su perspectiva.

![Generales Bizantinos - imposibilidad con N<=3f, escenario 1](../Presentaciones/Resumenes/Clase19_imagenes/pag-53.png)
</details>

---

**12. ¿Cómo resuelve el problema con N >= 3f + 1 (por ejemplo, 4 procesos con 1 traidor)?**

<details>
<summary>Respuesta</summary>

Cada General recibe los valores directamente del Comandante y además los valores que los demás Generales dicen haber recibido del Comandante. Con esta información redundante, cada General puede aplicar una función de mayoría sobre el conjunto de valores recibidos para determinar el valor correcto, incluso en presencia de un traidor.

![Generales Bizantinos - solución con N>=3f+1, intercambio de valores](../Presentaciones/Resumenes/Clase19_imagenes/pag-55.png)
</details>

---

**13. ¿Cuál es el objetivo de Paxos y qué garantiza su fórmula de Quorum N >= 2f + 1?**

<details>
<summary>Respuesta</summary>

El objetivo es consensuar un valor aunque múltiples procesos realicen diferentes propuestas. Es tolerante a fallos: el algoritmo progresa siempre que haya una mayoría de procesos vivos (N >= 2f + 1). El pedido de un cliente puede ser rechazado, pero puede reintentarse las veces que se desee, y Paxos asegura orden consistente en el clúster.
</details>

---

**14. Describí los tres actores de la arquitectura de Paxos: Proposer, Acceptor y Learner.**

<details>
<summary>Respuesta</summary>

Proposer: recibe los requests de los clientes y comienza el protocolo; debe elegirse un Leader entre los Proposers para evitar starvation. Acceptor: recibe los mensajes prepare/propose de los Proposers y mantiene el estado del protocolo en almacenamiento estable; existe Quorum cuando la mayoría de los Acceptors están vivos. Learner: cuando el protocolo llega a un acuerdo, ejecuta el request y envía la respuesta al cliente.

![Paxos - arquitectura general (Proposers, Acceptors, Learners, Quorum)](../Presentaciones/Resumenes/Clase19_imagenes/pag-61.png)
</details>

---

**15. Describí las fases 1a (Prepare) y 1b (Promise) del protocolo Paxos.**

<details>
<summary>Respuesta</summary>

Fase 1a — Prepare: el Proposer crea una propuesta #N (mayor a cualquier propuesta previa suya) y envía `prepare(N)` a los Acceptors, buscando obtener Quorum. Fase 1b — Promise: si el ID recibido es mayor al último recibido, los Acceptors prometen rechazar cualquier request con ID < N y envían `promise(N', v')` de vuelta (con el N previo y el valor asociado si lo hubiera); el Proposer necesita promesas de la mayoría.

![Paxos - Fase 1a: Prepare](../Presentaciones/Resumenes/Clase19_imagenes/pag-64.png)
</details>

---

**16. Describí las fases 2a (Propose), 2b (Accept) y 2c (Accept/respuesta al cliente) del protocolo Paxos.**

<details>
<summary>Respuesta</summary>

Fase 2a — Propose: si el Proposer recibe promesas de la mayoría, rechaza requests con ID < N y envía `propose(N, v)` a los Acceptors. Fase 2b — Accept: si la promesa aún se mantiene (no se recibió un ID superior a N), cada Acceptor anuncia el valor v enviando `accept(N, v)` a todos los Learners y al Proposer original. Fase 2c — Accept: el Learner acepta el valor si recibe la mayoría de los accepts (Quorum), responde al cliente y ejecuta las acciones correspondientes (ej. persistirlo en bases replicadas).

![Paxos - Fase 2c: Accept, respuesta al cliente](../Presentaciones/Resumenes/Clase19_imagenes/pag-68.png)
</details>

---
