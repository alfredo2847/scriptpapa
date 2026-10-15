"""Utilidades comunes: rutas, configuración, registro y normalización de nombres."""

from __future__ import annotations

import copy
import logging
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent

# Código DIR3 de un ayuntamiento de la provincia de Valencia:
# L01 (ayuntamiento) + 46 (Valencia) + 3 dígitos del municipio INE + 1 dígito de control.
PATRON_AYTO_VALENCIA = re.compile(r"^L0146\d{4}$")
PATRON_CODIGO_DIR3 = re.compile(r"\b[A-Z][A-Z0-9]\d{7}\b")

CONFIG_POR_DEFECTO = {
    "interesado": {
        "tipo": "sociedad",
        "razon_social": "",
        "cif": "",
        "direccion": "",
        "email": "",
        "telefono": "",
    },
    "textos": {"asunto": "", "expone": "", "solicita": ""},
    "documentos": {
        "carta": "documentos/carta.pdf",
        "dossier": "documentos/dossier.pdf",
        "carta_personalizada": False,
        "plantilla_carta": "documentos/plantilla_carta.txt",
        "tamano_max_mb": 5,
    },
    "ejecucion": {
        "max_por_tanda": 5,
        "espera_firma_seg": 300,
        "pausa_entre_envios_seg": [20, 45],
        "confirmar_por_consola": True,
        "max_errores_seguidos": 3,
        "timeout_pantalla_seg": 20,
        "timeout_accion_seg": 15,
    },
    "inventario": {
        "url_dir3": "",
        "total_esperado": 266,
        "columnas": {},
        "url_poblacion": "",
        "prioridad": {"umbral_1": 10000, "umbral_2": 3000},
    },
    "deteccion": {
        "hilos": 6,
        "timeout_http_seg": 10,
        "min_ayuntamientos_adaptador": 10,
    },
    "rec": {"url_inicio": "https://rec.redsara.es/"},
    "navegador": {"canal": "chrome", "headless": False},
}


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
    with open(ruta, encoding="utf-8") as f:
        datos = yaml.safe_load(f) or {}
    return _mezclar(CONFIG_POR_DEFECTO, datos)


def ruta_proyecto(relativa: str | Path) -> Path:
    ruta = Path(relativa)
    return ruta if ruta.is_absolute() else RAIZ / ruta


def ahora_texto() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def marca_tiempo() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def configurar_log(nombre: str = "bot") -> logging.Logger:
    """Registro en consola y en logs/<nombre>_<fecha>.log (hora, municipio y resultado)."""
    carpeta = RAIZ / "logs"
    carpeta.mkdir(exist_ok=True)
    log = logging.getLogger("bot")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    formato = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S")
    fichero = logging.FileHandler(carpeta / f"{nombre}_{datetime.now():%Y%m%d}.log", encoding="utf-8")
    fichero.setFormatter(formato)
    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(fichero)
    log.addHandler(consola)
    return log


# ---------------------------------------------------------------------------
# Normalización de nombres de municipios
# ---------------------------------------------------------------------------

def sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y sin signos: 'L'Eliana' -> 'l eliana'."""
    texto = sin_tildes(str(texto or "")).lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return texto.strip()


PREFIJOS_AYUNTAMIENTO = (
    "ayuntamiento de ",
    "ayuntamiento del ",
    "ajuntament de ",
    "ajuntament del ",
    "ajuntament d'",
    "ajuntament d’",
    "ayuntamiento ",
    "ajuntament ",
)

ARTICULOS = ("el", "la", "los", "las", "els", "les", "l")


def municipio_desde_denominacion(denominacion: str) -> str:
    """'Ayuntamiento de València' -> 'València'."""
    nombre = (denominacion or "").strip()
    minusculas = nombre.lower()
    for prefijo in PREFIJOS_AYUNTAMIENTO:
        if minusculas.startswith(prefijo):
            return nombre[len(prefijo):].strip()
    return nombre


def variantes_municipio(municipio: str) -> list[str]:
    """Formas normalizadas con las que puede aparecer el nombre de un municipio.

    Cubre nombres bilingües ('Alboraya/Alboraia'), artículos pospuestos
    ('Eliana, l'') y la forma sin artículo ('Eliana').
    """
    variantes: list[str] = []
    for parte in re.split(r"\s*/\s*", municipio or ""):
        parte = parte.strip()
        if not parte:
            continue
        coma = re.match(r"^(.*),\s*(el|la|los|las|els|les|l'|l’)$", parte, re.IGNORECASE)
        if coma:
            parte = f"{coma.group(2)} {coma.group(1)}"
        forma = normalizar(parte)
        if forma:
            variantes.append(forma)
        palabras = forma.split()
        if len(palabras) > 1 and palabras[0] in ARTICULOS:
            variantes.append(" ".join(palabras[1:]))
    # sin duplicados y conservando el orden
    return list(dict.fromkeys(v for v in variantes if v))


def contiene_municipio(texto: str, municipio: str) -> bool:
    """True si el texto contiene alguna variante del nombre del municipio, como palabras completas."""
    texto_normal = f" {normalizar(texto)} "
    return any(f" {v} " in texto_normal for v in variantes_municipio(municipio))


def slugs_municipio(municipio: str) -> list[str]:
    """Posibles nombres de dominio: 'L'Eliana' -> ['leliana', 'l-eliana', 'eliana']."""
    slugs: list[str] = []
    for variante in variantes_municipio(municipio):
        palabras = variante.split()
        slugs.append("".join(palabras))
        slugs.append("-".join(palabras))
    return list(dict.fromkeys(s for s in slugs if s))


def nombre_archivo_seguro(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", sin_tildes(texto)).strip("_")


# ---------------------------------------------------------------------------
# Elección de la unidad destinataria
# ---------------------------------------------------------------------------

PALABRAS_FIESTAS = ("fiestas", "festejos", "festes", "fiesta", "festa")
PALABRAS_CULTURA = ("cultura",)


def elegir_unidad(dir3_ayto: str, nombre_ayto: str, unidades: list[tuple[str, str]]) -> tuple[str, str]:
    """Elige destinatario entre las unidades de un ayuntamiento.

    1. Una unidad cuyo nombre contenga Fiestas, Festejos o Festes.
    2. Si no, una de Cultura.
    3. Si no, el ayuntamiento en general.

    `unidades` es una lista de (codigo, nombre) de unidades del ayuntamiento
    (puede incluir al propio ayuntamiento).
    """
    def busca(palabras):
        for codigo, nombre in unidades:
            if codigo == dir3_ayto:
                continue
            palabras_nombre = normalizar(nombre).split()
            if any(p in palabras_nombre for p in palabras):
                return codigo, nombre
        return None

    return busca(PALABRAS_FIESTAS) or busca(PALABRAS_CULTURA) or (dir3_ayto, nombre_ayto)


def rellenar_plantilla(texto: str, contexto: dict) -> str:
    """Sustituye {campos}. Un campo inexistente es un error, nunca se deja en blanco."""
    try:
        return str(texto).format_map(contexto)
    except KeyError as e:
        raise KeyError(f"La plantilla usa el campo {e} que no existe. Texto: {texto!r}") from None
