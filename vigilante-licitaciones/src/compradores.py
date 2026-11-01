"""Histórico: qué ayuntamientos contratan paellas, cuándo, por cuánto y a quién.

Genera dos cosas:
- un Excel con una pestaña por apartado del análisis;
- el informe HTML para leer (ver informe_compradores.py).
Ambos van a historial_contratos_menores/ (ver vigilante.salida_historial).

Solo cuentan los contratos que hablan de paellas (ver filtros.puntuar). Se
rehace entero en cada ejecución.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from comun import DATOS, MESES, guardar_libro, normalizar
from clasificar import SERVICIO, categoria, es_ayuntamiento, nombre_municipio
from filtros import dir3_ayuntamiento, en_zona, municipio, provincia, puntuar
from placsp import ESTADOS, Contrato

RUTA = DATOS / "compradores.xlsx"
MESES_NOMBRE = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                "septiembre", "octubre", "noviembre", "diciembre"]

PRIORIDADES = {
    1: "Cliente recurrente: ha contratado paellas en 2 o más años distintos",
    2: "Ha contratado paellas en los 2 últimos años",
    3: "Contrató paellas hace más de 2 años",
}


@dataclass
class Hallazgo:
    contrato: Contrato
    encaje: str
    motivo: str
    municipio: str
    dir3: str
    provincia: str = ""
    categoria: str = SERVICIO
    es_ayto: bool = True

    @property
    def principal(self) -> bool:
        """Servicio de paella contratado por un ayuntamiento: lo que cuenta en los informes."""
        return self.categoria == SERVICIO and self.es_ayto

    @property
    def fecha(self) -> date | None:
        c = self.contrato
        if c.fecha_adjudicacion:
            return c.fecha_adjudicacion
        if c.plazo:
            return c.plazo.date()
        return c.actualizado.date() if c.actualizado else None

    @property
    def importe(self) -> float | None:
        c = self.contrato
        return c.importe_adjudicacion if c.importe_adjudicacion is not None else c.importe

    @property
    def via(self) -> str:
        return "Contrato menor" if self.contrato.fuente == "menores" else "Licitación"

    @property
    def gigante(self) -> bool:
        texto = normalizar(self.contrato.texto)
        return any(p in texto for p in ("gigant", "gegant", "monumental"))

    @property
    def objeto(self) -> str:
        return self.contrato.objeto or self.contrato.titulo


def filtrar(contratos: Iterable[Contrato], config: dict) -> list[Hallazgo]:
    """Se queda con la última versión de cada contrato de la zona que encaja."""
    hallazgos: dict[str, Hallazgo] = {}
    for c in contratos:
        if c.estado == "ANUL" or not en_zona(c, config["provincias"]):
            continue
        resultado = puntuar(c, config)
        if not resultado:
            continue
        previo = hallazgos.get(c.id)
        if previo and (c.actualizado or datetime.min) <= (previo.contrato.actualizado or datetime.min):
            continue
        hallazgos[c.id] = Hallazgo(c, resultado[0], resultado[1], nombre_municipio(municipio(c)),
                                   dir3_ayuntamiento(c, config["provincias"]),
                                   provincia(c, config["provincias"]),
                                   categoria(c.objeto or c.titulo), es_ayuntamiento(c.organo))
    return list(hallazgos.values())


# ---------------------------------------------------------------------------
# Análisis

def _redondo(valor: float | None) -> float | None:
    return round(valor, 2) if valor is not None else None


def _mes_envio(mes: int, antelacion: int) -> int:
    return (mes - 1 - antelacion) % 12 + 1


def resumen_general(hallazgos: list[Hallazgo]) -> dict:
    importes = [h.importe for h in hallazgos if h.importe is not None]
    fechas = [h.fecha for h in hallazgos if h.fecha]
    municipios = {h.dir3 or h.municipio for h in hallazgos}
    return {
        "contratos": len(hallazgos),
        "ayuntamientos": len(municipios),
        "contratos_menores": sum(h.via == "Contrato menor" for h in hallazgos),
        "licitaciones": sum(h.via == "Licitación" for h in hallazgos),
        "desde": min(fechas) if fechas else None,
        "hasta": max(fechas) if fechas else None,
        "importe_total": _redondo(sum(importes)) if importes else None,
        "importe_medio": _redondo(statistics.mean(importes)) if importes else None,
        "importe_mediana": _redondo(statistics.median(importes)) if importes else None,
        "importe_min": _redondo(min(importes)) if importes else None,
        "importe_max": _redondo(max(importes)) if importes else None,
        "con_importe": len(importes),
    }


def resumen_municipios(hallazgos: list[Hallazgo], antelacion: int = 2, hoy: date | None = None,
                       orden: str = "prioridad") -> list[dict]:
    """Un resumen por ayuntamiento.

    orden="prioridad": primero los clientes recurrentes (para el calendario de envíos).
    orden="demanda": primero los que más contratos de paellas han hecho, sumando todas las vías.
    """
    hoy = hoy or date.today()
    grupos: dict[str, list[Hallazgo]] = defaultdict(list)
    for h in hallazgos:
        grupos[h.dir3 or normalizar(h.municipio) or normalizar(h.contrato.organo)].append(h)

    filas = []
    for grupo in grupos.values():
        grupo.sort(key=lambda h: h.fecha or date.min, reverse=True)
        anos = sorted({h.fecha.year for h in grupo if h.fecha})
        meses = Counter(h.fecha.month for h in grupo if h.fecha)
        mes_habitual = meses.most_common(1)[0][0] if meses else None
        importes = [h.importe for h in grupo if h.importe is not None]
        empresas = Counter(a for h in grupo for a in h.contrato.adjudicatarios)
        ultimo = grupo[0]
        if len(anos) >= 2:
            prioridad = 1
        elif anos and anos[-1] >= hoy.year - 2:
            prioridad = 2
        else:
            prioridad = 3
        filas.append({
            "prioridad": prioridad,
            "municipio": next((h.municipio for h in grupo if h.municipio), ultimo.contrato.organo),
            "provincia": next((h.provincia for h in grupo if h.provincia), ""),
            "contratos": len(grupo),
            "contratos_menores": sum(h.via == "Contrato menor" for h in grupo),
            "licitaciones": sum(h.via == "Licitación" for h in grupo),
            "anos": ", ".join(str(a) for a in anos),
            "importe_medio": _redondo(statistics.mean(importes)) if importes else None,
            "importe_min": _redondo(min(importes)) if importes else None,
            "importe_max": _redondo(max(importes)) if importes else None,
            "importe_total": _redondo(sum(importes)) if importes else None,
            "mes_habitual": MESES_NOMBRE[mes_habitual - 1] if mes_habitual else "",
            "meses": ", ".join(f"{MESES[m - 1]} ({n})" for m, n in sorted(meses.items())),
            "enviar_propuesta_en": MESES_NOMBRE[_mes_envio(mes_habitual, antelacion) - 1] if mes_habitual else "",
            "ultimo_contrato": ultimo.fecha,
            "ultimo_importe": _redondo(ultimo.importe),
            "ultimo_objeto": ultimo.objeto,
            "empresa_habitual": empresas.most_common(1)[0][0] if empresas else "",
            "empresas": "; ".join(sorted(empresas)),
            "via": ", ".join(sorted({h.via for h in grupo})),
            "dir3_ayto": next((h.dir3 for h in grupo if h.dir3), ""),
            "_mes_envio": _mes_envio(mes_habitual, antelacion) if mes_habitual else None,
        })
    if orden == "demanda":
        filas.sort(key=lambda f: (-f["contratos"], -(f["importe_total"] or 0), f["prioridad"], f["municipio"]))
    else:
        filas.sort(key=lambda f: (f["prioridad"], -f["contratos"], -(f["importe_medio"] or 0), f["municipio"]))
    return filas


def resumen_meses(hallazgos: list[Hallazgo]) -> list[dict]:
    por_mes: dict[int, list[Hallazgo]] = defaultdict(list)
    for h in hallazgos:
        if h.fecha:
            por_mes[h.fecha.month].append(h)
    filas = []
    for mes in range(1, 13):
        grupo = por_mes.get(mes, [])
        importes = [h.importe for h in grupo if h.importe is not None]
        filas.append({
            "mes": MESES_NOMBRE[mes - 1],
            "contratos": len(grupo),
            "importe_total": _redondo(sum(importes)) if importes else None,
            "importe_medio": _redondo(statistics.mean(importes)) if importes else None,
            "municipios": "; ".join(sorted({h.municipio for h in grupo if h.municipio})),
        })
    return filas


def calendario_envios(municipios: list[dict]) -> list[dict]:
    """Mes a mes, a qué ayuntamientos conviene enviar la propuesta."""
    por_mes: dict[int, list[dict]] = defaultdict(list)
    for f in municipios:
        if f["_mes_envio"]:
            por_mes[f["_mes_envio"]].append(f)
    return [{
        "enviar_en": MESES_NOMBRE[mes - 1],
        "ayuntamientos": len(por_mes.get(mes, [])),
        "municipios": "; ".join(f"{f['municipio']} (contrata en {f['mes_habitual']})"
                                for f in sorted(por_mes.get(mes, []), key=lambda f: f["prioridad"])),
    } for mes in range(1, 13)]


def resumen_provincias(hallazgos: list[Hallazgo]) -> list[dict]:
    grupos: dict[str, list[Hallazgo]] = defaultdict(list)
    for h in hallazgos:
        grupos[h.provincia or "Sin identificar"].append(h)
    filas = []
    for nombre, grupo in grupos.items():
        importes = [h.importe for h in grupo if h.importe is not None]
        filas.append({
            "provincia": nombre,
            "contratos": len(grupo),
            "ayuntamientos": len({h.dir3 or h.municipio for h in grupo}),
            "importe_total": _redondo(sum(importes)) if importes else None,
            "importe_medio": _redondo(statistics.mean(importes)) if importes else None,
        })
    filas.sort(key=lambda f: -f["contratos"])
    return filas


def resumen_competencia(hallazgos: list[Hallazgo]) -> list[dict]:
    grupos: dict[str, list[Hallazgo]] = defaultdict(list)
    for h in hallazgos:
        for a in h.contrato.adjudicatarios:
            grupos[a].append(h)
    filas = []
    for empresa, g in grupos.items():
        importes = [h.importe for h in g if h.importe is not None]
        filas.append({
            "empresa": empresa,
            "contratos": len(g),
            "importe_total": _redondo(sum(importes)) if importes else None,
            "importe_medio": _redondo(statistics.mean(importes)) if importes else None,
            "municipios": "; ".join(sorted({h.municipio for h in g if h.municipio})),
            "ultimo": max((h.fecha for h in g if h.fecha), default=None),
        })
    filas.sort(key=lambda f: (-f["contratos"], -(f["importe_total"] or 0)))
    return filas


def filas_contratos(hallazgos: list[Hallazgo]) -> list[dict]:
    orden = sorted(hallazgos, key=lambda h: h.fecha or date.min, reverse=True)
    return [{
        "fecha": h.fecha,
        "municipio": h.municipio,
        "provincia": h.provincia,
        "objeto": h.objeto,
        "importe": _redondo(h.importe),
        "empresa": "; ".join(h.contrato.adjudicatarios),
        "via": h.via,
        "paella_gigante": "sí" if h.gigante else "",
        "estado": ESTADOS.get(h.contrato.estado, h.contrato.estado),
        "organo": h.contrato.organo,
        "dir3_ayto": h.dir3,
        "enlace": h.contrato.enlace,
        "id": h.contrato.id,
    } for h in orden]


def analizar(hallazgos: list[Hallazgo], antelacion: int = 2, hoy: date | None = None,
             orden: str = "prioridad") -> dict:
    municipios = resumen_municipios(hallazgos, antelacion, hoy, orden)
    return {
        "general": resumen_general(hallazgos),
        "municipios": municipios,
        "meses": resumen_meses(hallazgos),
        "calendario": calendario_envios(municipios),
        "provincias": resumen_provincias(hallazgos),
        "competencia": resumen_competencia(hallazgos),
        "contratos": filas_contratos(hallazgos),
        "antelacion": antelacion,
        "orden": orden,
    }


# ---------------------------------------------------------------------------
# Excel

FORMATO_EUROS = '#,##0.00 "€"'
COLUMNAS_EUROS = ("importe", "importe_medio", "importe_min", "importe_max", "importe_total", "ultimo_importe")
COLUMNAS_FECHA = ("fecha", "ultimo_contrato", "ultimo")


def _pestana(libro: Workbook, titulo: str, filas: list[dict], primera: bool = False) -> None:
    hoja = libro.active if primera else libro.create_sheet()
    hoja.title = titulo
    filas = [{k: v for k, v in f.items() if not k.startswith("_")} for f in filas]
    if not filas:
        hoja.append(["(sin resultados)"])
        return
    columnas = list(filas[0])
    hoja.append(columnas)
    for celda in hoja[1]:
        celda.font = Font(bold=True)
        celda.fill = PatternFill("solid", fgColor="DDEBF7")
    for fila in filas:
        hoja.append([fila[c] for c in columnas])
    for i, columna in enumerate(columnas, start=1):
        largo = max(len(str(columna)), *(min(len(str(f[columna] or "")), 60) for f in filas))
        hoja.column_dimensions[get_column_letter(i)].width = largo + 2
        formato = FORMATO_EUROS if columna in COLUMNAS_EUROS else "dd/mm/yyyy" if columna in COLUMNAS_FECHA else None
        if formato:
            for (celda,) in hoja.iter_rows(min_row=2, min_col=i, max_col=i):
                celda.number_format = formato
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = hoja.dimensions


def guardar(hallazgos: list[Hallazgo], antelacion: int, ruta: Path | None = None,
            hoy: date | None = None, orden: str = "prioridad", otros: list[Hallazgo] | None = None) -> dict:
    ruta = ruta or RUTA
    analisis = analizar(hallazgos, antelacion, hoy, orden)
    general = analisis["general"]
    libro = Workbook()
    municipios = analisis["municipios"]
    if not (general["contratos_menores"] and general["licitaciones"]):
        municipios = [{k: v for k, v in f.items() if k not in ("contratos_menores", "licitaciones")}
                      for f in municipios]
    _pestana(libro, "ayuntamientos", municipios, primera=True)
    _pestana(libro, "calendario_envios", analisis["calendario"])
    _pestana(libro, "por_mes", analisis["meses"])
    _pestana(libro, "por_provincia", analisis["provincias"])
    _pestana(libro, "competencia", analisis["competencia"])
    _pestana(libro, "contratos", analisis["contratos"])
    _pestana(libro, "resumen", [{"dato": k, "valor": v} for k, v in general.items()])
    if otros is not None:
        filas = filas_contratos(otros)
        for fila, h in zip(filas, sorted(otros, key=lambda h: h.fecha or date.min, reverse=True)):
            fila["tipo"] = h.categoria if h.es_ayto else f"{h.categoria} (no es ayuntamiento)"
        _pestana(libro, "otros_contratos", [{"tipo": f.pop("tipo"), **f} for f in filas])
    guardar_libro(libro, ruta)
    return {
        "contratos": general["contratos"],
        "municipios": general["ayuntamientos"],
        "prioridad_1": sum(f["prioridad"] == 1 for f in analisis["municipios"]),
        "analisis": analisis,
    }
