"""Qué contratos interesan: zona geográfica y encaje con paellas para fiestas."""

from __future__ import annotations

import re
from functools import lru_cache

from comun import NUTS_COMUNITAT, PROVINCIAS, municipio_desde_nombre, normalizar
from placsp import Contrato

ALTO = "Alto"
MEDIO = "Medio"
DUDOSO = "Dudoso"
ORDEN_ENCAJE = {ALTO: 0, MEDIO: 1, DUDOSO: 2}


@lru_cache(maxsize=None)
def _patron(terminos: tuple[str, ...]) -> re.Pattern | None:
    limpios = sorted({normalizar(t) for t in terminos if normalizar(t)}, key=len, reverse=True)
    if not limpios:
        return None
    return re.compile(r"\b(" + "|".join(re.escape(t) for t in limpios) + r")[a-z]*\b")


def _coincidencias(texto: str, terminos: list[str]) -> list[str]:
    """Términos encontrados; cada uno vale también con plural o terminación (paella -> paellas)."""
    patron = _patron(tuple(terminos))
    if patron is None:
        return []
    return sorted(set(patron.findall(texto)))


def en_zona(c: Contrato, provincias: list[str]) -> bool:
    """El contrato se ejecuta en, o lo convoca un organismo de, alguna provincia elegida.

    Los que se ejecutan en "toda la Comunitat Valenciana" (NUTS ES52) también cuentan.
    """
    if any(n.strip().upper() == NUTS_COMUNITAT for n in c.nuts):
        return True
    for prov in provincias:
        nuts = PROVINCIAS[prov]["nuts"]
        if any(n.upper().startswith(nuts) for n in c.nuts):
            return True
        if any(d.upper().startswith(f"L01{prov}") or d.upper() == f"L020000{prov}" for d in c.dir3):
            return True
        if c.cp.strip().startswith(prov) and len(c.cp.strip()) == 5:
            return True
    return False


def de_paella(texto: str, config: dict) -> list[str]:
    """Palabras de paella que aparecen en el texto (vacío si no habla de paellas)."""
    return _coincidencias(normalizar(texto), config["palabras"]["paella"])


def puntuar(c: Contrato, config: dict) -> tuple[str, str] | None:
    """Devuelve (encaje, motivo) o None si el contrato no tiene que ver con paellas."""
    palabras = config["palabras"]
    texto = normalizar(c.texto)
    if config.get("solo_paellas", True):
        paellas = de_paella(texto, config)
        return (ALTO, "menciona " + ", ".join(paellas)) if paellas else None
    seguras = _coincidencias(texto, palabras["seguras"])
    if seguras:
        return ALTO, "menciona " + ", ".join(seguras)
    excluidas = _coincidencias(texto, palabras["excluir"])
    if excluidas:
        return None
    fiesta = _coincidencias(texto, palabras["fiesta"])
    comida = _coincidencias(texto, palabras["comida"])
    cpv_comida = [p for p in c.cpvs if any(p.startswith(x) for x in config["cpv_comida"])]
    cpv_eventos = [p for p in c.cpvs if any(p.startswith(x) for x in config["cpv_eventos"])]
    if fiesta and comida:
        return MEDIO, f"fiesta ({', '.join(fiesta)}) y comida ({', '.join(comida)})"
    if fiesta and cpv_comida:
        return MEDIO, f"fiesta ({', '.join(fiesta)}) y CPV de comidas {', '.join(cpv_comida)}"
    if comida and cpv_eventos:
        return MEDIO, f"comida ({', '.join(comida)}) y CPV de eventos {', '.join(cpv_eventos)}"
    if cpv_comida:
        return DUDOSO, f"CPV de comidas {', '.join(cpv_comida)}"
    return None


def municipio(c: Contrato) -> str:
    for nombre in [c.organo, *c.padres]:
        m = municipio_desde_nombre(nombre)
        if m:
            return m
    return c.ciudad


def dir3_ayuntamiento(c: Contrato, provincias: list[str]) -> str:
    """Código DIR3 del ayuntamiento (L01 + provincia), el mismo que usa la hoja del bot."""
    for d in c.dir3:
        if any(d.upper().startswith(f"L01{p}") for p in provincias):
            return d.upper()
    return ""


def provincia(c: Contrato, provincias: list[str]) -> str:
    """Valencia, Alicante o Castellón según el DIR3, el código postal o el lugar de ejecución."""
    for prov in provincias:
        if any(d.upper().startswith(f"L01{prov}") for d in c.dir3):
            return PROVINCIAS[prov]["nombre"]
    for prov in provincias:
        if c.cp.strip().startswith(prov) and len(c.cp.strip()) == 5:
            return PROVINCIAS[prov]["nombre"]
    for prov in provincias:
        if any(n.upper().startswith(PROVINCIAS[prov]["nuts"]) for n in c.nuts):
            return PROVINCIAS[prov]["nombre"]
    return ""
