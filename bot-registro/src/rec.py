"""Fase 3: adaptador del Registro Electrónico Común (rec.redsara.es).

Los pasos, pantallas y selectores viven en huellas/rec.yaml y se fijan con las
capturas de un envío manual de referencia (python src/main.py grabar).
"""

from __future__ import annotations

from adaptador import Adaptador, contexto_base
from hoja import VIA_REC
from motor import CARPETA_HUELLAS, ErrorAyuntamiento, Flujo, Motor
from salvaguardas import verificar_resumen_rec

RUTA_HUELLAS_REC = CARPETA_HUELLAS / "rec.yaml"


def cargar_flujo_rec() -> Flujo:
    return Flujo(RUTA_HUELLAS_REC)


class AdaptadorREC(Adaptador):
    via = VIA_REC

    def verificar_resumen(self, fila: dict) -> tuple[dict, list[str]]:
        contexto = self.motor.contexto
        leido = self.motor.leer_resumen()
        esperado = {
            "municipio": fila["municipio"],
            "dir3_ayto": fila["dir3_ayto"],
            "dir3_destino": contexto["dir3_destino"],
            "codigos_validos": contexto["codigos_validos"],
            "adjuntos": [p.name for p in contexto["adjuntos"].values()],
        }
        return leido, verificar_resumen_rec(leido, esperado)


class DetectorREC:
    """Comprueba en el buscador de destinatarios del REC si un ayuntamiento está disponible."""

    def __init__(self, navegador, flujo: Flujo, config: dict, log):
        self.motor = Motor(navegador, flujo, config, log)
        self.flujo = flujo
        self.log = log
        self.motor.contexto = contexto_base(config)

    def preparar(self) -> None:
        self.motor.ejecutar_pasos(self.flujo.seccion("deteccion"))

    def esta_en_rec(self, dir3_ayto: str) -> tuple[bool, list[dict]]:
        from playwright.sync_api import Error as ErrorPlaywright

        try:
            if (self.flujo.datos.get("destinatario") or {}).get("modo") == "codigo":
                encontrado = self.motor.buscar_por_codigo(dir3_ayto)
                resultados = [{"codigo": dir3_ayto, "nombre": "", "fila": None}] if encontrado else []
                if encontrado:
                    self.preparar()  # el organismo queda elegido: se vuelve a un formulario limpio
                return encontrado, [{"codigo": r["codigo"], "nombre": r["nombre"]} for r in resultados]
            resultados = self.motor.buscar_destinatario(dir3_ayto)
            encontrado = any(r["codigo"] == dir3_ayto for r in resultados)
            self.motor.cerrar_busqueda()
        except ErrorPlaywright as e:
            raise ErrorAyuntamiento(f"Fallo en el buscador del REC: {str(e).splitlines()[0]}") from None
        return encontrado, [{"codigo": r["codigo"], "nombre": r["nombre"]} for r in resultados]
