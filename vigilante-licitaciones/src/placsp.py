"""Lectura de los datos abiertos de la Plataforma de Contratación del Sector Público.

La PLACSP publica sus contratos como feeds ATOM con formato CODICE. Cada
entrada es un expediente (ContractFolderStatus) en su último estado. Los
feeds se encadenan con enlaces rel="next" hacia atrás en el tiempo, y los
años y meses anteriores se publican en ZIP con todas sus páginas.

El lector ignora los espacios de nombres y busca los elementos por su nombre
local, para no romperse si cambia una versión del esquema.
"""

from __future__ import annotations

import io
import time
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, Iterator

import requests

ESTADOS = {
    "PRE": "Anuncio previo",
    "PUB": "En plazo",
    "EV": "Pendiente de adjudicación",
    "ADJ": "Adjudicada",
    "RES": "Resuelta",
    "ANUL": "Anulada",
}

PROCEDIMIENTOS = {
    "1": "Abierto",
    "2": "Restringido",
    "3": "Negociado sin publicidad",
    "4": "Negociado con publicidad",
    "5": "Diálogo competitivo",
    "7": "Derivado de acuerdo marco",
    "9": "Abierto simplificado",
    "13": "Licitación con negociación",
}

TIPOS = {"1": "Suministros", "2": "Servicios", "3": "Obras"}

PRESENTACION = {"1": "Electrónica", "2": "Manual (en papel)", "3": "Electrónica y manual"}

GARANTIAS = {"1": "Provisional", "2": "Definitiva", "3": "Complementaria"}

DOCUMENTOS = {
    "LegalDocumentReference": "pliego_administrativo",
    "TechnicalDocumentReference": "pliego_tecnico",
    "AdditionalDocumentReference": "documento",
}

UNIDADES = {"DAY": "días", "MON": "meses", "ANN": "años"}


@dataclass
class Contrato:
    id: str
    fuente: str = ""
    enlace: str = ""
    titulo: str = ""
    actualizado: datetime | None = None
    expediente: str = ""
    estado: str = ""
    organo: str = ""
    padres: list[str] = field(default_factory=list)
    dir3: list[str] = field(default_factory=list)
    nif: str = ""
    ciudad: str = ""
    cp: str = ""
    objeto: str = ""
    lotes: list[str] = field(default_factory=list)
    tipo: str = ""
    importe: float | None = None
    cpvs: list[str] = field(default_factory=list)
    nuts: list[str] = field(default_factory=list)
    lugar: str = ""
    plazo: datetime | None = None
    procedimiento: str = ""
    adjudicatarios: list[str] = field(default_factory=list)
    importe_adjudicacion: float | None = None
    fecha_adjudicacion: date | None = None
    presentacion: str = ""
    ejecucion: str = ""
    documentos: list[tuple[str, str, str]] = field(default_factory=list)  # (tipo, nombre, url)
    criterios: list[tuple[str, str]] = field(default_factory=list)        # (descripción, peso)
    garantias: list[str] = field(default_factory=list)
    solvencia: list[str] = field(default_factory=list)

    @property
    def texto(self) -> str:
        """Texto en el que se buscan las palabras clave."""
        return " | ".join([self.titulo, self.objeto, *self.lotes])


# ---------------------------------------------------------------------------
# Ayudas para recorrer el XML sin espacios de nombres

def _ln(etiqueta) -> str:
    return etiqueta.rsplit("}", 1)[-1] if isinstance(etiqueta, str) else ""


def _hijo(el, *ruta):
    for nombre in ruta:
        if el is None:
            return None
        el = next((c for c in el if _ln(c.tag) == nombre), None)
    return el


def _texto(el, *ruta) -> str:
    e = _hijo(el, *ruta)
    return (e.text or "").strip() if e is not None else ""


def _todos(el, nombre: str) -> list:
    if el is None:
        return []
    return [d for d in el.iter() if _ln(d.tag) == nombre]


def _numero(texto: str) -> float | None:
    try:
        return float(texto)
    except (TypeError, ValueError):
        return None


def _fecha(texto: str) -> date | None:
    try:
        return date.fromisoformat((texto or "")[:10])
    except ValueError:
        return None


def _fecha_hora(texto: str) -> datetime | None:
    if not texto:
        return None
    try:
        valor = datetime.fromisoformat(texto.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    # Se trabaja en hora local sin zona: la PLACSP publica en hora peninsular.
    return valor.replace(tzinfo=None)


def _unicos(valores: Iterable[str]) -> list[str]:
    vistos: list[str] = []
    for v in valores:
        v = (v or "").strip()
        if v and v not in vistos:
            vistos.append(v)
    return vistos


# ---------------------------------------------------------------------------
# Entradas

def parsear_entrada(entrada, fuente: str = "") -> Contrato | None:
    """Convierte un <entry> del feed en un Contrato."""
    ident = _texto(entrada, "id")
    if not ident:
        return None
    c = Contrato(id=ident, fuente=fuente)
    c.titulo = _texto(entrada, "title")
    c.actualizado = _fecha_hora(_texto(entrada, "updated"))
    for enlace in entrada:
        if _ln(enlace.tag) == "link" and enlace.get("rel") in (None, "alternate"):
            c.enlace = enlace.get("href", "")
            break

    cfs = _hijo(entrada, "ContractFolderStatus")
    if cfs is None:
        return c
    c.expediente = _texto(cfs, "ContractFolderID")
    c.estado = _texto(cfs, "ContractFolderStatusCode")

    organo = _hijo(cfs, "LocatedContractingParty")
    parte = _hijo(organo, "Party")
    c.organo = _texto(parte, "PartyName", "Name")
    c.ciudad = _texto(parte, "PostalAddress", "CityName")
    c.cp = _texto(parte, "PostalAddress", "PostalZone")
    for ident_el in _todos(parte, "ID"):
        if (ident_el.get("schemeName") or "").upper() == "NIF":
            c.nif = (ident_el.text or "").strip()
            break
    c.dir3 = _unicos(
        e.text for e in _todos(organo, "ID") if (e.get("schemeName") or "").upper() == "DIR3"
    )
    c.padres = _unicos(
        e.text for p in _todos(organo, "ParentLocatedParty") for e in _todos(_hijo(p, "PartyName"), "Name")
    )

    proyecto = _hijo(cfs, "ProcurementProject")
    c.objeto = _texto(proyecto, "Name")
    c.tipo = _texto(proyecto, "TypeCode")
    presupuesto = _hijo(proyecto, "BudgetAmount")
    for campo in ("TaxExclusiveAmount", "TotalAmount", "EstimatedOverallContractAmount"):
        valor = _numero(_texto(presupuesto, campo))
        if valor is not None:
            c.importe = valor
            break
    c.cpvs = _unicos(e.text for e in _todos(proyecto, "ItemClassificationCode"))
    lugar = _hijo(proyecto, "RealizedLocation")
    c.nuts = _unicos(e.text for e in _todos(lugar, "CountrySubentityCode"))
    c.lugar = _texto(lugar, "CountrySubentity")

    for lote in _todos(cfs, "ProcurementProjectLot"):
        p = _hijo(lote, "ProcurementProject")
        c.lotes.extend(_unicos([_texto(p, "Name")]))
        c.cpvs = _unicos([*c.cpvs, *(e.text for e in _todos(p, "ItemClassificationCode"))])
        c.nuts = _unicos([*c.nuts, *(e.text for e in _todos(p, "CountrySubentityCode"))])

    proceso = _hijo(cfs, "TenderingProcess")
    c.procedimiento = _texto(proceso, "ProcedureCode")
    plazo = _hijo(proceso, "TenderSubmissionDeadlinePeriod")
    fecha_plazo = _fecha(_texto(plazo, "EndDate"))
    if fecha_plazo:
        hora = _texto(plazo, "EndTime")[:8] or "23:59:59"
        try:
            c.plazo = datetime.fromisoformat(f"{fecha_plazo.isoformat()}T{hora}")
        except ValueError:
            c.plazo = datetime.combine(fecha_plazo, datetime.max.time()).replace(microsecond=0)

    c.presentacion = _texto(proceso, "SubmissionMethodCode")
    periodo = _hijo(proyecto, "PlannedPeriod")
    partes = []
    duracion = _hijo(periodo, "DurationMeasure")
    if duracion is not None and (duracion.text or "").strip():
        unidad = UNIDADES.get(duracion.get("unitCode", ""), duracion.get("unitCode", ""))
        partes.append(f"{duracion.text.strip()} {unidad}".strip())
    inicio, fin = _fecha(_texto(periodo, "StartDate")), _fecha(_texto(periodo, "EndDate"))
    if inicio or fin:
        partes.append(" a ".join(f"{d:%d/%m/%Y}" for d in (inicio, fin) if d))
    c.ejecucion = "; ".join(partes)

    for etiqueta, tipo in DOCUMENTOS.items():
        for doc in _todos(cfs, etiqueta):
            url = _texto(doc, "Attachment", "ExternalReference", "URI")
            if url:
                c.documentos.append((tipo, _texto(doc, "ID") or tipo, url))

    terminos = _hijo(cfs, "TenderingTerms")
    for criterio in _todos(terminos, "AwardingCriteria"):
        descripcion = _texto(criterio, "Description")
        if descripcion:
            c.criterios.append((descripcion, _texto(criterio, "WeightNumeric")))
    for garantia in _todos(terminos, "RequiredFinancialGuarantee"):
        tipo = GARANTIAS.get(_texto(garantia, "GuaranteeTypeCode"), "Garantía")
        porcentaje, importe = _texto(garantia, "AmountRate"), _texto(garantia, "LiabilityAmount")
        detalle = f"{porcentaje} %" if porcentaje else (f"{importe} €" if importe else "")
        c.garantias.append(f"{tipo}: {detalle}".rstrip(": "))
    for etiqueta in ("TechnicalEvaluationCriteria", "FinancialEvaluationCriteria"):
        for criterio in _todos(terminos, etiqueta):
            descripcion = _texto(criterio, "Description")
            if descripcion:
                c.solvencia.append(("Técnica: " if etiqueta.startswith("Tech") else "Económica: ") + descripcion)
    c.solvencia = _unicos(c.solvencia)

    resultados = _todos(cfs, "TenderResult")
    c.adjudicatarios = _unicos(
        _texto(g, "PartyName", "Name") for r in resultados for g in _todos(r, "WinningParty")
    )
    importes = [
        _numero(_texto(t, "TaxExclusiveAmount"))
        for r in resultados for t in _todos(r, "LegalMonetaryTotal")
    ]
    importes = [i for i in importes if i is not None]
    if importes:
        c.importe_adjudicacion = sum(importes)
    fechas = [f for f in (_fecha(_texto(r, "AwardDate")) for r in resultados) if f]
    if fechas:
        c.fecha_adjudicacion = max(fechas)
    return c


def leer_atom(origen, fuente: str = "", siguiente: dict | None = None) -> Iterator[Contrato]:
    """Lee un archivo ATOM (ruta, bytes o archivo abierto) entrada a entrada.

    Si se pasa `siguiente`, se guarda en siguiente["url"] el enlace rel="next".
    """
    if isinstance(origen, (bytes, bytearray)):
        origen = io.BytesIO(origen)
    raiz = None
    for evento, el in ET.iterparse(origen, events=("start", "end")):
        if evento == "start":
            if raiz is None:
                raiz = el
            continue
        nombre = _ln(el.tag)
        if nombre == "entry":
            contrato = parsear_entrada(el, fuente)
            raiz.clear()  # libera memoria: los ZIP anuales tienen cientos de miles de entradas
            if contrato:
                yield contrato
        elif nombre == "link" and el.get("rel") == "next" and siguiente is not None:
            siguiente["url"] = el.get("href", "")


def leer_archivo(ruta: Path, fuente: str = "") -> Iterator[Contrato]:
    """Lee un .atom/.xml o un .zip con varios .atom dentro."""
    ruta = Path(ruta)
    if zipfile.is_zipfile(ruta):
        with zipfile.ZipFile(ruta) as z:
            for nombre in sorted(z.namelist()):
                if nombre.lower().endswith((".atom", ".xml")):
                    with z.open(nombre) as f:
                        yield from leer_atom(f, fuente)
    else:
        with open(ruta, "rb") as f:
            yield from leer_atom(f, fuente)


# ---------------------------------------------------------------------------
# Descargas

def urls_historico(url_atom: str, anos: int, hoy: date | None = None) -> list[str]:
    """ZIP de los años completos anteriores y de los meses ya cerrados de este año.

    'licitaciones...Completo3.atom' -> '..._2024.zip', ..., '..._202601.zip'
    """
    hoy = hoy or date.today()
    base = url_atom[: -len(".atom")] if url_atom.endswith(".atom") else url_atom
    urls = [f"{base}_{ano}.zip" for ano in range(hoy.year - anos, hoy.year)]
    urls += [f"{base}_{hoy.year}{mes:02d}.zip" for mes in range(1, hoy.month)]
    return urls


class Red:
    def __init__(self, timeout: float = 120, reintentos: int = 3):
        self.timeout = timeout
        self.reintentos = reintentos
        self.sesion = requests.Session()
        self.sesion.headers["User-Agent"] = "vigilante-licitaciones/1.0 (datos abiertos PLACSP)"

    def _get(self, url: str, **kw) -> requests.Response:
        ultimo = None
        for intento in range(self.reintentos):
            try:
                r = self.sesion.get(url, timeout=self.timeout, **kw)
                if r.status_code == 404:
                    r.raise_for_status()
                if r.status_code >= 500:
                    raise requests.HTTPError(f"{r.status_code} en {url}", response=r)
                r.raise_for_status()
                return r
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    raise
                ultimo = e
            except requests.RequestException as e:
                ultimo = e
            time.sleep(2 ** (intento + 1))
        raise ultimo  # type: ignore[misc]

    def obtener(self, url: str) -> bytes:
        return self._get(url).content

    def descargar_documento(self, url: str, carpeta: Path, nombre: str) -> Path:
        """Descarga un pliego a la carpeta. Si ya existe uno con ese nombre, no lo repite."""
        r = self._get(url)
        if "." not in nombre[-6:]:
            tipo = r.headers.get("Content-Type", "")
            nombre += ".pdf" if "pdf" in tipo or r.content[:4] == b"%PDF" else ""
        destino = carpeta / nombre
        if not destino.exists():
            destino.write_bytes(r.content)
        return destino

    def descargar(self, url: str, destino: Path) -> Path:
        """Descarga a destino. Si ya está descargado, no lo repite."""
        if destino.exists() and destino.stat().st_size > 0:
            return destino
        destino.parent.mkdir(parents=True, exist_ok=True)
        parcial = destino.with_suffix(destino.suffix + ".part")
        with self._get(url, stream=True) as r, open(parcial, "wb") as f:
            for trozo in r.iter_content(1 << 20):
                f.write(trozo)
        parcial.replace(destino)
        return destino


def leer_feed_reciente(
    url: str,
    desde: datetime,
    fuente: str,
    obtener: Callable[[str], bytes],
    max_paginas: int = 400,
) -> tuple[list[Contrato], int]:
    """Recorre el feed vivo hacia atrás hasta llegar a `desde`.

    Devuelve los contratos actualizados desde esa fecha (solo la versión más
    reciente de cada uno) y el número de páginas leídas.
    """
    vistos: dict[str, Contrato] = {}
    paginas = 0
    while url and paginas < max_paginas:
        siguiente: dict = {}
        contratos = list(leer_atom(obtener(url), fuente, siguiente))
        paginas += 1
        for c in contratos:
            if c.actualizado and c.actualizado < desde:
                continue
            previo = vistos.get(c.id)
            if previo is None or (c.actualizado or datetime.min) > (previo.actualizado or datetime.min):
                vistos[c.id] = c
        fechas = [c.actualizado for c in contratos if c.actualizado]
        if not fechas or min(fechas) < desde:
            break
        url = siguiente.get("url", "")
    return list(vistos.values()), paginas


def hace(dias: float, ahora: datetime | None = None) -> datetime:
    return (ahora or datetime.now()) - timedelta(days=dias)
