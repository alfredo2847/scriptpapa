"""Fase 4: adaptador genérico de sede electrónica, uno por plataforma (no por municipio).

Cada plataforma se describe en huellas/sedes/<plataforma>.yaml con el mismo
formato que huellas/rec.yaml. Su apertura solo puede llevar al trámite
"Instancia general" o "Solicitud genérica"; un formulario desconocido es un
MANUAL, no una adivinanza.

Si una plataforma necesita lógica propia, se crea src/sedes/<plataforma>.py con
una clase `Adaptador` que herede de AdaptadorSede.
"""

from __future__ import annotations

import re

import yaml

from adaptador import Adaptador
from motor import CARPETA_HUELLAS
from salvaguardas import verificar_resumen_sede

RUTA_PLATAFORMAS = CARPETA_HUELLAS / "plataformas.yaml"


def cargar_plataformas() -> dict:
    with open(RUTA_PLATAFORMAS, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("plataformas") or {}


def identificar_plataforma(url: str, html: str, plataformas: dict | None = None) -> str:
    """Nombre de la plataforma cuya huella (dominio o HTML) coincide, o ''."""
    plataformas = cargar_plataformas() if plataformas is None else plataformas
    for nombre, huella in plataformas.items():
        if reconoce_con(huella, url, html):
            return nombre
    return ""


def reconoce_con(huella: dict, url: str, html: str) -> bool:
    from urllib.parse import urlparse

    dominio = (urlparse(url).hostname or "").lower()
    if any(re.search(p, dominio, re.IGNORECASE) for p in huella.get("dominios") or []):
        return True
    return any(re.search(p, html or "", re.IGNORECASE) for p in huella.get("html") or [])


class AdaptadorSede(Adaptador):
    @property
    def via(self) -> str:
        return self.flujo.nombre

    @classmethod
    def reconoce(cls, plataforma: str, url: str, html: str) -> bool:
        huella = cargar_plataformas().get(plataforma) or {}
        return reconoce_con(huella, url, html)

    def verificar_resumen(self, fila: dict) -> tuple[dict, list[str]]:
        contexto = self.motor.contexto
        leido = self.motor.leer_resumen()
        esperado = {
            "municipio": fila["municipio"],
            "url_sede": fila.get("url_sede") or "",
            "adjuntos": [p.name for p in contexto["adjuntos"].values()],
        }
        return leido, verificar_resumen_sede(leido, esperado)
