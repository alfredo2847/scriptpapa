"""Explora la estructura interna del formulario del REG (no rellena ni envía nada).

    python src/main.py explorar-reg

Abre el Chrome del bot en "Nuevo registro" (iniciando sesión con Cl@ve si hace
falta), guarda el contenido interno de los componentes dnt-* (sus shadow DOM),
abre uno de los desplegables y guarda las opciones que aparecen. El resultado
queda en huellas/exploracion_<fecha>.txt para escribir los selectores.
"""

from __future__ import annotations

import time

from comun import RAIZ, marca_tiempo
from motor import CARPETA_HUELLAS, Navegador

URL_NUEVO = "https://reg.redsara.es/es/nuevo-registro"

VOLCAR_COMPONENTES_JS = """
() => {
  const salida = [];
  const vistos = new Set();
  for (const el of document.querySelectorAll('dnt-select, dnt-input, dnt-checkbox, dnt-radio-group, dnt-button')) {
    const clave = el.tagName + '|' + (el.getAttribute('formcontrolname') || '') + '|' + (el.getAttribute('type') || '');
    if (vistos.has(clave)) continue;
    vistos.add(clave);
    const raiz = el.shadowRoot;
    let html = raiz ? raiz.innerHTML : '(sin shadowRoot abierto) ' + el.innerHTML;
    html = html.replace(/<style[\\s\\S]*?<\\/style>/g, '').replace(/\\s+/g, ' ');
    salida.push('### <' + el.tagName.toLowerCase() + ' id="' + (el.id || '') + '" formcontrolname="' +
      (el.getAttribute('formcontrolname') || '') + '">\\n' + html.slice(0, 2500));
  }
  return salida.join('\\n\\n');
}
"""

BUSCAR_OPCIONES_JS = """
() => {
  const encontrados = [];
  const recorrer = (raiz, ruta) => {
    for (const el of raiz.querySelectorAll('*')) {
      const rol = el.getAttribute && el.getAttribute('role');
      const tag = el.tagName.toLowerCase();
      if (rol === 'option' || rol === 'listbox' || tag === 'option' || tag === 'li' || tag.includes('option')) {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) {
          encontrados.push(ruta + ' > ' + el.outerHTML.replace(/\\s+/g, ' ').slice(0, 300));
        }
      }
      if (el.shadowRoot) recorrer(el.shadowRoot, ruta + ' > ' + tag + '::shadow');
    }
  };
  recorrer(document, 'document');
  return encontrados.slice(0, 60).join('\\n');
}
"""


def _iniciar_sesion_si_hace_falta(pagina, log) -> None:
    pagina.goto(URL_NUEVO)
    pagina.wait_for_timeout(3000)
    for _ in range(3):
        if "Paso 1 de 4" in pagina.inner_text("body"):
            return
        boton_reg = pagina.get_by_text("Accede con tu Cl@ve")
        if boton_reg.count():
            log.info("Iniciando sesión con Cl@ve…")
            boton_reg.first.click()
            pagina.wait_for_timeout(4000)
        boton_clave = pagina.locator('button.idp-button:has-text("Certificado electrónico")')
        if boton_clave.count():
            boton_clave.first.click()
            pagina.wait_for_url("https://reg.redsara.es/**", timeout=90000)
            pagina.wait_for_timeout(3000)
        pagina.goto(URL_NUEVO)
        pagina.wait_for_timeout(3000)
    raise SystemExit("No se llegó al formulario 'Nuevo registro'. Mira la ventana de Chrome y avísame de qué aparece.")


def ejecutar(config: dict, log) -> None:
    salida = CARPETA_HUELLAS / f"exploracion_{marca_tiempo()}.txt"
    partes = []
    navegador = Navegador(config)
    try:
        pagina = navegador.pagina
        _iniciar_sesion_si_hace_falta(pagina, log)
        log.info("Formulario abierto. Leyendo los componentes…")
        partes.append("=== COMPONENTES (paso 1) ===\n" + pagina.evaluate(VOLCAR_COMPONENTES_JS))

        # Abrir un desplegable para ver cómo muestra las opciones (no se elige nada).
        for selector in ('dnt-select#tipoDoc', 'dnt-select#streetType'):
            desplegable = pagina.locator(selector)
            if desplegable.count():
                desplegable.first.scroll_into_view_if_needed()
                desplegable.first.click()
                time.sleep(1.5)
                partes.append(f"=== OPCIONES AL ABRIR {selector} ===\n" + pagina.evaluate(BUSCAR_OPCIONES_JS))
                pagina.keyboard.press("Escape")
                time.sleep(0.5)
        captura = RAIZ / "capturas" / f"exploracion_{marca_tiempo()}.png"
        pagina.screenshot(path=str(captura), full_page=True)
        partes.append(f"=== URL === {pagina.url}")
    finally:
        salida.write_text("\n\n".join(partes) + "\n", encoding="utf-8")
        navegador.cerrar()
    log.info(f"Exploración guardada en {salida}")
