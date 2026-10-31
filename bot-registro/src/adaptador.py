"""Contrato común de los adaptadores (REC y sedes electrónicas).

  abrir_instancia_general(contexto)  navega hasta el formulario (en sedes, solo "Instancia general")
  rellenar(contexto)                 interesado, expone, solicita, destinatario y adjuntos
  verificar_resumen(fila)            lee el resumen y lo compara con la hoja -> (leido, fallos)
  cancelar()                         abandona el borrador (modo prueba o envío no confirmado)
  firmar_y_esperar(segundos)         pulsa "Firmar y enviar" y espera al justificante
  guardar_justificante(fila)         lee número y fecha y descarga el PDF
"""

from __future__ import annotations

import re
from pathlib import Path

from comun import RAIZ, ahora_texto, nombre_archivo_seguro, rellenar_plantilla
from motor import ErrorAyuntamiento, Flujo, Motor, Navegador

CARPETA_JUSTIFICANTES = RAIZ / "justificantes"


def contexto_base(config: dict) -> dict:
    """Campos disponibles en las plantillas de las huellas: {razon_social}, {url_inicio}, ..."""
    contexto = {f"interesado_{k}": v for k, v in config["interesado"].items()}
    contexto.update(config["interesado"])
    contexto["url_inicio"] = config["rec"]["url_inicio"]
    return contexto


def contexto_envio(config: dict, fila: dict, adjuntos: dict[str, Path], codigos_validos: set[str],
                   nombre_ayto: str) -> dict:
    contexto = contexto_base(config)
    municipio = fila["municipio"]
    for campo in ("asunto", "expone", "solicita"):
        contexto[campo] = " ".join(rellenar_plantilla(config["textos"][campo], {"municipio": municipio}).split())
    contexto.update({
        "municipio": municipio,
        "dir3_ayto": fila["dir3_ayto"],
        "dir3_destino": fila.get("dir3_destino") or fila["dir3_ayto"],
        "nombre_destino": fila.get("nombre_destino") or nombre_ayto,
        "nombre_ayto": nombre_ayto,
        "url_sede": fila.get("url_sede") or "",
        "adjuntos": adjuntos,
        "codigos_validos": codigos_validos,
    })
    return contexto


class Adaptador:
    via = ""

    def __init__(self, navegador: Navegador, flujo: Flujo, config: dict, log):
        self.flujo = flujo
        self.config = config
        self.log = log
        self.motor = Motor(navegador, flujo, config, log)

    # -- contrato ------------------------------------------------------------
    def abrir_instancia_general(self, contexto: dict) -> None:
        self.motor.contexto = contexto
        self.motor.dialogos.clear()
        self.motor.ejecutar_pasos(self.flujo.seccion("apertura"))

    def rellenar(self, contexto: dict) -> None:
        self.motor.contexto = contexto
        self.motor.ejecutar_pasos(self.flujo.seccion("rellenado"))

    def verificar_resumen(self, fila: dict) -> tuple[dict, list[str]]:
        raise NotImplementedError

    def cancelar(self) -> None:
        cfg = self.flujo.seccion("resumen")
        try:
            self.motor.ejecutar_acciones(cfg.get("cancelar"))
        except ErrorAyuntamiento as e:
            self.log.warning(f"    no se pudo cancelar el borrador: {e}")

    def firmar_y_esperar(self, segundos: float) -> bool:
        firma = self.flujo.seccion("firma")
        justificante = self.flujo.seccion("justificante")
        self.motor.exigir(self.flujo.seccion("resumen")["pantalla"])
        self.motor.aceptar_dialogos = bool(firma.get("aceptar_dialogos"))
        try:
            self.motor.ejecutar_acciones(firma["acciones"])
            self.motor.ejecutar_pasos(firma.get("pasos"))
            self.log.info(f"    >>> {firma.get('mensaje', 'Confirma la firma en Autofirma')} "
                          f"(espera máxima {int(segundos)} s)")
            return self.motor._esperar_coincidencia(justificante["pantalla"], segundos)
        finally:
            self.motor.aceptar_dialogos = False

    def guardar_justificante(self, fila: dict) -> dict:
        """Devuelve {num_registro, fecha_envio, justificante, aviso}."""
        cfg = self.flujo.seccion("justificante")
        self.motor.exigir(cfg["pantalla"])
        campos = self.motor.leer_campos(cfg.get("campos"))
        numero = campos.get("num_registro", "")
        if cfg.get("regex_num_registro"):
            m = re.search(cfg["regex_num_registro"], numero)
            numero = (m.group(1) if m and m.groups() else m.group(0)) if m else ""
        resultado = {
            "num_registro": numero.strip(),
            "fecha_envio": campos.get("fecha", "").strip() or ahora_texto(),
            "justificante": "",
            "aviso": "",
        }
        if cfg.get("descargar"):
            CARPETA_JUSTIFICANTES.mkdir(exist_ok=True)
            destino = CARPETA_JUSTIFICANTES / f"{fila['dir3_ayto']}_{nombre_archivo_seguro(fila['municipio'])}.pdf"
            try:
                with self.motor.pagina.expect_download(timeout=60000) as descarga:
                    self.motor.localizar(cfg["descargar"]).click()
                descarga.value.save_as(str(destino))
                resultado["justificante"] = str(destino.relative_to(RAIZ))
            except Exception as e:
                resultado["aviso"] = f"No se pudo descargar el justificante ({str(e).splitlines()[0]}); descargarlo a mano"
        else:
            resultado["aviso"] = "Sin descarga configurada: guardar el justificante a mano"
        return resultado
