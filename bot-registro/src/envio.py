"""Bucle de envío (fases 3 y 4): un ayuntamiento cada vez, con todas las salvaguardas.

Para cada ayuntamiento:
  comprobación previa -> apertura -> rellenado -> verificación del resumen
  -> (prueba: PRUEBA_OK y fin) -> confirmación -> REVISAR -> firma -> justificante -> ENVIADO
"""

from __future__ import annotations

import random
from pathlib import Path

from adaptador import Adaptador, contexto_envio
from comun import ruta_proyecto
from hoja import (
    ENVIADO,
    ERROR,
    ESTADOS_BLOQUEADOS,
    MANUAL,
    PENDIENTE,
    PRUEBA_OK,
    REVISAR,
    VIA_REC,
    HojaControl,
)
from motor import DetenerTanda, ErrorAyuntamiento, Flujo, HuellaInvalida, Navegador, hash_huellas
from salvaguardas import (
    ControlParada,
    avisar,
    comprobar_documento,
    confirmar_consola,
    prueba_vigente,
    registrar_prueba_ok,
)


class EnvioNoPermitido(Exception):
    pass


def adjuntos_para(config: dict, fila: dict) -> dict[str, Path]:
    docs = config["documentos"]
    if docs.get("carta_personalizada"):
        from carta import generar_carta

        carta = generar_carta(config, fila)
    else:
        carta = ruta_proyecto(docs["carta"])
    return {"carta": carta, "dossier": ruta_proyecto(docs["dossier"])}


def comprobar_documentos(config: dict) -> None:
    docs = config["documentos"]
    rutas = [ruta_proyecto(docs["dossier"])]
    if docs.get("carta_personalizada"):
        rutas.append(ruta_proyecto(docs["plantilla_carta"]))
    else:
        rutas.append(ruta_proyecto(docs["carta"]))
    problemas = []
    for ruta in rutas:
        if ruta.suffix.lower() == ".pdf":
            problemas += comprobar_documento(ruta, float(docs.get("tamano_max_mb", 5)))
        elif not ruta.exists():
            problemas.append(f"No existe {ruta}")
        elif "[" in ruta.read_text(encoding="utf-8"):
            problemas.append(f"{ruta.name} tiene textos sin completar entre [corchetes]")
    if problemas:
        raise EnvioNoPermitido("Revisa los documentos:\n  - " + "\n  - ".join(problemas))
    textos = config["textos"]
    marcadores = [c for c in ("asunto", "expone", "solicita") if "[" in str(textos.get(c, ""))]
    interesado = config["interesado"]
    opcionales = {"razon_social"} if interesado.get("tipo") == "autonomo" else set()
    marcadores += [c for c, v in interesado.items()
                   if c not in opcionales and ("[" in str(v) or not str(v).strip())]
    if marcadores:
        raise EnvioNoPermitido(f"config.yaml tiene campos sin completar: {marcadores}")
    if "{municipio}" not in textos.get("asunto", ""):
        raise EnvioNoPermitido("El asunto debe contener {municipio} (se verifica en el resumen)")


def cargar_adaptadores(config: dict, log) -> dict[str, tuple[type, Flujo]]:
    """Vías con adaptador verificado: {'REC': (clase, flujo), '<plataforma>': (...)}."""
    from rec import AdaptadorREC, cargar_flujo_rec
    from sedes import clase_adaptador, flujos_sede

    disponibles = {}
    try:
        flujo = cargar_flujo_rec()
        if flujo.verificada:
            disponibles[VIA_REC] = (AdaptadorREC, flujo)
        else:
            log.warning("huellas/rec.yaml no está verificado (verificada: false): no se envía por el REC.")
    except FileNotFoundError:
        log.warning("No existe huellas/rec.yaml")
    for plataforma, flujo in flujos_sede().items():
        disponibles[plataforma] = (clase_adaptador(plataforma), flujo)
    return disponibles


def candidatas(hoja: HojaControl, vias: set[str], maximo: int,
               solo: list[str] | None = None, reintentar_errores: bool = False) -> list[dict]:
    resultado = []
    for fila in hoja.ordenadas():
        estado = fila.get("estado") or PENDIENTE
        if estado in ESTADOS_BLOQUEADOS or estado == MANUAL:
            continue  # nunca se repite un envío
        if estado == ERROR and not reintentar_errores:
            continue
        if fila.get("via") not in vias:
            continue
        if solo and fila["dir3_ayto"] not in solo:
            continue
        resultado.append(fila)
    return resultado[:maximo]


def ejecutar(config: dict, log, prueba: bool, maximo: int | None, confirmar: bool | None,
             solo: list[str] | None = None, reintentar_errores: bool = False, entrada=input) -> dict:
    ejecucion = config["ejecucion"]
    maximo = int(maximo or ejecucion.get("max_por_tanda", 5))
    confirmar = ejecucion.get("confirmar_por_consola", True) if confirmar is None else confirmar

    hoja = HojaControl()
    if not len(hoja):
        raise EnvioNoPermitido("La hoja de control está vacía: ejecuta antes 'inventario' y 'detectar'.")
    comprobar_documentos(config)
    try:
        adaptadores = cargar_adaptadores(config, log)
    except HuellaInvalida as e:
        raise EnvioNoPermitido(f"Huellas inválidas: {e}") from None
    if not adaptadores:
        raise EnvioNoPermitido("No hay ningún adaptador verificado. Completa huellas/rec.yaml con el envío "
                               "manual de referencia (python src/main.py grabar) y pon verificada: true.")
    huellas = hash_huellas()
    if not prueba and not prueba_vigente(huellas):
        raise EnvioNoPermitido("Hay que pasar el modo prueba (--prueba) antes del primer envío real y "
                               "después de cualquier cambio en huellas/.")

    filas = candidatas(hoja, set(adaptadores), maximo, solo, reintentar_errores)
    if not filas:
        log.info("No hay ayuntamientos pendientes con vía disponible.")
        return {}
    copia = hoja.copia_seguridad()
    log.info(f"Copia de la hoja en {copia}")
    modo = "PRUEBA (no se firma nada)" if prueba else "REAL"
    log.info(f"Tanda {modo}: {len(filas)} ayuntamientos. Para parar: crea un archivo STOP o pulsa Ctrl+C.")

    parada = ControlParada().instalar()
    navegador = Navegador(config)
    instancias: dict[str, Adaptador] = {}
    resultados = {"PRUEBA_OK": 0, "ENVIADO": 0, "ERROR": 0, "OMITIDO": 0}
    errores_seguidos = 0
    max_errores = int(ejecucion.get("max_errores_seguidos", 3))
    pausa = ejecucion.get("pausa_entre_envios_seg", [20, 45])
    try:
        for n, fila in enumerate(filas, start=1):
            if parada.debe_parar():
                log.info("Parada solicitada: fin de la tanda.")
                break
            via = fila["via"]
            if via not in instancias:
                clase, flujo = adaptadores[via]
                instancias[via] = clase(navegador, flujo, config, log)
            adaptador = instancias[via]
            log.info(f"[{n}/{len(filas)}] {fila['municipio']} ({fila['dir3_ayto']}) por {via}")
            try:
                resultado = procesar(hoja, fila, adaptador, config, log, prueba, confirmar, entrada)
                resultados[resultado] += 1
                errores_seguidos = 0
            except ErrorAyuntamiento as e:
                capturas = adaptador.motor.capturar(f"error_{fila['dir3_ayto']}")
                if fila.get("estado") != REVISAR:
                    fila["estado"] = ERROR
                fila["notas"] = f"{e} | captura: {capturas[0].name if capturas else '-'}"
                hoja.guardar()
                log.error(f"    ERROR (no se ha firmado): {e}")
                resultados["ERROR"] += 1
                errores_seguidos += 1
                if errores_seguidos >= max_errores:
                    avisar("Tanda detenida", f"{errores_seguidos} errores seguidos; revisa capturas/")
                    log.error(f"{errores_seguidos} errores seguidos: se detiene la tanda.")
                    break
            except DetenerTanda as e:
                capturas = adaptador.motor.capturar(f"parada_{fila['dir3_ayto']}")
                if fila.get("estado") != REVISAR:
                    fila["estado"] = ERROR
                fila["notas"] = f"Tanda detenida: {e} | captura: {capturas[0].name if capturas else '-'}"
                hoja.guardar()
                avisar("Tanda detenida", f"{fila['municipio']}: {e}")
                log.error(f"    TANDA DETENIDA: {e}")
                break
            if n < len(filas) and not parada.debe_parar():
                espera = random.uniform(float(pausa[0]), float(pausa[1]))
                log.info(f"    pausa de {espera:.0f} s")
                if not parada.pausa(espera):
                    log.info("Parada solicitada: fin de la tanda.")
                    break
    finally:
        hoja.guardar()
        parada.restaurar()
        try:
            navegador.cerrar()
        except Exception:
            pass

    log.info(f"Resultado de la tanda: {resultados}")
    if prueba and resultados["PRUEBA_OK"] and not resultados["ERROR"]:
        registrar_prueba_ok(huellas, [f["municipio"] for f in filas if f.get("estado") == PRUEBA_OK])
        log.info("Modo prueba superado con estas huellas: ya se puede enviar de verdad (empieza con --max 5 --confirmar).")
    elif prueba:
        log.warning("El modo prueba no se ha superado sin errores: revisa capturas/ antes de enviar.")
    return resultados


def descargar_pendientes(config: dict, log) -> None:
    """Descarga los justificantes de los registros ENVIADO que no lo tienen, desde la página del registro."""
    from comun import nombre_archivo_seguro
    from rec import AdaptadorREC, cargar_flujo_rec

    hoja = HojaControl()
    pendientes = [f for f in hoja if f.get("estado") == ENVIADO and f.get("url_registro")
                  and not (f.get("justificante") and ruta_proyecto(str(f["justificante"])).exists())]
    sin_url = [f for f in hoja if f.get("estado") == ENVIADO and not f.get("url_registro")
               and not (f.get("justificante") and ruta_proyecto(str(f["justificante"])).exists())]
    for f in sin_url:
        log.warning(f"{f['municipio']}: sin dirección del registro guardada; descargar a mano desde 'Mis registros' "
                    f"({f.get('num_registro')})")
    if not pendientes:
        log.info("No hay justificantes pendientes de descargar con dirección guardada.")
        return
    flujo = cargar_flujo_rec()
    navegador = Navegador(config)
    try:
        adaptador = AdaptadorREC(navegador, flujo, config, log)
        motor = adaptador.motor
        cfg = flujo.seccion("justificante")
        for fila in pendientes:
            motor.contexto = {}
            navegador.pagina.goto(fila["url_registro"])
            # si la sesión caducó: los mismos pasos de inicio de sesión que la apertura
            motor.ejecutar_pasos([p for p in flujo.seccion("apertura") if "si_pantalla" in p])
            if not motor.coincide(cfg["pantalla"]):
                navegador.pagina.goto(fila["url_registro"])
            motor.exigir(cfg["pantalla"], 60)
            destino = ruta_proyecto("justificantes") / f"{fila['dir3_ayto']}_{nombre_archivo_seguro(fila['municipio'])}.pdf"
            destino.parent.mkdir(exist_ok=True)
            try:
                adaptador.descargar_justificante(cfg["descargar"], destino)
                fila["justificante"] = str(destino.relative_to(ruta_proyecto(".")))
                fila["notas"] = ""
                hoja.guardar()
                log.info(f"{fila['municipio']}: justificante guardado en {destino}")
            except Exception as e:  # noqa: BLE001
                log.error(f"{fila['municipio']}: no se pudo descargar ({str(e).splitlines()[0]})")
    finally:
        hoja.guardar()
        navegador.cerrar()


def procesar(hoja: HojaControl, fila: dict, adaptador: Adaptador, config: dict, log, prueba: bool,
             confirmar: bool, entrada=input) -> str:
    # 1. Comprobación previa: nunca se repite un envío.
    if fila.get("estado") in ESTADOS_BLOQUEADOS:
        log.info(f"    estado {fila['estado']}: se salta")
        return "OMITIDO"

    dir3 = fila["dir3_ayto"]
    nombre_ayto = f"Ayuntamiento de {fila['municipio']}"
    codigos_validos = {dir3} | {c for c, _ in hoja.unidades_de(dir3)}
    contexto = contexto_envio(config, fila, adjuntos_para(config, fila), codigos_validos, nombre_ayto)

    # 2-6. Acceso, datos, contenido, destinatario y adjuntos.
    adaptador.abrir_instancia_general(contexto)
    adaptador.rellenar(contexto)
    fila["dir3_destino"] = contexto["dir3_destino"]
    fila["nombre_destino"] = contexto["nombre_destino"]
    hoja.guardar()

    # 7. Verificación en el resumen.
    leido, fallos = adaptador.verificar_resumen(fila)
    if fallos:
        adaptador.cancelar()
        raise ErrorAyuntamiento("Verificación del resumen: " + "; ".join(fallos))
    log.info(f"    resumen verificado: {leido.get('destinatario_nombre') or leido.get('cabecera', '')}")

    if prueba:
        fila["estado"] = PRUEBA_OK
        fila["notas"] = "Prueba OK: resumen verificado, no se ha firmado"
        hoja.guardar()
        adaptador.cancelar()
        log.info("    PRUEBA_OK (no se ha firmado)")
        return "PRUEBA_OK"

    if confirmar and not confirmar_consola(fila, entrada):
        fila["notas"] = "Envío no confirmado por consola"
        hoja.guardar()
        adaptador.cancelar()
        log.info("    no confirmado: no se firma")
        return "OMITIDO"

    # 8. Firma: REVISAR justo antes de pulsar, por si el proceso se corta.
    fila["estado"] = REVISAR
    fila["notas"] = "Firma iniciada; si no pasa a ENVIADO, comprobar a mano si el registro entró"
    hoja.guardar()
    try:
        firmado = adaptador.firmar_y_esperar(float(config["ejecucion"].get("espera_firma_seg", 300)))
    except ErrorAyuntamiento as e:
        raise DetenerTanda(f"Fallo al pulsar firmar ({e}); queda en REVISAR") from None
    if not firmado:
        fila["notas"] = "No apareció el justificante a tiempo; comprobar a mano si el registro entró"
        hoja.guardar()
        raise DetenerTanda("No apareció el justificante tras la firma; queda en REVISAR")

    # 9. Justificante.
    try:
        datos = adaptador.guardar_justificante(fila)
    except ErrorAyuntamiento as e:
        fila["notas"] = f"Firmado pero no se pudo leer el justificante ({e}); comprobar a mano"
        hoja.guardar()
        raise DetenerTanda(f"Justificante ilegible; queda en REVISAR: {e}") from None
    if not datos["num_registro"]:
        fila["notas"] = "Pantalla final sin número de registro legible; comprobar a mano"
        hoja.guardar()
        raise DetenerTanda("Justificante sin número de registro; queda en REVISAR")
    fila.update(
        estado=ENVIADO,
        num_registro=datos["num_registro"],
        fecha_envio=datos["fecha_envio"],
        justificante=datos["justificante"],
        notas=datos["aviso"],
        url_registro=datos.get("url_registro", ""),
    )
    hoja.guardar()
    log.info(f"    ENVIADO: registro {datos['num_registro']} ({datos['fecha_envio']}) {datos['aviso']}")
    return "ENVIADO"
