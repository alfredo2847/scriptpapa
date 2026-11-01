"""Acciones del motor para el formulario del REG: desplegables propios, etiquetas y buscador por código."""

import logging

import pytest

pytest.importorskip("playwright")

from comun import cargar_config  # noqa: E402
from motor import CARPETA_HUELLAS, ErrorAyuntamiento, Flujo, Motor, Navegador  # noqa: E402

PAGINA = """
<html><body>
<h1>Datos de solicitud (Paso 2 de 4)</h1>
<div id="tipo" role="combobox" onclick="document.getElementById('lista').style.display='block'">Selecciona</div>
<div id="lista" role="listbox" style="display:none">
  <div role="option" onclick="document.getElementById('tipo').textContent='NIF'">NIF</div>
  <div role="option" onclick="document.getElementById('tipo').textContent='CIF';document.getElementById('lista').style.display='none'">CIF</div>
</div>
<button onclick="document.getElementById('modal').style.display='block'">Asistente de búsqueda</button>
<div id="modal" style="display:none">
  <input id="buscar-campo"><button onclick="buscar()">Buscar</button>
  <div id="resultados"></div>
</div>
<div id="elegido"></div>
<input id="organismo" readonly value="">
<dl><dt>Órgano destino:</dt><dd>L01461311 - Ayuntamiento de Gandia</dd><dt>Asunto:</dt><dd>Paellas para Gandia</dd></dl>
<div id="componente"></div>
<script>
document.getElementById('componente').attachShadow({mode: 'open'}).innerHTML =
  '<dl><dt>Número de registro:</dt><dd>REGAGE26e00000000001</dd></dl>';
function buscar() {
  const c = document.getElementById('buscar-campo').value;
  const r = document.getElementById('resultados');
  r.innerHTML = '';
  if (c === 'L01461311') {
    // como en el REG: el resultado se pinta dentro de un componente con shadow DOM
    const caja = document.createElement('div');
    caja.attachShadow({mode: 'open'}).innerHTML =
      '<div>L01461311 - Ayuntamiento de Gandia <button>Seleccionar</button></div>';
    caja.shadowRoot.querySelector('button').onclick = elegir;
    r.appendChild(caja);
  }
}
// como en el REG: el organismo elegido se muestra dentro del shadow DOM del componente
const elegidoSombra = document.getElementById('elegido').attachShadow({mode: 'open'});
function elegir() {
  elegidoSombra.innerHTML = '<span>L01461311 - Ayuntamiento de Gandia</span>';
  // como en el REG: el organismo elegido queda como valor de un campo de solo lectura
  document.getElementById('organismo').value = 'L01461311 - Ayuntamiento de Gandia';
  document.getElementById('modal').style.display = 'none';
}
</script>
</body></html>
"""

FLUJO = """
plataforma: prueba
pantallas:
  p: {etiquetas: ["Paso 2 de 4"]}
destinatario:
  modo: codigo
  abrir:
    - clic: 'role=button[name="Asistente de búsqueda"]'
  campo_busqueda: '#buscar-campo'
  boton_buscar: 'role=button[name="Buscar"]'
  boton_seleccionar: 'role=button[name="Seleccionar"]'
  espera_resultados_seg: 0.2
  confirmacion: '#organismo'
"""


@pytest.fixture()
def motor(tmp_path):
    config = cargar_config()
    config["navegador"] = {"canal": "", "headless": True, "perfil": str(tmp_path / "perfil")}
    config["ejecucion"].update(timeout_accion_seg=3, timeout_pantalla_seg=3)
    ruta = tmp_path / "f.yaml"
    ruta.write_text(FLUJO, encoding="utf-8")
    navegador = Navegador(config)
    navegador.pagina.set_content(PAGINA)
    m = Motor(navegador, Flujo(ruta), config, logging.getLogger("test"))
    yield m
    navegador.cerrar()


def test_elegir_opcion(motor):
    motor.elegir_opcion("#tipo", "CIF")
    assert motor.pagina.inner_text("#tipo") == "CIF"
    with pytest.raises(ErrorAyuntamiento, match="No aparece la opción"):
        motor.elegir_opcion("#tipo", "Pasaporte")


def test_leer_por_etiquetas(motor):
    leido = motor.leer_por_etiquetas({"codigo": "Órgano destino:", "asunto": "Asunto:"})
    assert leido == {"codigo": "L01461311 - Ayuntamiento de Gandia", "asunto": "Paellas para Gandia"}
    with pytest.raises(ErrorAyuntamiento):
        motor.leer_por_etiquetas({"x": "No existe:"})
    # valores dentro de un shadow DOM
    assert motor.leer_por_etiquetas({"n": "Número de registro:"}) == {"n": "REGAGE26e00000000001"}


def test_buscar_por_codigo(motor):
    # varias búsquedas seguidas: sin resultado (el buscador queda abierto), con resultado, y otra vez
    assert motor.buscar_por_codigo("L01469999") is False
    assert motor.buscar_por_codigo("L01469998") is False
    assert motor.buscar_por_codigo("L01461311") is True   # la confirmación está en un shadow DOM
    assert motor.buscar_por_codigo("L01461311") is True   # el buscador se cerró y se vuelve a abrir
    assert "L01461311" in motor.texto_completo("#elegido")


def test_huellas_del_reg_cargan():
    flujo = Flujo(CARPETA_HUELLAS / "rec.yaml")
    assert flujo.verificada
    assert flujo.seccion("destinatario")["modo"] == "codigo"
    assert flujo.datos["deteccion"][-1]["pantalla"] == "paso2"
