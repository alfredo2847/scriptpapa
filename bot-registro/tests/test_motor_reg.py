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
<dl><dt>Órgano destino:</dt><dd>L01461311 - Ayuntamiento de Gandia</dd><dt>Asunto:</dt><dd>Paellas para Gandia</dd></dl>
<script>
function buscar() {
  const c = document.getElementById('buscar-campo').value;
  const r = document.getElementById('resultados');
  r.innerHTML = '';
  if (c === 'L01461311') {
    r.innerHTML = '<div>L01461311 - Ayuntamiento de Gandia <button onclick="elegir()">Seleccionar</button></div>';
  }
}
function elegir() { document.getElementById('elegido').textContent = 'L01461311 - Ayuntamiento de Gandia'; }
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
  confirmacion: '#elegido'
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


def test_buscar_por_codigo(motor):
    assert motor.buscar_por_codigo("L01469999") is False
    assert motor.buscar_por_codigo("L01461311") is True
    assert "L01461311" in motor.pagina.inner_text("#elegido")


def test_huellas_del_reg_cargan():
    flujo = Flujo(CARPETA_HUELLAS / "rec.yaml")
    assert flujo.verificada
    assert flujo.seccion("destinatario")["modo"] == "codigo"
    assert flujo.datos["deteccion"][-1]["pantalla"] == "paso2"
