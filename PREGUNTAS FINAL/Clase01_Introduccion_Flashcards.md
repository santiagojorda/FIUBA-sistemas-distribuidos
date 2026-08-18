# Flashcards — Clase 01: Introducción a Sistemas Distribuidos

> Formato: pregunta primero, respuesta debajo. Tapá las respuestas y probate.

---

**1. ¿Por qué la Ley de Moore ya no garantiza mejoras de performance?**

<details>
<summary>Respuesta</summary>

El número de transistores sigue creciendo, pero la frecuencia y el rendimiento por hilo se estancaron desde mediados de los 2000. Por eso la industria recurre a más núcleos (paralelismo) en vez de procesadores individuales más rápidos.

![Tendencias de microprocesadores - 42 años](../Presentaciones/Resumenes/Clase01_imagenes/pag-03.png)
</details>

---

**2. Nombrá las tres arquitecturas de ejemplo vistas en la clase.**

<details>
<summary>Respuesta</summary>

Client-Server (servidor central atiende múltiples clientes), Peer-to-peer (todos los nodos tienen el mismo rol) y Heterogéneas (combinación de distintos tipos de nodos y roles).

![Arquitecturas Client-Server, P2P y Heterogéneas](../Presentaciones/Resumenes/Clase01_imagenes/pag-09.png)
</details>

---

**3. Dale las tres definiciones clásicas de "Sistema Distribuido" y su autor.**

<details>
<summary>Respuesta</summary>

- Tanenbaum: "Colección de computadoras independientes que el usuario ve como un solo sistema coherente".
- Coulouris: "Sistema de computadoras interconectadas por una red que se comunican y coordinan sus acciones intercambiando mensajes".
- Lamport: "Aquel en el que el fallo de un computador que ni siquiera sabés que existe, puede dejar tu propio computador inutilizable".
</details>

---

**4. ¿Cuáles son los parámetros de diseño de un sistema distribuido?**

<details>
<summary>Respuesta</summary>

Transparencia, Acceso a recursos compartidos, Sistemas distribuidos abiertos (Interfaces, Interoperability, Portability), Escalabilidad, Tolerancia a fallos (Availability, Reliability, Safety, Maintainability).
</details>

---

**5. Diferenciá Multi-threading, Multi-processing y Multi-computing.**

<details>
<summary>Respuesta</summary>

- Multi-threading: múltiples hilos comparten una misma memoria.
- Multi-processing: múltiples procesos, cada uno con su propia memoria, dentro de la misma máquina.
- Multi-computing: múltiples computadoras, cada una con su propia memoria, interconectadas — esto es lo propio de los sistemas distribuidos.

![Multi-threading, Multi-processing, Multi-computing](../Presentaciones/Resumenes/Clase01_imagenes/pag-14.png)
</details>

---

**6. ¿Qué diferencia al Modelo de Estados del Modelo de Eventos para analizar sistemas distribuidos?**

<details>
<summary>Respuesta</summary>

- Modelo de Estados (interleaved model): cada proceso transita entre estados mediante transiciones.
- Modelo de Eventos (happened before): analiza la relación causal entre eventos de distintos procesos en el tiempo (ej. un evento en P1 provoca un evento en P2 vía un mensaje).

![Modelo de estados y modelo de eventos](../Presentaciones/Resumenes/Clase01_imagenes/pag-15.png)
</details>

---

**7. ¿Cuál es la diferencia clave entre Paralelismo y Concurrencia?**

<details>
<summary>Respuesta</summary>

Paralelo: cada proceso accede a su propio recurso de forma simultánea e independiente. Concurrente: varios procesos compiten/comparten el acceso al mismo recurso a lo largo del tiempo.

![Paralelo vs Concurrente](../Presentaciones/Resumenes/Clase01_imagenes/pag-16.png)
</details>

---

**8. Nombrá las topologías de comunicación vistas en la clase.**

<details>
<summary>Respuesta</summary>

Bus, Star, Tree, Mesh, Sequential y Ring.

![Topologías: Bus, Star, Tree, Mesh, Sequential, Ring](../Presentaciones/Resumenes/Clase01_imagenes/pag-18.png)
</details>

---

**9. Dá dos ventajas de centralizar y dos ventajas de distribuir un sistema.**

<details>
<summary>Respuesta</summary>

Centralizar: Control (lógica simple y eficiente) y Consistencia (políticas fuertes, monitoreo del estado global) — también Homogeneidad y Seguridad.
Distribuir: Disponibilidad (sigue funcionando ante fallos aislados) y Escalabilidad — también Reducción de latencia, Colaboración, Movilidad y Costo.
</details>

---

**10. ¿Qué establece la Ley de Conway?**

<details>
<summary>Respuesta</summary>

"Cualquier organización que diseñe un sistema, inevitablemente producirá un diseño cuya estructura será una copia de la estructura de comunicación de la organización" (Conway, 1968). Corolario: diseñamos de acuerdo a lo que conocemos y a cómo trabajamos día a día.
</details>

---

**11. ¿Qué es un Hypervisor y qué funciones cumple?**

<details>
<summary>Respuesta</summary>

Es el Virtual Machine Monitor: administra las VMs, emula capacidades de hardware, administra recursos del Host OS hacia los Guest OS e implementa mecanismos de seguridad.
</details>

---

**12. ¿En qué se diferencian las VMs (modelo Hosted) de los Containers?**

<details>
<summary>Respuesta</summary>

En el modelo Hosted, cada aplicación necesita su propio Guest OS completo (más pesado). En Containers, las apps comparten el mismo Host OS (Linux) a través de un Container Engine, siendo mucho más livianos.

![Comparación entre máquinas virtuales (Hosted) y Containers](../Presentaciones/Resumenes/Clase01_imagenes/pag-27.png)
</details>

---

**13. ¿En qué lenguaje está desarrollado Docker y en qué features del kernel de Linux se apoya?**

<details>
<summary>Respuesta</summary>

Docker está desarrollado en Golang (primera versión estable en 2013). Se apoya en cgroups, namespaces y union mount del kernel de Linux.
</details>

---

**14. ¿Qué namespaces de Linux usa Docker para aislar recursos?**

<details>
<summary>Respuesta</summary>

NET (network stack), PID (procesos), MNT (mount), IPC (semáforos, shared memory) y USER (user/group ids).
</details>

---

**15. Distinguí Dockerfile, Image, Container y Volume.**

<details>
<summary>Respuesta</summary>

- Dockerfile: secuencia de comandos que generan una Image (cada comando agrega un layer).
- Image: bloque estático construido a partir de un Dockerfile, reutilizable.
- Container: ejecución de comandos dentro de una Image; comparte el kernel con el Host OS y no provee persistencia por sí mismo.
- Volume: directorio compartido entre el Host OS y el container, necesario para dar persistencia.
</details>

---

**16. ¿Qué es Docker Compose y cómo se configura?**

<details>
<summary>Respuesta</summary>

Es una herramienta incorporada al cliente de Docker (desarrollada originalmente en Python) que administra múltiples containers, con DNS resolution y containers en la misma red por defecto. Se configura mediante archivos YAML.
</details>
