# Flashcards — Clase 03: Paralelización, Multiprocessors y Nombres

> Formato: pregunta primero, respuesta debajo. Tapá las respuestas y probate.

---

**1. ¿Cuáles son los tres objetivos principales de paralelizar tareas?**

<details>
<summary>Respuesta</summary>

Reducir el tiempo de cómputo de una tarea (latencia), incrementar la cantidad de tareas realizables en paralelo (throughput) y reducir la energía consumida al realizar todas las tareas.
</details>

---

**2. ¿Qué es el "camino crítico" en paralelización?**

<details>
<summary>Respuesta</summary>

Es la máxima longitud de tareas secuenciales a computar. Define el mejor rendimiento posible al realizar un conjunto de tareas, ya que ninguna paralelización puede ir más rápido que esa cadena de dependencias.
</details>

---

**3. ¿Qué establece la Ley de Amdahl y de qué depende el Speedup máximo?**

<details>
<summary>Respuesta</summary>

Establece que el esfuerzo en lograr altas tasas de procesamiento paralelo se desperdicia si no va acompañado de mejoras similares en la fracción secuencial. El Speedup máximo está acotado por la fracción de tiempo no paralelizable, asumiendo que la fracción paralelizable se distribuye uniformemente entre los procesadores.

![Amdahl](../Presentaciones/Resumenes/image-10.png)
</details>

---

**4. ¿En qué se diferencia la Ley de Gustafson de la Ley de Amdahl?**

<details>
<summary>Respuesta</summary>

Gustafson plantea que el Speedup debe medirse escalando el problema a la cantidad de procesadores, no fijando su tamaño. Si el problema crece, el Speedup aumenta ya sea porque la parte serial disminuye proporcionalmente o porque el paralelismo aumenta. A diferencia de Amdahl (tamaño de problema fijo), Gustafson asume que más cómputo disponible se usa para resolver problemas más grandes.
</details>

---

**5. En el Modelo Work-Span, ¿qué representan Work (T₁) y Span (T∞)?**

<details>
<summary>Respuesta</summary>

Work (T₁): tiempo total si el programa se ejecutara de forma completamente serial (un solo hilo). Span (T∞) o camino crítico: tiempo mínimo si se ejecutara con un número infinito de procesadores; representa la secuencia más larga de dependencias entre tareas.
</details>

---

**6. ¿Cuáles son las hipótesis del Modelo Work-Span?**

<details>
<summary>Respuesta</summary>

Paralelismo imperfecto (no todo el trabajo paralelizable se puede ejecutar al mismo tiempo), Greedy scheduling (proceso disponible ⇒ tarea ejecutada), tiempo de acceso a memoria despreciable y tiempo de comunicación entre procesos despreciable.
</details>

---

**7. ¿Entre qué cotas se ubica el Speedup según el modelo Work-Span, y por qué el modelo de Amdahl sobreestima el Speedup?**

<details>
<summary>Respuesta</summary>

El Speedup se acota entre T₁/(T₁/P + T∞) (cota inferior) y min(P, T₁/T∞) (cota superior). Amdahl sobreestima porque asume que la fracción paralelizable se distribuye perfectamente entre los P procesadores, sin considerar las dependencias reales del camino crítico que sí captura Work-Span.

![Amdahl vs Work-Span](../Presentaciones/Resumenes/Clase03_imagenes/pag-12.png)
</details>

---

**8. Diferenciá Descomposición Funcional de Particionamiento de Datos como estrategias de particionamiento.**

<details>
<summary>Respuesta</summary>

Descomposición Funcional: divide el problema en funciones independientes que se ejecutan en paralelo (ej. `f(data)`, `g(data)`, `h(data)` cada una en su propio proceso). Particionamiento de Datos: divide los datos de entrada entre procesos que ejecutan la misma función sobre distintos rangos (solo aplica si la función es particionable).
</details>

---

**9. Nombrá los patrones de procesamiento vistos y qué hace cada uno.**

<details>
<summary>Respuesta</summary>

- Fork-Join: un proceso se divide (fork) en tareas paralelas que luego se sincronizan (join).
- Pack/Split: reorganización de datos filtrando o separando elementos según una condición.
- Pipeline: tareas encadenadas donde la salida de una etapa alimenta la siguiente, permitiendo solapamiento.
- Map: aplica la misma operación a cada elemento de un conjunto de datos en paralelo.
- Reduction: combina múltiples elementos en un único resultado de forma jerárquica/paralela.

![Patrones de procesamiento](../Presentaciones/Resumenes/Clase03_imagenes/pag-15.png)
</details>

---

**10. ¿Qué clasifica la Taxonomía de Flynn y cuáles son sus cuatro categorías?**

<details>
<summary>Respuesta</summary>

Clasifica sistemas según la cardinalidad de flujos de instrucciones (procesadores) y flujos de datos (memoria): SISD (single instruction, single data — un procesador sin paralelismo), SIMD (array processors, ej. GPU), MISD (poco usual: redundant computation, data-pipelines) y MIMD (múltiples instrucciones, múltiples datos).
</details>

---

**11. Dentro de MIMD, ¿qué diferencia a Multiprocessors de Multicomputers?**

<details>
<summary>Respuesta</summary>

Multiprocessors: comparten memoria y/o clock. Multicomputers: no comparten memoria ni clock, cada computadora tiene su propia memoria local, puede fallar independientemente y requiere comunicación por red (LAN, MAN, WAN).
</details>

---

**12. Diferenciá Symmetric Multiprocessing de Asymmetric Multiprocessing.**

<details>
<summary>Respuesta</summary>

Symmetric: todos los procesadores acceden por igual al bus compartido con la memoria y dispositivos de I/O. Asymmetric: existe una jerarquía/bridge entre procesadores, no todos tienen el mismo nivel de acceso directo a la memoria principal.

![Symmetric vs Asymmetric Multiprocessing](../Presentaciones/Resumenes/Clase03_imagenes/pag-22.png)
</details>

---

**13. ¿Qué diferencia a UMA de NUMA?**

<details>
<summary>Respuesta</summary>

UMA (Uniform Memory Access): el tiempo de acceso a memoria es idéntico para todos los procesadores, con ancho de banda compartido y performance balanceada para uso general. NUMA (Non Uniform Memory Access): cada CPU controla un bloque de memoria local (home agent), logrando mayor ancho de banda si se respeta el acceso a memoria local; ideado en SGI, presente en Linux kernel y MS Servers.

![NUMA](../Presentaciones/Resumenes/Clase03_imagenes/pag-24.png)
</details>

---

**14. ¿Qué son los "Nombres" en un sistema distribuido y qué propiedad clave tienen respecto a las direcciones?**

<details>
<summary>Respuesta</summary>

Permiten identificar unívocamente a una entidad dentro de un sistema, deben describirla, y la abstraen de las propiedades que la atan al sistema (lugar geográfico, direcciones de red). A diferencia de la dirección (que puede cambiar y ser reutilizada), el nombre en general no cambia.
</details>

---

**15. ¿Qué es el Direccionamiento (Addressing)?**

<details>
<summary>Respuesta</summary>

Es el mapeo entre un nombre y una dirección. La dirección de una entidad puede cambiar aunque el nombre se mantenga, y una misma dirección puede ser reutilizada por distintas entidades a lo largo del tiempo.
</details>

---

**16. Dá tres ejemplos de mapeo nombre → dirección y su protocolo/mecanismo de resolución.**

<details>
<summary>Respuesta</summary>

- Domain Name → IP Address: resuelto mediante DNS.
- IP Address → Ethernet Address: resuelto mediante ARP (IPv4) o ND/Neighbor Discovery (IPv6).
- Service (nombre) → Instances (dirección): resuelto mediante Service Discovery (implementaciones: Zookeeper, Istio, Linkerd).
</details>

---

**17. ¿Cómo se organiza jerárquicamente el DNS?**

<details>
<summary>Respuesta</summary>

En zonas, desde el nivel raíz (Top Level `"."`) hacia dominios (`.com`, `.net`, `.edu`, `.org`, `.info`) y subdominios dentro de estos (ej. `.duke`, `.unc`, `.ncsu` dentro de `.edu`). Se puede explorar con el comando `dig fi.uba.ar. @8.8.8.8 +trace`.

![Árbol jerárquico de zonas DNS](../Presentaciones/Resumenes/Clase03_imagenes/pag-29.png)
</details>

---

**18. ¿Cómo funciona el Service Discovery?**

<details>
<summary>Respuesta</summary>

Las Service Instances se registran (Register) en el Service Registry. El Client consulta (Discover) al Service Registry para obtener una instancia disponible del servicio que necesita, resolviendo así el nombre del servicio a una dirección concreta.

![Service Discovery](../Presentaciones/Resumenes/Clase03_imagenes/pag-30.png)
</details>

---
