"""Utilidades comunes: configuración, textos, avisos y guardado de hojas.

Esta herramienta es independiente del bot de registro: no lee ni escribe nada
de la carpeta bot-registro/.
"""

from __future__ import annotations

import copy
import logging
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import yaml

VERSION = "2026-11-01 (solo paellas, Comunitat Valenciana)"

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"
DESCARGAS = DATOS / "descargas"
LOGS = RAIZ / "logs"

BASE_PLACSP = "https://contrataciondelsectorpublico.gob.es/sindicacion"

# Valores por defecto. config.yaml solo necesita lo que quieras cambiar.
DEFAULTS: dict = {
    # Comunitat Valenciana: 46 Valencia, 03 Alicante, 12 Castellón
    "provincias": ["46", "03", "12"],
    "fuentes": {
        "licitaciones": f"{BASE_PLACSP}/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom",
        "agregadas": f"{BASE_PLACSP}/sindicacion_1044/PlataformasAgregadasSinMenores.atom",
        "menores": f"{BASE_PLACSP}/sindicacion_1143/contratosMenoresPerfilesContratantes.atom",
    },
    # true: solo licitaciones que hablan de paellas (nada de catering ni comidas genéricas)
    "solo_paellas": True,
    "palabras": {
        # Con solo_paellas, únicamente cuentan estas (valen también plurales: paellas, paelleros...)
        "paella": [
            "paella", "paelles", "paellada", "paellades", "paellera", "paeller",
            "arroz gigante", "arroces gigantes", "arros gegant", "arrossos gegants",
        ],
        # Basta una para que el contrato sea de encaje "Alto"
        "seguras": [
            "paella", "paelles", "paellada", "arroz gigante", "arros gegant",
            "comida popular", "comidas populares", "dinar popular", "dinars populars",
            "sopar popular", "sopars populars", "comida de hermandad", "dinar de germanor",
            "sopar de germanor", "comida de convivencia",
        ],
        # Una de fiesta + una de comida = encaje "Medio"
        "fiesta": [
            "fiesta", "fiestas", "festes", "festa", "festividad", "festival", "fira", "firas",
            "feria", "ferias", "falla", "fallas", "falles", "moros y cristianos", "moros i cristians",
            "patronal", "patronales", "verbena", "semana cultural", "setmana cultural",
            "porrat", "aniversario", "dia del municipio", "evento", "eventos", "esdeveniment",
        ],
        "comida": [
            "comida", "comidas", "dinar", "dinars", "sopar", "sopars", "cena", "cenas",
            "almuerzo", "almuerzos", "esmorzar", "catering", "degustacion", "degustacio",
            "arroz", "arros", "gastronomic", "gastronomica", "gastronomia", "menu", "menus",
            "manutencion", "avituallamiento",
        ],
        # Descartan el contrato salvo que tenga una palabra "segura"
        "excluir": [
            "comedor escolar", "comedores escolares", "menjador", "menjadors", "escolar",
            "escoleta", "escuela infantil", "escuelas infantiles", "guarderia", "residencia",
            "centro de dia", "centre de dia", "ayuda a domicilio", "comida a domicilio",
            "comidas a domicilio", "teleasistencia", "hospital", "cocina central",
            "penitenciario", "comisaria", "vending", "maquinas expendedoras",
        ],
    },
    # Prefijos de CPV de servicios de comidas y de organización de eventos
    "cpv_comida": ["553", "555"],
    "cpv_eventos": ["7995"],
    # Búsqueda automática (buscar --programada, la que lanza la tarea de Windows):
    # cada día en los meses de temporada y una vez por semana el resto del año.
    "temporada": {
        "meses": [2, 3, 4, 5, 6, 7, 8, 9],   # febrero a septiembre
        "dias_fuera_de_temporada": 7,
    },
    "buscar": {
        "dias_primera_vez": 30,     # cuántos días atrás mira la primera vez
        "solape_dias": 2,           # repaso de seguridad sobre la última búsqueda
        "max_paginas": 400,         # páginas de 500 entradas por fuente, como máximo
        "aviso_dias_plazo": 3,      # recordatorio de las ME INTERESA que vencen pronto
        "incluir_dudosos": True,
    },
    "fichas": {
        "encajes": ["Alto", "Medio"],   # qué licitaciones tienen carpeta propia
        "importe_minimo": 1500,         # por debajo, la valoración no suma por importe
        "importe_maximo": 100000,       # por encima, suma menos (pide más solvencia)
        "descargar_pliegos": True,
    },
    "compradores": {
        "anos": 3,
        # menores: contratos menores; licitaciones y agregadas: licitaciones pasadas.
        # Con las tres salen tres documentos: menores, licitaciones y conjunto.
        "fuentes": ["menores", "licitaciones", "agregadas"],
        "meses_antelacion": 2,      # enviar la propuesta N meses antes del mes en que contratan
    },
    "red": {"timeout_seg": 120, "reintentos": 3},
}

# Código NUTS de la Comunitat Valenciana entera (contratos de la Generalitat sin provincia concreta)
NUTS_COMUNITAT = "ES52"

PROVINCIAS = {
    "46": {"nuts": "ES523", "nombre": "Valencia"},
    "03": {"nuts": "ES521", "nombre": "Alicante"},
    "12": {"nuts": "ES522", "nombre": "Castellón"},
}

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _mezclar(base: dict, extra: dict) -> dict:
    resultado = copy.deepcopy(base)
    for clave, valor in (extra or {}).items():
        if isinstance(valor, dict) and isinstance(resultado.get(clave), dict):
            resultado[clave] = _mezclar(resultado[clave], valor)
        else:
            resultado[clave] = valor
    return resultado


def cargar_config(ruta: Path | None = None) -> dict:
    ruta = ruta or RAIZ / "config.yaml"
    extra = {}
    if ruta.exists():
        extra = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    config = _mezclar(DEFAULTS, extra)
    config["provincias"] = [str(p).zfill(2) for p in config["provincias"]]
    for p in config["provincias"]:
        if p not in PROVINCIAS:
            raise ValueError(f"Provincia desconocida en config.yaml: {p} (usa 46, 03 o 12)")
    return config


def configurar_log(nombre: str) -> logging.Logger:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("vigilante")
    if not log.handlers:
        log.setLevel(logging.INFO)
        archivo = logging.FileHandler(LOGS / f"{nombre}_{datetime.now():%Y%m%d}.log", encoding="utf-8")
        archivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        consola = logging.StreamHandler(sys.stdout)
        consola.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(archivo)
        log.addHandler(consola)
    return log


# ---------------------------------------------------------------------------
# Textos

def sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y sin signos: 'Dinar de Germanor!' -> 'dinar de germanor'."""
    texto = sin_tildes(str(texto or "")).lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return texto.strip()


_AYUNTAMIENTO = re.compile(r"\b(?:ayuntamiento|ajuntament)\s+(?:de\s+|del\s+|d['’]\s*)?(.+)$", re.I)


def municipio_desde_nombre(nombre: str) -> str:
    """'Alcaldía del Ayuntamiento de Sueca' -> 'Sueca'. Vacío si no es un ayuntamiento."""
    m = _AYUNTAMIENTO.search((nombre or "").strip())
    if not m:
        return ""
    municipio = m.group(1).strip(" .,-")
    return municipio[:1].upper() + municipio[1:]


# ---------------------------------------------------------------------------
# Avisos

def avisar(titulo: str, mensaje: str) -> None:
    """Notificación de Windows (en otros sistemas, solo consola)."""
    print(f"\n*** {titulo}: {mensaje} ***\n")
    if sys.platform != "win32":
        return
    titulo_ps = titulo.replace("'", "''")
    mensaje_ps = mensaje[:250].replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; $n.Icon = [System.Drawing.SystemIcons]::Information; "
        f"$n.BalloonTipTitle = '{titulo_ps}'; $n.BalloonTipText = '{mensaje_ps}'; $n.Visible = $true; "
        "$n.ShowBalloonTip(15000); Start-Sleep -Seconds 15; $n.Dispose()"
    )
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Hojas

def guardar_libro(libro, ruta: Path, intentos: int = 60) -> None:
    """Guarda el libro; si está abierto en Excel, espera a que se cierre."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f"~tmp_{ruta.name}")
    libro.save(temporal)
    for intento in range(intentos):
        try:
            temporal.replace(ruta)
            return
        except PermissionError:
            if intento == 0:
                print(f"\n*** No se puede guardar {ruta.name}: ¿está abierto en Excel? "
                      "Ciérralo; se reintenta cada 10 s. ***")
            time.sleep(10)
    raise PermissionError(f"No se pudo guardar {ruta}. Los datos están en {temporal}")
