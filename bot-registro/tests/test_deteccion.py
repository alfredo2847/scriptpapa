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
            return url + "/info.0", "<title>Sede Electrónica del Ayuntamiento de Albal</title>46470 Albal esPublico"
        return None
    monkeypatch.setattr(deteccion_via, "_descargar", falsa_descarga)
    assert buscar_sede("Albal", "", 1, PLATAFORMAS) == ("https://albal.sedelectronica.es/info.0", "gestiona")


def test_homonimo_de_otra_provincia(monkeypatch):
    """l'Alcúdia (Valencia) no debe quedarse con la sede de Alcúdia (Mallorca)."""
    mallorca = "<title>Ajuntament d'Alcúdia</title><p>Major, 9 - 07400 Alcúdia (Illes Balears)</p>espublico"
    valencia = "<title>Ajuntament de l'Alcúdia</title><p>Pl. Constitució 1, 46250 L'Alcúdia</p>espublico"

    def descarga(paginas):
        return lambda sesion, url, timeout: (url, paginas[url]) if url in paginas else None

    monkeypatch.setattr(deteccion_via, "_descargar", descarga({"https://alcudia.sedelectronica.es": mallorca}))
    assert buscar_sede("Alcúdia, l'", "", 1, PLATAFORMAS, exigir_provincia=True) == ("", "")
    monkeypatch.setattr(deteccion_via, "_descargar", descarga({"https://lalcudia.sedelectronica.es": valencia}))
    assert buscar_sede("Alcúdia, l'", "", 1, PLATAFORMAS, exigir_provincia=True)[1] == "gestiona"


def test_sin_homonimo_basta_el_nombre(monkeypatch):
    """La página de inicio de Gestiona no muestra código postal: sin homónimos no se exige."""
    pagina = "<title>Sede Electrónica del Ayuntamiento de Agullent</title>espublico"
    monkeypatch.setattr(deteccion_via, "_descargar",
                        lambda s, url, t: (url, pagina) if url == "https://agullent.sedelectronica.es" else None)
    assert buscar_sede("Agullent", "", 1, PLATAFORMAS)[1] == "gestiona"
    assert buscar_sede("Agullent", "", 1, PLATAFORMAS, exigir_provincia=True) == ("", "")


def test_es_de_valencia():
    assert deteccion_via.es_de_valencia("<p>NIF P4601900A</p>", "P4601900A")
    assert deteccion_via.es_de_valencia("<p>46200 Paiporta</p>")
    assert deteccion_via.es_de_valencia("<p>Ajuntament de Paiporta (València)</p>")
    assert not deteccion_via.es_de_valencia("<p>Tel. 962 46 00 00 · 07400 Alcúdia</p>")
