"""Informe del estado de la campaña y hoja de ayuntamientos MANUAL (datos/manuales.xlsx)."""

from __future__ import annotations

from collections import Counter

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from comun import RAIZ, rellenar_plantilla
from hoja import ENVIADO, MANUAL, REVISAR, VIA_MANUAL, VIA_REC, HojaControl

RUTA_MANUALES = RAIZ / "datos" / "manuales.xlsx"


def plataformas_con_adaptador() -> set[str]:
    from sedes import flujos_sede

    try:
        return set(flujos_sede())
    except Exception:
        return set()


def es_manual(fila: dict, con_adaptador: set[str]) -> bool:
    via = fila.get("via") or ""
    if fila.get("estado") == ENVIADO:
        return False
    if fila.get("estado") == MANUAL or via == VIA_MANUAL:
        return True
    return bool(via) and via != VIA_REC and via not in con_adaptador


def generar_manuales(hoja: HojaControl, config: dict) -> int:
    con_adaptador = plataformas_con_adaptador()
    filas = [f for f in hoja.ordenadas() if es_manual(f, con_adaptador)]
    libro = Workbook()
    h = libro.active
    h.title = "manuales"
    cabecera = ["dir3_ayto", "municipio", "via", "url_sede", "asunto", "expone", "solicita",
                "adjuntos", "num_registro", "fecha_envio"]
    h.append(cabecera)
    docs = config["documentos"]
    for f in filas:
        textos = {c: " ".join(rellenar_plantilla(config["textos"][c], {"municipio": f["municipio"]}).split())
                  for c in ("asunto", "expone", "solicita")}
        if docs.get("carta_personalizada"):
            carta = f"documentos/personalizadas/carta_{f['dir3_ayto']}.pdf"
        else:
            carta = docs["carta"]
        h.append([f["dir3_ayto"], f["municipio"], f.get("via"), f.get("url_sede"), textos["asunto"],
                  textos["expone"], textos["solicita"], f"{carta} + {docs['dossier']}", "", ""])
    for celda in h[1]:
        celda.font = Font(bold=True)
    for col, ancho in zip("ABCDEFGHIJ", (12, 26, 14, 40, 50, 60, 60, 40, 20, 18)):
        h.column_dimensions[col].width = ancho
    for fila in h.iter_rows(min_row=2):
        for celda in fila:
            celda.alignment = Alignment(wrap_text=True, vertical="top")
    RUTA_MANUALES.parent.mkdir(parents=True, exist_ok=True)
    libro.save(RUTA_MANUALES)
    return len(filas)


def ejecutar(config: dict, log) -> None:
    hoja = HojaControl()
    if not len(hoja):
        raise SystemExit("La hoja de control está vacía: ejecuta antes 'python src/main.py inventario'.")
    total = len(hoja)
    log.info(f"Ayuntamientos en la hoja: {total}")
    log.info("\nPor estado:")
    for estado, n in Counter(f.get("estado") for f in hoja).most_common():
        log.info(f"  {estado:<12} {n:>4}")
    log.info("\nPor vía:")
    for via, n in Counter(f.get("via") or "(sin detectar)" for f in hoja).most_common():
        log.info(f"  {via:<20} {n:>4}")
    revisar = [f for f in hoja if f.get("estado") == REVISAR]
    if revisar:
        log.warning("\nComprobar a mano (estado REVISAR, no se reintentan):")
        for f in revisar:
            log.warning(f"  {f['dir3_ayto']} {f['municipio']}: {f.get('notas')}")
    errores = [f for f in hoja if f.get("estado") == "ERROR"]
    if errores:
        log.info("\nEn ERROR (no firmados):")
        for f in errores:
            log.info(f"  {f['dir3_ayto']} {f['municipio']}: {f.get('notas')}")
    n = generar_manuales(hoja, config)
    log.info(f"\n{n} ayuntamientos para presentar a mano en {RUTA_MANUALES}")
    log.info("Al terminar cada uno: python src/main.py marcar <dir3> --estado ENVIADO --num <registro>")
