import deteccion_via
from deteccion_via import buscar_sede, menciona_municipio

PLATAFORMAS = {
    "gestiona": {"dominios": [r"\.sedelectronica\.es$"], "html": ["espublico"]},
    "eadmin": {"dominios": [], "html": ["eadmin"]},
}


def test_menciona_municipio():
    assert menciona_municipio("<title>Sede Electrónica del Ayuntamiento de Albal</title>", "Albal")
    assert menciona_municipio("<h1>Ajuntament de Bot&eacute;</h1>", "Botè")
    assert not menciona_municipio("<title>Sede electrónica</title><script>var x='Albal'</script>", "Albal")


def test_subdominio_comodin_no_cuenta(monkeypatch):
    """*.sedelectronica.es responde a cualquier nombre: sin el municipio en la página no es su sede."""
    def falsa_descarga(sesion, url, timeout):
        if "sedelectronica.es" in url:
            return url, "<title>Gestiona - esPublico</title><p>Sede no encontrada</p>"
        return None
    monkeypatch.setattr(deteccion_via, "_descargar", falsa_descarga)
    assert buscar_sede("Albal", "", 1, PLATAFORMAS) == ("", "")


def test_sede_real_reconocida(monkeypatch):
    def falsa_descarga(sesion, url, timeout):
        if url == "https://albal.sedelectronica.es":
            return url + "/info.0", "<title>Sede Electrónica del Ayuntamiento de Albal</title>esPublico"
        return None
    monkeypatch.setattr(deteccion_via, "_descargar", falsa_descarga)
    assert buscar_sede("Albal", "", 1, PLATAFORMAS) == ("https://albal.sedelectronica.es/info.0", "gestiona")
