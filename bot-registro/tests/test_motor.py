from pathlib import Path

import pytest

from motor import CARPETA_HUELLAS, Flujo, HuellaInvalida

AQUI = Path(__file__).parent


def test_plantillas_del_proyecto_son_validas():
    Flujo(CARPETA_HUELLAS / "rec.yaml")  # huellas reales del REG: deben cargar sin errores
    Flujo(CARPETA_HUELLAS / "sedes" / "_plantilla.yaml")
    assert Flujo(AQUI / "mock_rec" / "rec.yaml").verificada


@pytest.mark.parametrize("contenido, mensaje", [
    ("pantallas: {a: {url: x}}\napertura: [{pantalla: b}]", "sin huella"),
    ("pantallas: {a: {url: x}}\napertura: [{pantala: a}]", "claves desconocidas"),
    ("pantallas: {a: {url: x}}\napertura: [{acciones: [{pinchar: x}]}]", "acción desconocida"),
    ("pantallas: {a: {}}", "necesita url"),
    ("verificada: true\npantallas: {a: {url: TODO}}", "TODO"),
])
def test_huellas_invalidas(tmp_path, contenido, mensaje):
    ruta = tmp_path / "x.yaml"
    ruta.write_text(contenido, encoding="utf-8")
    with pytest.raises(HuellaInvalida, match=mensaje):
        Flujo(ruta)
