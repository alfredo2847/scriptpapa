"""Informe para leer del historial (ANALISIS_CONTRATOS_MENORES.html).

Ordenado para decidir a quién y cuándo enviar la propuesta:
1. Resumen en cifras.
2. Calendario de envíos: mes a mes, a qué ayuntamientos escribir.
3. Ayuntamientos que contratan paellas (ranking con presupuestos y fechas).
4. En qué meses se contratan.
5. Por provincia.
6. Competencia.
7. Todos los contratos.
8. Limitaciones de los datos.
"""

from __future__ import annotations

from datetime import date, datetime
from html import escape
from pathlib import Path

from comun import RAIZ
from compradores import PRIORIDADES

RUTA = RAIZ / "ANALISIS_COMPRADORES.html"


def _e(valor) -> str:
    return escape(str(valor if valor is not None else ""))


def _euros(valor) -> str:
    if not isinstance(valor, (int, float)):
        return "—"
    return f"{valor:,.0f} €".replace(",", ".")


def _fecha(valor) -> str:
    return f"{valor:%d/%m/%Y}" if isinstance(valor, (date, datetime)) else "—"


def _tabla(cabecera: list[str], filas: list[list[str]], vacio: str = "Sin datos.", clases: list[str] | None = None) -> str:
    clases = clases or [""] * len(cabecera)
    th = "".join(f"<th class='{c}'>{h}</th>" for h, c in zip(cabecera, clases))
    if not filas:
        return f"<table><tr>{th}</tr><tr><td colspan='{len(cabecera)}' class='vacio'>{vacio}</td></tr></table>"
    cuerpo = "".join("<tr>" + "".join(f"<td class='{c}'>{v}</td>" for v, c in zip(f, clases)) + "</tr>"
                     for f in filas)
    return f"<div class='tabla'><table><tr>{th}</tr>{cuerpo}</table></div>"


def _cifra(valor: str, texto: str) -> str:
    return f"<div class='cifra'><div class='valor'>{valor}</div><div class='texto'>{texto}</div></div>"


def generar(analisis: dict, ahora: datetime, ruta: Path | None = None, avisos: list[str] | None = None,
            titulo: str = "Historial de contratos menores de paellas") -> Path:
    ruta = ruta or RUTA
    g = analisis["general"]
    municipios = analisis["municipios"]
    antelacion = analisis["antelacion"]
    num = ["", "num"]

    periodo = f"{_fecha(g['desde'])} a {_fecha(g['hasta'])}" if g["desde"] else "—"
    cifras = "".join([
        _cifra(str(g["contratos"]), "contratos de paellas"),
        _cifra(str(g["ayuntamientos"]), "ayuntamientos"),
        _cifra(str(sum(f["prioridad"] == 1 for f in municipios)), "clientes recurrentes"),
        _cifra(_euros(g["importe_mediana"]), "importe típico (mediana)"),
        _cifra(f"{_euros(g['importe_min'])} – {_euros(g['importe_max'])}", "rango de importes"),
        _cifra(_euros(g["importe_total"]), "importe total"),
    ])

    calendario = _tabla(
        ["Enviar en", "Nº", "Ayuntamientos (y cuándo contratan)"],
        [[f"<b>{_e(c['enviar_en']).capitalize()}</b>", str(c["ayuntamientos"]), _e(c["municipios"]) or "—"]
         for c in analisis["calendario"]],
        clases=["", "num", ""],
    )

    mixto = bool(g["contratos_menores"] and g["licitaciones"])
    demanda = analisis.get("orden") == "demanda"
    cab = ["#"] if demanda else []
    cab += ["Prior.", "Ayuntamiento", "Prov.", "Contratos"]
    cab += ["Menores", "Licit."] if mixto else []
    cab += ["Años", "Importe medio", "Mín – máx", "Mes habitual", "Enviar en", "Último contrato", "Empresa habitual"]
    clases_r = (["num"] if demanda else []) + ["", "", "", "num"] + (["num", "num"] if mixto else []) + \
        ["", "num", "num", "", "", "num", ""]
    filas_r = []
    for n, f in enumerate(municipios, start=1):
        fila = [str(n)] if demanda else []
        fila += [f"<span class='p p{f['prioridad']}'>{f['prioridad']}</span>",
                 f"<b>{_e(f['municipio'])}</b><div class='peq'>{_e(f['ultimo_objeto'])}</div>",
                 _e(f["provincia"]), f"<b>{f['contratos']}</b>"]
        fila += [str(f["contratos_menores"]), str(f["licitaciones"])] if mixto else []
        fila += [_e(f["anos"]), _euros(f["importe_medio"]),
                 f"{_euros(f['importe_min'])} – {_euros(f['importe_max'])}", _e(f["mes_habitual"]),
                 f"<b>{_e(f['enviar_propuesta_en'])}</b>",
                 f"{_fecha(f['ultimo_contrato'])}<div class='peq'>{_euros(f['ultimo_importe'])}</div>",
                 _e(f["empresa_habitual"]) or "—"]
        filas_r.append(fila)
    ranking = _tabla(cab, filas_r, vacio="No se ha encontrado ningún contrato de paellas.", clases=clases_r)

    maximo = max((m["contratos"] for m in analisis["meses"]), default=0) or 1
    meses = _tabla(
        ["Mes", "Contratos", "", "Importe medio", "Ayuntamientos"],
        [[_e(m["mes"]).capitalize(), str(m["contratos"]),
          f"<div class='barra' style='width:{round(100 * m['contratos'] / maximo)}%'></div>",
          _euros(m["importe_medio"]), _e(m["municipios"]) or "—"]
         for m in analisis["meses"]],
        clases=["", "num", "col-barra", "num", "peq"],
    )

    provincias = _tabla(
        ["Provincia", "Contratos", "Ayuntamientos", "Importe medio", "Importe total"],
        [[_e(p["provincia"]), str(p["contratos"]), str(p["ayuntamientos"]), _euros(p["importe_medio"]),
          _euros(p["importe_total"])] for p in analisis["provincias"]],
        clases=["", "num", "num", "num", "num"],
    )

    competencia = _tabla(
        ["Empresa", "Contratos", "Importe medio", "Importe total", "Ayuntamientos", "Último"],
        [[f"<b>{_e(c['empresa'])}</b>", str(c["contratos"]), _euros(c["importe_medio"]),
          _euros(c["importe_total"]), _e(c["municipios"]), _fecha(c["ultimo"])]
         for c in analisis["competencia"]],
        vacio="Los contratos encontrados no indican la empresa adjudicataria.",
        clases=["", "num", "num", "num", "peq", "num"],
    )

    contratos = _tabla(
        ["Fecha", "Ayuntamiento", "Objeto", "Importe", "Empresa", "Vía", ""],
        [[_fecha(c["fecha"]), _e(c["municipio"]),
          _e(c["objeto"]) + (" <span class='etq'>gigante</span>" if c["paella_gigante"] else ""),
          _euros(c["importe"]), _e(c["empresa"]) or "—", _e(c["via"]),
          f"<a href='{_e(c['enlace'])}'>ver</a>" if c["enlace"] else ""]
         for c in analisis["contratos"]],
        clases=["num", "", "", "num", "peq", "peq", ""],
    )

    bloque_calendario = (
        "<h2>{n}. Calendario de envíos de la propuesta</h2>"
        f"<p>Cada ayuntamiento aparece en el mes en que conviene escribirle: {antelacion} meses antes del mes "
        f"en que suele contratar las paellas.</p>{calendario}"
    )
    titulo_ranking = "Ayuntamientos que más contratan paellas" if demanda else "Ayuntamientos que contratan paellas"
    explicacion = ("<p>Ordenados por número de contratos de paellas, sumando contratos menores y licitaciones.</p>"
                   if demanda else "")
    leyenda_html = "".join(f"<li><span class='p p{n}'>{n}</span> {escape(t)}</li>" for n, t in PRIORIDADES.items())
    bloque_ranking = (f"<h2>{{n}}. {titulo_ranking}</h2>{explicacion}"
                      f"<ul class='peq'>{leyenda_html}</ul>{ranking}")
    orden_bloques = [bloque_ranking, bloque_calendario] if demanda else [bloque_calendario, bloque_ranking]
    bloques = "\n\n".join(b.replace("{n}", str(i)) for i, b in enumerate(orden_bloques, start=1))

    leyenda = "".join(f"<li><span class='p p{n}'>{n}</span> {escape(t)}</li>" for n, t in PRIORIDADES.items())
    avisos_html = "".join(f"<p class='aviso'>{escape(a)}</p>" for a in (avisos or []))

    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)}</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px auto; max-width: 1200px; padding: 0 16px;
       color: #222; background: #fff; line-height: 1.4; }}
h1 {{ margin-bottom: 4px; }} h2 {{ margin-top: 40px; border-bottom: 2px solid #e3e9f2; padding-bottom: 4px; }}
.sub, .peq {{ color: #666; }} .peq {{ font-size: 0.85em; }}
.cifras {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 20px 0; }}
.cifra {{ background: #f4f7fb; border-radius: 8px; padding: 12px 14px; }}
.cifra .valor {{ font-size: 1.5em; font-weight: 600; }} .cifra .texto {{ color: #555; font-size: 0.9em; }}
.tabla {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #e2e2e2; padding: 7px 8px; text-align: left; vertical-align: top; }}
th {{ background: #f2f6fb; font-weight: 600; }} .num {{ text-align: right; white-space: nowrap; }}
.col-barra {{ width: 30%; }} .barra {{ background: #4a7fc1; height: 14px; border-radius: 3px; min-width: 2px; }}
.p {{ display: inline-block; width: 1.6em; text-align: center; border-radius: 4px; font-weight: 600; }}
.p1 {{ background: #c8e6c9; }} .p2 {{ background: #fff3c4; }} .p3 {{ background: #eceff1; }}
.etq {{ font-size: 0.75em; background: #ffe0b2; border-radius: 3px; padding: 1px 4px; }}
.aviso {{ background: #fff3cd; padding: 8px 12px; border-radius: 6px; }}
.vacio {{ color: #666; font-style: italic; }} ul {{ padding-left: 20px; }}
</style></head><body>
<h1>{escape(titulo)}</h1>
<div class="sub">Comunitat Valenciana · contratos adjudicados entre el {periodo} · informe del {ahora:%d/%m/%Y}</div>
{avisos_html}
<div class="cifras">{cifras}</div>
<p class="peq">{g['contratos_menores']} contratos menores y {g['licitaciones']} licitaciones.
Importes sin IVA; {g['con_importe']} de {g['contratos']} contratos indican importe.</p>

{bloques}

<h2>3. En qué meses se contratan</h2>
<p class="peq">Fecha de adjudicación del contrato, que suele ser unas semanas antes de la fiesta.</p>
{meses}

<h2>4. Por provincia</h2>
{provincias}

<h2>5. Competencia</h2>
{competencia}

<h2>6. Todos los contratos</h2>
{contratos}

<h2>Limitaciones de los datos</h2>
<ul class="peq">
<li>Solo aparecen los ayuntamientos que publican sus contratos en la Plataforma de Contratación del Sector Público
(directamente o a través de la Generalitat). Algunos municipios pequeños publican en su propia web.</li>
<li>Los contratos menores de menos de 5.000 € que se pagan por anticipo de caja fija no tienen obligación de publicarse,
así que muchas paellas pequeñas no salen aquí.</li>
<li>Solo cuentan los contratos cuyo título u objeto menciona paellas. Una paella incluida en un contrato
genérico de fiestas sin mencionarla no aparece.</li>
<li>La fecha es la de adjudicación; la fiesta suele ser unas semanas después.</li>
</ul>
</body></html>
"""
    ruta.write_text(html, encoding="utf-8")
    return ruta
