"""Adaptadores de sede electrónica disponibles (solo los de huellas verificadas)."""

from __future__ import annotations

import importlib

from motor import CARPETA_HUELLAS, Flujo

CARPETA_SEDES = CARPETA_HUELLAS / "sedes"


def flujos_sede(solo_verificados: bool = True) -> dict[str, Flujo]:
    flujos = {}
    for ruta in sorted(CARPETA_SEDES.glob("*.yaml")):
        if ruta.name.startswith("_"):
            continue
        flujo = Flujo(ruta)
        if flujo.verificada or not solo_verificados:
            flujos[flujo.nombre] = flujo
    return flujos


def clase_adaptador(plataforma: str):
    """src/sedes/<plataforma>.py con una clase Adaptador, o el adaptador genérico."""
    from sedes.base import AdaptadorSede

    try:
        modulo = importlib.import_module(f"sedes.{plataforma}")
        return getattr(modulo, "Adaptador", AdaptadorSede)
    except ModuleNotFoundError:
        return AdaptadorSede
