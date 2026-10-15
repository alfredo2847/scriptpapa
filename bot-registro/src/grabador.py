"""Envío manual de referencia (paso 3 del plan de trabajo).

Abre Chrome con el perfil del bot. Tú haces el envío a mano y, en cada pantalla,
pulsas Enter en la consola: se guarda la captura, el HTML y un borrador de
huella (URL, título, etiquetas y campos con selectores sugeridos) en
huellas/borrador_<fecha>.yaml. Con eso se completa huellas/rec.yaml.

El grabador no pulsa nada ni rellena nada: solo observa.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import yaml

from comun import RAIZ, marca_tiempo, nombre_archivo_seguro
from motor import CARPETA_HUELLAS, Navegador

RECOGER_JS = """
() => {
  const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const limpio = t => (t || '').replace(/\\s+/g, ' ').trim();
  const textos = sel => [...document.querySelectorAll(sel)].filter(visible).map(e => limpio(e.innerText)).filter(t => t && t.length < 120);
  const etiquetaDe = el => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return limpio(l.innerText); }
    const padre = el.closest('label'); if (padre) return limpio(padre.innerText);
    return el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title') || '';
  };
  const selector = el => {
    if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) return '#' + CSS.escape(el.id);
    const nombre = el.getAttribute('name');
    if (nombre) return `${el.tagName.toLowerCase()}[name="${nombre}"]`;
    return '';
  };
  const campos = [...document.querySelectorAll('input, textarea, select')]
    .filter(el => el.type === 'file' || (visible(el) && el.type !== 'hidden'))
    .map(el => ({tipo: el.tagName.toLowerCase() + (el.type ? ':' + el.type : ''), etiqueta: limpio(etiquetaDe(el)), selector: selector(el)}));
  const botones = [...document.querySelectorAll('button, input[type=submit], input[type=button], a.btn, [role=button]')]
    .filter(visible).map(el => ({texto: limpio(el.innerText || el.value), selector: selector(el)})).filter(b => b.texto);
  return {
    titulos: textos('h1, h2, h3, legend'),
    etiquetas: textos('label, th, dt'),
    campos, botones,
  };
}
"""


def _patron_url(url: str) -> str:
    partes = urlparse(url)
    return "^" + re.escape(f"{partes.scheme}://{partes.netloc}{partes.path}")


def ejecutar(config: dict, log, url: str | None = None) -> None:
    url = url or config["rec"]["url_inicio"]
    carpeta = RAIZ / "capturas" / f"referencia_{marca_tiempo()}"
    carpeta.mkdir(parents=True, exist_ok=True)
    borrador_ruta = CARPETA_HUELLAS / f"borrador_{marca_tiempo()}.yaml"
    pantallas: dict = {}

    navegador = Navegador(config)
    try:
        navegador.pagina.goto(url)
        log.info("Haz el envío a mano en Chrome. En cada pantalla nueva, vuelve aquí y pulsa Enter "
                 "(o escribe un nombre para la pantalla y Enter). Escribe 'fin' para terminar.")
        n = 0
        while True:
            respuesta = input(f"[pantalla {n + 1}] nombre (Enter = automático, 'fin' = terminar): ").strip()
            if respuesta.lower() == "fin":
                break
            pagina = navegador.contexto.pages[-1]  # la pestaña más reciente
            n += 1
            nombre = nombre_archivo_seguro(respuesta) or f"pantalla_{n:02d}"
            base = carpeta / f"{n:02d}_{nombre}"
            pagina.screenshot(path=str(base.with_suffix(".png")), full_page=True)
            base.with_suffix(".html").write_text(pagina.content(), encoding="utf-8")
            datos = pagina.evaluate(RECOGER_JS)
            pantallas[nombre] = {
                "url": _patron_url(pagina.url),
                "titulo": pagina.title(),
                "etiquetas": (datos["titulos"] + datos["etiquetas"])[:8],
                "_campos": datos["campos"],
                "_botones": datos["botones"],
            }
            with open(borrador_ruta, "w", encoding="utf-8") as f:
                yaml.safe_dump({"pantallas": pantallas}, f, allow_unicode=True, sort_keys=False, width=120)
            log.info(f"  guardada {base.name} ({len(datos['campos'])} campos, {len(datos['botones'])} botones)")
    finally:
        navegador.cerrar()
    log.info(f"Capturas en {carpeta}\nBorrador de huellas en {borrador_ruta}\n"
             "Revisa el borrador y pasa las huellas y selectores a huellas/rec.yaml; "
             "las claves que empiezan por _ son solo orientativas.")
