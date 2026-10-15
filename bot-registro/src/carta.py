"""Carta personalizada por municipio (documentos.carta_personalizada: true).

Genera documentos/personalizadas/carta_<dir3>.pdf a partir de la plantilla de
texto (documentos/plantilla_carta.txt), sustituyendo {municipio}, {fecha},
{razon_social}, {cif}, {direccion}, {email} y {telefono}.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from comun import RAIZ, rellenar_plantilla, ruta_proyecto

CARPETA_PERSONALIZADAS = RAIZ / "documentos" / "personalizadas"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def generar_carta(config: dict, fila: dict) -> Path:
    from fpdf import FPDF

    plantilla = ruta_proyecto(config["documentos"]["plantilla_carta"]).read_text(encoding="utf-8")
    hoy = date.today()
    contexto = dict(config["interesado"])
    contexto.update(municipio=fila["municipio"], fecha=f"{hoy.day} de {MESES[hoy.month - 1]} de {hoy.year}")
    texto = rellenar_plantilla(plantilla, contexto)

    pdf = FPDF(format="A4")
    pdf.set_margins(25, 25, 25)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for linea in texto.splitlines():
        # Las fuentes básicas de PDF cubren latin-1 (tildes, ç, à, l·l).
        pdf.multi_cell(0, 6, linea.encode("latin-1", "replace").decode("latin-1") or " ",
                       new_x="LMARGIN", new_y="NEXT")
    CARPETA_PERSONALIZADAS.mkdir(parents=True, exist_ok=True)
    destino = CARPETA_PERSONALIZADAS / f"carta_{fila['dir3_ayto']}.pdf"
    pdf.output(str(destino))
    return destino
