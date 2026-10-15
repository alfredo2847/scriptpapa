from salvaguardas import confirmar_consola, verificar_resumen_rec, verificar_resumen_sede

ESPERADO = {
    "municipio": "Albal",
    "dir3_ayto": "L01460011",
    "dir3_destino": "LA0000001",
    "codigos_validos": {"L01460011", "LA0000001"},
    "adjuntos": ["carta.pdf", "dossier.pdf"],
}
LEIDO = {
    "destinatario_codigo": "LA0000001",
    "destinatario_nombre": "Ayuntamiento de Albal - Concejalía de Fiestas",
    "asunto": "Propuesta de servicio de paellas para las fiestas de Albal",
    "adjuntos": ["carta.pdf (12 KB)", "dossier.pdf (1 MB)"],
}


def test_resumen_correcto():
    assert verificar_resumen_rec(LEIDO, ESPERADO) == []


def test_resumen_codigo_distinto():
    fallos = verificar_resumen_rec({**LEIDO, "destinatario_codigo": "L01460022"}, ESPERADO)
    assert any("código" in f for f in fallos)


def test_resumen_unidad_de_otro_ayuntamiento():
    esperado = {**ESPERADO, "dir3_destino": "LA9999999"}
    fallos = verificar_resumen_rec({**LEIDO, "destinatario_codigo": "LA9999999"}, esperado)
    assert any("no pertenece" in f for f in fallos)


def test_resumen_municipio_ausente_y_asunto():
    fallos = verificar_resumen_rec({**LEIDO, "destinatario_nombre": "Concejalía de Fiestas",
                                    "asunto": "Propuesta"}, ESPERADO)
    assert len(fallos) == 2


def test_resumen_adjuntos():
    assert verificar_resumen_rec({**LEIDO, "adjuntos": ["carta.pdf"]}, ESPERADO)
    assert verificar_resumen_rec({**LEIDO, "adjuntos": ["carta.pdf", "carta.pdf", "dossier.pdf"]}, ESPERADO)
    assert verificar_resumen_rec({**LEIDO, "adjuntos": ["carta.pdf", "otro.pdf"]}, ESPERADO)


def test_resumen_sede_dominio():
    esperado = {"municipio": "Albal", "url_sede": "https://albal.sedelectronica.es/info.0",
                "adjuntos": ["carta.pdf", "dossier.pdf"]}
    leido = {"url": "https://albal.sedelectronica.es/tramite", "cabecera": "Ayuntamiento de Albal",
             "asunto": "Fiestas de Albal", "adjuntos": ["carta.pdf", "dossier.pdf"]}
    assert verificar_resumen_sede(leido, esperado) == []
    assert verificar_resumen_sede({**leido, "url": "https://otro.sedelectronica.es/x"}, esperado)
    assert verificar_resumen_sede({**leido, "cabecera": "Ayuntamiento de Alzira"}, esperado)


def test_confirmar_consola():
    respuestas = iter(["quizá", "s"])
    assert confirmar_consola({"municipio": "Albal"}, lambda _: next(respuestas))
    assert not confirmar_consola({"municipio": "Albal"}, lambda _: "n")
