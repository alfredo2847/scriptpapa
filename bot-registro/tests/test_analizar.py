from analizar_capturas import resumir_html
from configurar_certificado import nombre_comun


def test_resumir_html_detecta_campos_y_botones():
    html = """<h1>Datos de solicitud (Paso 2 de 4)</h1>
    <label for="asunto">Asunto</label><input id="asunto" formcontrolname="subject" placeholder="Introduce el asunto">
    <ng-select formcontrolname="tipo" role="combobox"></ng-select>
    <button class="btn btn-primary" type="button">Siguiente</button>
    <script>var x = "<input id='falso'>";</script>"""
    lineas = "\n".join(resumir_html(html))
    assert "[h1] Datos de solicitud (Paso 2 de 4)" in lineas
    assert 'id="asunto"' in lineas and 'formcontrolname="subject"' in lineas
    assert 'formcontrolname="tipo"' in lineas
    assert "«Siguiente»" in lineas
    assert "falso" not in lineas


def test_nombre_comun():
    assert nombre_comun("CN=CRESPO BEJARANO GUILLERMO - 00000000T, SERIALNUMBER=IDCES-00000000T, C=ES") == \
        "CRESPO BEJARANO GUILLERMO - 00000000T"
    assert nombre_comun('CN="APELLIDO, NOMBRE", O=X') == "APELLIDO, NOMBRE"
