"""Resume los campos y botones de las capturas HTML del envío de referencia.

    python src/main.py analizar-capturas [--carpeta capturas/referencia_<fecha>]

Lee los .html que guardó `grabar` (no necesita navegador) y escribe en
huellas/analisis_<fecha>.txt una lista corta por pantalla: campos (input,
textarea, select y componentes con role/formcontrolname), botones y
etiquetas, con los atributos útiles para escribir selectores. Ese texto es el
que se usa para completar huellas/rec.yaml.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from comun import RAIZ, marca_tiempo
from motor import CARPETA_HUELLAS

ATRIBUTOS = ("id", "name", "formcontrolname", "type", "role", "aria-label", "placeholder",
             "data-testid", "for", "href")
CAMPOS = {"input", "textarea", "select"}
ROLES_CAMPO = {"combobox", "listbox", "option", "radio", "checkbox", "textbox", "searchbox"}
CONTENEDORES_TEXTO = {"button", "label", "a", "option", "legend", "h1", "h2", "h3", "th"}


def _limpio(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


class _Lector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elementos: list[dict] = []
        self._abiertos: list[dict] = []
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg"):
            self._ignorar += 1
            return
        a = {k: (v or "") for k, v in attrs}
        interesa = (
            tag in CAMPOS
            or tag in CONTENEDORES_TEXTO
            or a.get("role") in ROLES_CAMPO | {"button"}
            or "formcontrolname" in a
            or tag.startswith(("ng-", "mat-", "p-")) and ("formcontrolname" in a or "id" in a)
        )
        if not interesa:
            return
        el = {"tag": tag, "attrs": {k: a[k] for k in ATRIBUTOS if a.get(k)},
              "clase": " ".join(a.get("class", "").split()[:3]), "texto": ""}
        self.elementos.append(el)
        if tag not in CAMPOS:
            self._abiertos.append(el)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg"):
            self._ignorar = max(0, self._ignorar - 1)
            return
        for i in range(len(self._abiertos) - 1, -1, -1):
            if self._abiertos[i]["tag"] == tag:
                del self._abiertos[i:]
                break

    def handle_data(self, data):
        if self._ignorar:
            return
        for el in self._abiertos:
            if len(el["texto"]) < 120:
                el["texto"] = _limpio(el["texto"] + " " + data)[:120]


def resumir_html(html: str) -> list[str]:
    lector = _Lector()
    lector.feed(html)
    lineas, vistos = [], set()
    for el in lector.elementos:
        tag, attrs, texto = el["tag"], el["attrs"], el["texto"]
        if tag in ("h1", "h2", "h3", "legend", "th", "label") and not attrs and texto:
            linea = f"  [{tag}] {texto}"
        elif tag == "a" and not texto and not attrs.get("role"):
            continue
        else:
            partes = [f'{k}="{v}"' for k, v in attrs.items() if not (k == "href" and len(v) > 60)]
            if el["clase"]:
                partes.append(f'class="{el["clase"]}"')
            linea = f"  <{tag} {' '.join(partes)}>" + (f"  «{texto}»" if texto else "")
        if linea not in vistos:
            vistos.add(linea)
            lineas.append(linea)
    return lineas


def ejecutar(config: dict, log, carpeta: str | None = None) -> Path:
    if carpeta:
        origen = Path(carpeta)
        if not origen.is_absolute():
            origen = RAIZ / origen
    else:
        candidatas = sorted((RAIZ / "capturas").glob("referencia_*"))
        if not candidatas:
            raise SystemExit("No hay capturas de referencia: ejecuta antes python src/main.py grabar")
        origen = candidatas[-1]
    salida = CARPETA_HUELLAS / f"analisis_{marca_tiempo()}.txt"
    bloques = []
    for html in sorted(origen.glob("*.html")):
        lineas = resumir_html(html.read_text(encoding="utf-8", errors="replace"))
        bloques.append(f"=== {html.stem} ===\n" + "\n".join(lineas))
    salida.write_text("\n\n".join(bloques) + "\n", encoding="utf-8")
    log.info(f"Analizadas {len(bloques)} pantallas de {origen}")
    log.info(f"Resumen en {salida}")
    return salida
