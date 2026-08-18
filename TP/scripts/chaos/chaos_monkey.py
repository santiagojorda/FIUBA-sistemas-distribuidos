#!/usr/bin/env python3
import time
import random
import sys
import docker
from datetime import datetime

# Lista de servicios críticos que el Chaos Monkey NO debe apagar jamás
# A menos que se pida apagar TODOS (--todos) o se especifique una etapa que los incluya.
# Nota: "gateway" y "rabbitmq" son servicios de infraestructura base para que el test unitario de workers
# pueda correr o reconectar, no son workers stateless. Los watchdogs y actuadores controlan el ciclo de vida.
# Excluimos estos servicios clave de "--todos" para evitar que el test falle por indisponibilidad de RabbitMQ o Gateway muerto permanente.
SERVICIOS_CRITICOS = ["client", "rabbitmq", "actuador"]
SERVICIOS_OPCIONALES = ["gateway", "watchdog"]

def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if msg.startswith('\n'):
        print(f"\n[{timestamp}] {msg[1:]}", flush=True)
    else:
        print(f"[{timestamp}] {msg}", flush=True)

def run_chaos_monkey(segundos=10, filtros=None, matar_todos=False):
    try:
        client = docker.from_env()
    except Exception as e:
        log(f"Error al conectar con Docker: {e}")
        log("Asegúrate de que el daemon de Docker esté corriendo y tengas permisos.")
        sys.exit(1)

    log("=== Chaos Monkey Iniciado ===")
    
    if matar_todos:
        log("MODO DESTRUCTOR: Apagando todos los contenedores activos de inmediato.")
        try:
            contenedores = client.containers.list(filters={"status": "running"})
            # Excluimos cliente por sanidad del test, y también RabbitMQ / Gateway / Watchdogs / Actuadores
            # para no romper el test-todos (que asume que los workers mueren pero la base sigue viva).
            victimas = [
                c for c in contenedores 
                if not (c.name.startswith("client") or any(crit in c.name for crit in SERVICIOS_CRITICOS))
            ]
            if not victimas:
                log("No hay contenedores de workers corriendo para apagar.")
                return
            log(f"Matando a todos los contenedores: {[c.name for c in victimas]}")
            for v in victimas:
                try:
                    v.kill()
                except Exception as e:
                    log(f"Error matando a {v.name}: {e}")
            log("Todos los nodos elegidos fueron derribados.")
        except Exception as e:
            log(f"Error en destructor: {e}")
        return

    log(f"Intervalo fijo de fallas: {segundos}s")
    if filtros:
        log(f"Apuntando solo a contenedores que contengan: {filtros}")
    else:
        log(f"Excluyendo servicios críticos: {SERVICIOS_CRITICOS}")

    try:
        while True:
            log(f"\nSiguiente ataque en {segundos:.1f} segundos...")
            time.sleep(segundos)

            contenedores = []
            for _ in range(3):
                try:
                    client = docker.from_env(timeout=10)
                    contenedores = client.containers.list(filters={"status": "running"})
                    break
                except docker.errors.NotFound:
                    time.sleep(0.1)
                except Exception as e:
                    log(f"Error al listar contenedores: {e}")
                    time.sleep(2)
                    continue

            if filtros:
                workers = [
                    c for c in contenedores
                    if any(f in c.name for f in filtros)
                    and not any(crit in c.name for crit in SERVICIOS_CRITICOS if crit not in filtros)
                ]
            else:
                workers = [
                    c for c in contenedores
                    if not (c.name.startswith("client") or any(crit in c.name for crit in SERVICIOS_CRITICOS))
                ]

            if not workers:
                log("No se encontraron workers activos para derribar.")
                continue

            # Si es por etapa (filtros especificados), matamos todos los de esa etapa de una.
            if filtros:
                log(f"[Chaos Monkey] ATACANDO etapa con filtros: {filtros}. Matando a todos sus nodos activos...")
                for victima in workers:
                    try:
                        victima.kill()
                        log(f"[Chaos Monkey] '{victima.name}' fue derribado.")
                    except Exception as e:
                        log(f"[Chaos Monkey] Error derribando a '{victima.name}': {e}")
            else:
                victima = random.choice(workers)
                metodo = random.choice(["stop", "kill"])
                log(f"[Chaos Monkey] ATACANDO a '{victima.name}' usando método '{metodo}'...")
                try:
                    if metodo == "stop":
                        victima.stop(timeout=2)
                    else:
                        victima.kill()
                    log(f"[Chaos Monkey] '{victima.name}' fue derribado exitosamente.")
                except Exception as e:
                    log(f"[Chaos Monkey] Error derribando a '{victima.name}': {e}")

    except KeyboardInterrupt:
        log("\n=== Chaos Monkey Finalizado ===")

if __name__ == "__main__":
    # Formato esperado de argumentos:
    # Caso 1: [segundos] --todos
    # Caso 2: [segundos] --etapa <prefijo>
    # Caso 3: [segundos] [filtros...]
    args = sys.argv[1:]
    
    # 1. Detectar si hay segundos provistos al principio
    espera_inicial = 0
    segundos_fijos = 10
    
    # Analizamos si los primeros argumentos son números
    nums = []
    while len(args) > 0 and args[0].isdigit():
        nums.append(int(args.pop(0)))
        
    if len(nums) >= 1:
        # Usamos los segundos fijos
        segundos_fijos = nums[0]
        espera_inicial = float(nums[0])
        
    if "--incluir" in args:
        idx = args.index("--incluir")
        args.pop(idx)
        while idx < len(args) and not args[idx].startswith("--"):
            SERVICIOS_OPCIONALES.remove(args.pop(idx))
    SERVICIOS_CRITICOS.extend(SERVICIOS_OPCIONALES)

    # Si se especificó espera_inicial y vienen flags inmediatas (--todos o --etapa), esperamos ese tiempo fijo
    if espera_inicial > 0 and ("--todos" in args or "--etapa" in args):
        log(f"Esperando {segundos_fijos}s antes del crash...")
        time.sleep(espera_inicial)


    try:
        if "--todos" in args:
            log(f"Iniciando loop destructor cada {segundos_fijos}s...")
            while True:
                log("") # Salto de línea para diferenciar ciclos
                # Ejecutamos matar todos
                try:
                    cl = docker.from_env()
                    contenedores = cl.containers.list(filters={"status": "running"})
                    victimas = [
                        c for c in contenedores 
                        if not (c.name.startswith("client") or any(crit in c.name for crit in SERVICIOS_CRITICOS))
                    ]
                    if victimas:
                        log(f"Matando a todos los contenedores activos: {[c.name for c in victimas]}")
                        for v in victimas:
                            try:
                                v.kill()
                            except Exception as e:
                                pass
                    else:
                        log("No hay workers activos para matar.")
                except Exception as e:
                    log(f"Error en destructor loop: {e}")
                time.sleep(segundos_fijos)

        elif "--etapa" in args:
            idx = args.index("--etapa")
            etapa_fija = None
            if idx + 1 < len(args):
                etapa_fija = args[idx+1]

            log(f"Iniciando loop de caída de etapa cada {segundos_fijos}s...")
            while True:
                log("") # Salto de línea para diferenciar ciclos
                etapa = etapa_fija
                try:
                    cl = docker.from_env()
                    contenedores = cl.containers.list(filters={"status": "running"})
                    candidatos = [
                        c for c in contenedores 
                        if not (c.name.startswith("client") or any(crit in c.name for crit in SERVICIOS_CRITICOS))
                    ]
                    
                    if candidatos:
                        # Si no se especificó etapa, elegimos una al azar en cada ciclo de los corriendo
                        if not etapa:
                            nombres_etapas = []
                            for c in candidatos:
                                partes = c.name.split('_')
                                if partes[-1].isdigit() and len(partes) > 1:
                                    prefijo = "_".join(partes[:-1])
                                else:
                                    prefijo = c.name
                                if prefijo not in nombres_etapas:
                                    nombres_etapas.append(prefijo)
                            if nombres_etapas:
                                etapa = random.choice(nombres_etapas)
                        
                        victimas = [c for c in candidatos if etapa in c.name]
                        if victimas:
                            log(f"Matando etapa '{etapa}': {[c.name for c in victimas]}")
                            for v in victimas:
                                try:
                                    v.kill()
                                except Exception as e:
                                    pass
                        else:
                            log(f"No hay workers de la etapa '{etapa}' activos para matar.")
                    else:
                        log("No hay workers activos en el sistema.")
                except Exception as e:
                    log(f"Error en loop de etapa: {e}")
                time.sleep(segundos_fijos)
        else:
            # Formato tradicional: se usan los segundos fijos ya leídos
            filtros = args if len(args) > 0 else None
            run_chaos_monkey(segundos_fijos, filtros)
    except KeyboardInterrupt:
        log("\n=== Chaos Monkey Finalizado ===")

