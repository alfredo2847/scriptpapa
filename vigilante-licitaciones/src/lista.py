"""La lista para leer: LISTA_LICITACIONES.html (se abre con doble clic en el navegador).

Se rehace en cada búsqueda a partir de datos/licitaciones.xlsx. Arriba, las
licitaciones de paellas con plazo abierto, de mayor a menor valoración; debajo,
las que has marcado PRESENTADA y las ya vencidas de las últimas semanas.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from html import escape
from pathlib import Path

from comun import RAIZ

RUTA = RAIZ / "LISTA_LICITACIONES.html"
SEMANAS_VENCIDAS = 6


def _fecha(valor) -> datetime | None:
    return valor if isinstance(valor, datetime) else None


def _euros(valor) -> str:
    if not isinstance(valor, (int, float)):
        return "—"
    return f"{valor:,.0f} €".replace(",", ".")


def _fila(f: dict, ahora: datetime) -> str:
    plazo = _fecha(f.get("plazo"))
    if plazo:
        dias = (plazo.date() - ahora.date()).days
        cuando = f"{plazo:%d/%m/%Y %H:%M}"
        quedan = "vencida" if plazo < ahora else ("hoy" if dias == 0 else f"{dias} día{'s' if dias != 1 else ''}")
        urgente = " urgente" if plazo >= ahora and dias <= 3 else ""
    else:
        cuando, quedan, urgente = "sin publicar", "", ""
    valoracion = f.get("valoracion")
    nota = f'<span class="nota">{valoracion}</span>' if isinstance(valoracion, (int, float)) else "—"
    enlaces = []
    if f.get("enlace"):
        enlaces.append(f'<a href="{escape(str(f["enlace"]))}">Ver en la Plataforma</a>')
    if f.get("carpeta") and Path(str(f["carpeta"])).is_absolute():
        enlaces.append(f'<a href="{escape(Path(str(f["carpeta"])).as_uri())}">Abrir carpeta</a>')
    seguimiento = escape(str(f.get("seguimiento") or ""))
    notas = escape(str(f.get("notas") or ""))
    return (
        "<tr>"
        f"<td class='num'>{nota}</td>"
        f"<td><b>{escape(str(f.get('municipio') or f.get('organo') or ''))}</b>"
        f"<div class='peq'>{escape(str(f.get('organo') or ''))}</div></td>"
        f"<td>{escape(str(f.get('objeto') or ''))}"
        + (f"<div class='peq'>Notas: {notas}</div>" if notas else "")
        + "</td>"
        f"<td class='num'>{_euros(f.get('importe'))}</td>"
        f"<td class='plazo{urgente}'>{cuando}<div class='peq'>{quedan}</div></td>"
        f"<td><span class='seg'>{seguimiento}</span></td>"
        f"<td>{' · '.join(enlaces)}</td>"
        "</tr>"
    )


def _tabla(titulo: str, filas: list[dict], ahora: datetime, vacio: str) -> str:
    cabecera = ("<tr><th>Valoración</th><th>Municipio</th><th>Objeto</th><th>Importe</th>"
                "<th>Plazo</th><th>Seguimiento</th><th></th></tr>")
    cuerpo = "".join(_fila(f, ahora) for f in filas) or f"<tr><td colspan='7' class='vacio'>{vacio}</td></tr>"
    return f"<h2>{titulo} <span class='cuenta'>({len(filas)})</span></h2><table>{cabecera}{cuerpo}</table>"


def generar(existentes: dict[str, dict], ahora: datetime, aviso: str = "", ruta: Path | None = None) -> Path:
    ruta = ruta or RUTA
    abiertas, presentadas, vencidas = [], [], []
    for f in existentes.values():
        plazo = _fecha(f.get("plazo"))
        if f.get("seguimiento") == "DESCARTADA":
            continue
        if f.get("seguimiento") == "PRESENTADA":
            presentadas.append(f)
        elif plazo and plazo < ahora:
            if plazo >= ahora - timedelta(weeks=SEMANAS_VENCIDAS):
                vencidas.append(f)
        else:
            abiertas.append(f)

    def por_valoracion(f):
        v = f.get("valoracion")
        return (-(v if isinstance(v, (int, float)) else -1), _fecha(f.get("plazo")) or datetime.max)

    abiertas.sort(key=por_valoracion)
    presentadas.sort(key=lambda f: _fecha(f.get("plazo")) or datetime.max)
    vencidas.sort(key=lambda f: _fecha(f.get("plazo")) or datetime.min, reverse=True)

    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Licitaciones de paellas</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #222; background: #fff; }}
h1 {{ margin-bottom: 4px; }} h2 {{ margin-top: 32px; }}
.sub {{ color: #666; }} .aviso {{ background: #fff3cd; padding: 8px 12px; border-radius: 6px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #f2f6fb; }} .num {{ text-align: right; white-space: nowrap; }}
.nota {{ display: inline-block; min-width: 2.2em; text-align: center; font-weight: bold;
        background: #e3f1e3; border-radius: 4px; padding: 2px 4px; }}
.peq {{ font-size: 0.85em; color: #666; }} .plazo {{ white-space: nowrap; }}
.urgente {{ color: #b00020; font-weight: bold; }} .cuenta {{ color: #888; font-weight: normal; }}
.vacio {{ color: #666; font-style: italic; }} .seg {{ font-size: 0.85em; }}
</style></head><body>
<h1>Licitaciones de paellas</h1>
<div class="sub">Comunitat Valenciana · actualizada el {ahora:%d/%m/%Y a las %H:%M}</div>
{f'<p class="aviso">{escape(aviso)}</p>' if aviso else ''}
{_tabla("Abiertas", abiertas, ahora, "Ahora mismo no hay licitaciones de paellas abiertas. El vigilante sigue mirando y avisará cuando salga alguna.")}
{_tabla("Presentadas", presentadas, ahora, "Ninguna marcada como PRESENTADA.")}
{_tabla(f"Vencidas (últimas {SEMANAS_VENCIDAS} semanas)", vencidas, ahora, "Ninguna.")}
<p class="peq">Para marcar ME INTERESA, PRESENTADA o DESCARTADA, o escribir notas, usa datos\\licitaciones.xlsx.
La valoración y los datos de cada una están en 00_RESUMEN.txt de su carpeta.</p>
</body></html>
"""
    ruta.write_text(html, encoding="utf-8")
    return ruta
