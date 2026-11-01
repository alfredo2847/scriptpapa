"""Una carpeta por licitación que sirve, con su valoración, lo principal y los pliegos.

    fichas/2026-11-20 Sueca - Servicio de paellas gigantes/
        00_RESUMEN.txt              valoración y datos principales
        pliego_administrativo_...   pliegos descargados de la plataforma
        pliego_tecnico_...

La valoración es orientativa (0 a 100) y explica de dónde sale cada punto.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from comun import RAIZ, normalizar
from filtros import ALTO, DUDOSO, MEDIO
from placsp import ESTADOS, PRESENTACION, PROCEDIMIENTOS, TIPOS, Contrato

CARPETA = RAIZ / "fichas"
RESUMEN = "00_RESUMEN.txt"

MESES_LARGOS = ("enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|"
                "gener|febrer|abril|maig|juny|juliol|agost|setembre|octubre|novembre|desembre")

# Frases que se buscan en el texto de los pliegos
FRASES = {
    "Raciones / personas": re.compile(
        r"\b\d[\d.]*\s*(raciones|racions|comensales|comensals|personas|persones|cubiertos|men[uú]s)\b", re.I),
    "Fechas": re.compile(rf"\b\d{{1,2}}\s+d['e]\s*(?:{MESES_LARGOS})\b", re.I),
    "Requisitos sanitarios y seguro": re.compile(
        r"registro sanitario|registre sanitari|manipulador|seguro de responsabilidad|asseguran[cç]a", re.I),
    "Solvencia": re.compile(r"solvencia|solv[eè]ncia", re.I),
    "Garantía": re.compile(r"garant[ií]a definitiva|garantia definitiva", re.I),
    "Criterios de adjudicación": re.compile(r"criterios? de adjudicaci|criteris? d'adjudicaci", re.I),
}
MAX_FRASES = 4


def _euros(valor: float | None) -> str:
    if valor is None:
        return "sin indicar"
    return f"{valor:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def valorar(c: Contrato, encaje: str, ahora: datetime, config: dict) -> tuple[int, str, list[str]]:
    """Puntos (0-100), etiqueta y razones."""
    opciones = config["fichas"]
    puntos = 0
    razones: list[str] = []

    def suma(n: int, razon: str) -> None:
        nonlocal puntos
        puntos += n
        razones.append(f"{'+' if n >= 0 else ''}{n}  {razon}")

    suma({ALTO: 40, MEDIO: 25, DUDOSO: 5}.get(encaje, 0), f"encaje {encaje.lower()}")
    if "paella" in normalizar(c.titulo + " " + c.objeto):
        suma(10, "el título habla de paellas")

    if c.importe is None:
        suma(5, "importe sin indicar")
    elif c.importe < opciones["importe_minimo"]:
        suma(0, f"importe bajo ({_euros(c.importe)})")
    elif c.importe <= opciones["importe_maximo"]:
        suma(20, f"importe adecuado ({_euros(c.importe)})")
    else:
        suma(10, f"importe alto ({_euros(c.importe)}): pedirá más solvencia")

    if c.plazo is None:
        suma(5, "sin plazo publicado")
    else:
        dias = (c.plazo.date() - ahora.date()).days
        if dias >= 10:
            suma(15, f"plazo holgado ({dias} días)")
        elif dias >= 5:
            suma(10, f"plazo justo ({dias} días)")
        elif dias >= 2:
            suma(5, f"poco plazo ({dias} días)")
        else:
            suma(0, f"plazo casi vencido ({dias} días)")

    if c.procedimiento == "9":
        suma(10, "procedimiento abierto simplificado (trámite sencillo)")
    elif c.procedimiento == "1":
        suma(5, "procedimiento abierto")
    if c.tipo == "2":
        suma(5, "contrato de servicios")
    if c.estado == "PRE":
        razones.append("    es un anuncio previo: aún no se pueden presentar ofertas")

    puntos = max(0, min(100, puntos))
    if puntos >= 70:
        etiqueta = "Muy interesante"
    elif puntos >= 50:
        etiqueta = "Interesante"
    elif puntos >= 30:
        etiqueta = "Revisar"
    else:
        etiqueta = "Poco interesante"
    return puntos, etiqueta, razones


def _seguro(texto: str, largo: int = 70) -> str:
    texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", texto or "")
    texto = re.sub(r"\s+", " ", texto).strip(" .")
    return texto[:largo].rstrip(" .") or "sin_nombre"


def nombre_carpeta(c: Contrato, municipio: str) -> str:
    fecha = f"{c.plazo:%Y-%m-%d}" if c.plazo else "sin-plazo"
    return _seguro(f"{fecha} {municipio or c.organo} - {c.objeto or c.titulo}", 90)


def frases_clave(texto: str) -> dict[str, list[str]]:
    """Frases de los pliegos con datos útiles (raciones, fechas, solvencia...)."""
    trozos = re.split(r"(?<=[.;:])\s+|\n+", re.sub(r"[ \t]+", " ", texto or ""))
    salida: dict[str, list[str]] = {}
    for titulo, patron in FRASES.items():
        vistas: list[str] = []
        for trozo in trozos:
            trozo = trozo.strip()
            if 15 <= len(trozo) <= 350 and patron.search(trozo) and trozo not in vistas:
                vistas.append(trozo)
                if len(vistas) >= MAX_FRASES:
                    break
        if vistas:
            salida[titulo] = vistas
    return salida


def texto_pdf(ruta: Path) -> str:
    try:
        from pypdf import PdfReader
        lector = PdfReader(str(ruta))
        return "\n".join((pagina.extract_text() or "") for pagina in lector.pages[:80])
    except Exception:
        return ""


def _descargar_pliegos(c: Contrato, carpeta: Path, red, log) -> tuple[list[str], list[str]]:
    descargados, fallidos = [], []
    for tipo, nombre, url in c.documentos:
        base = _seguro(f"{tipo}_{nombre}", 100)
        existentes = [p for p in carpeta.iterdir() if p.name.startswith(base)]
        if existentes:
            descargados.append(existentes[0].name)
            continue
        try:
            descargados.append(red.descargar_documento(url, carpeta, base).name)
        except Exception as e:
            fallidos.append(f"{nombre} ({url})")
            if log:
                log.warning(f"    No se pudo descargar {nombre}: {e}")
    return descargados, fallidos


def crear(c: Contrato, encaje: str, motivo: str, municipio: str, ahora: datetime, config: dict,
          red=None, log=None, carpeta: Path | None = None, base: Path | None = None) -> tuple[Path, int, str]:
    """Crea o actualiza la carpeta de la licitación. Devuelve (carpeta, puntos, etiqueta)."""
    base = base or CARPETA
    carpeta = carpeta if carpeta and carpeta.exists() else base / nombre_carpeta(c, municipio)
    carpeta.mkdir(parents=True, exist_ok=True)
    puntos, etiqueta, razones = valorar(c, encaje, ahora, config)

    descargados, fallidos = [], []
    if red is not None and config["fichas"]["descargar_pliegos"]:
        descargados, fallidos = _descargar_pliegos(c, carpeta, red, log)
    frases: dict[str, list[str]] = {}
    for nombre in descargados:
        if nombre.lower().endswith(".pdf"):
            for titulo, lista in frases_clave(texto_pdf(carpeta / nombre)).items():
                frases.setdefault(titulo, [])
                frases[titulo].extend(f"[{nombre}] {f}" for f in lista if len(frases[titulo]) < MAX_FRASES * 2)

    dias = f" (quedan {(c.plazo.date() - ahora.date()).days} días)" if c.plazo else ""
    lineas = [
        f"LICITACIÓN: {c.objeto or c.titulo}",
        f"VALORACIÓN: {puntos}/100 - {etiqueta}",
        f"Ficha actualizada el {ahora:%d/%m/%Y %H:%M}",
        "=" * 78,
        "",
        "POR QUÉ ESTA VALORACIÓN",
        *[f"  {r}" for r in razones],
        f"  (encaje: {motivo})",
        "",
        "DATOS PRINCIPALES",
        f"  Organismo:          {c.organo}",
        f"  Municipio:          {municipio}",
        f"  Expediente:         {c.expediente}",
        f"  Importe sin IVA:    {_euros(c.importe)}",
        f"  Plazo de ofertas:   {c.plazo:%d/%m/%Y %H:%M}{dias}" if c.plazo else "  Plazo de ofertas:   sin publicar",
        f"  Estado:             {ESTADOS.get(c.estado, c.estado)}",
        f"  Procedimiento:      {PROCEDIMIENTOS.get(c.procedimiento, c.procedimiento or 'sin indicar')}",
        f"  Tipo:               {TIPOS.get(c.tipo, c.tipo or 'sin indicar')}",
        f"  Presentación:       {PRESENTACION.get(c.presentacion, c.presentacion or 'sin indicar')}",
        f"  Ejecución:          {c.ejecucion or 'sin indicar'}",
        f"  CPV:                {', '.join(c.cpvs) or 'sin indicar'}",
        f"  Enlace:             {c.enlace}",
    ]
    if c.lotes:
        lineas += ["", "LOTES (se puede ofertar solo al que interese, si el pliego lo permite)",
                   *[f"  - {l}" for l in c.lotes]]
    if c.criterios:
        lineas += ["", "CRITERIOS DE ADJUDICACIÓN",
                   *[f"  - {d}" + (f": {p} puntos" if p else "") for d, p in c.criterios]]
    if c.garantias:
        lineas += ["", "GARANTÍAS", *[f"  - {g}" for g in c.garantias]]
    if c.solvencia:
        lineas += ["", "SOLVENCIA EXIGIDA", *[f"  - {s}" for s in c.solvencia]]
    lineas += ["", "DOCUMENTOS EN ESTA CARPETA"]
    lineas += [f"  - {d}" for d in descargados] or ["  (ninguno descargado: búscalos en el enlace)"]
    if fallidos:
        lineas += ["  No se pudieron descargar (ábrelos desde el enlace):", *[f"  - {f}" for f in fallidos]]
    if frases:
        lineas += ["", "FRASES CLAVE DE LOS PLIEGOS (sacadas automáticamente: compruébalas en el pliego)"]
        for titulo, lista in frases.items():
            lineas += [f"  {titulo}:", *[f"    · {f}" for f in lista]]
    lineas += [
        "",
        "QUÉ HACER",
        "  1. Lee los pliegos de esta carpeta (requisitos, raciones, fechas, solvencia).",
        "  2. Si interesa, pon ME INTERESA en datos\\licitaciones.xlsx: te avisará antes del plazo.",
        "  3. La oferta se presenta en la Plataforma de Contratación con el certificado,",
        "     siguiendo los pliegos. Después pon PRESENTADA en la hoja.",
    ]
    (carpeta / RESUMEN).write_text("\n".join(lineas) + "\n", encoding="utf-8-sig")
    return carpeta, puntos, etiqueta
