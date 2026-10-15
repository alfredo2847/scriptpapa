from comun import contiene_municipio, elegir_unidad, municipio_desde_denominacion, slugs_municipio, variantes_municipio


def test_municipio_desde_denominacion():
    assert municipio_desde_denominacion("Ayuntamiento de València") == "València"
    assert municipio_desde_denominacion("Ajuntament de Bétera") == "Bétera"
    assert municipio_desde_denominacion("Ajuntament d'Alzira") == "Alzira"


def test_variantes_bilingues_y_articulos():
    assert "alboraya" in variantes_municipio("Alboraya/Alboraia")
    assert "alboraia" in variantes_municipio("Alboraya/Alboraia")
    assert variantes_municipio("Eliana, l'")[:2] == ["l eliana", "eliana"]


def test_contiene_municipio():
    assert contiene_municipio("Ayuntamiento de Valencia - Concejalía de Fiestas", "València")
    assert contiene_municipio("Propuesta para las fiestas de L'Eliana", "Eliana, l'")
    assert not contiene_municipio("Ayuntamiento de Albalat dels Sorells", "Albal")
    assert not contiene_municipio("Ayuntamiento de Albal", "Albalat dels Sorells")


def test_slugs():
    assert set(slugs_municipio("L'Eliana")) >= {"leliana", "l-eliana", "eliana"}
    assert "puigdesantamaria" in slugs_municipio("Puig de Santa Maria, el")


def test_elegir_unidad_prioridades():
    ayto = ("L01460011", "Ayuntamiento de Albal")
    fiestas = ("LA1", "Concejalía de Cultura y Fiestas")
    cultura = ("LA2", "Regidoria de Cultura")
    otra = ("LA3", "Concejalía de Urbanismo")
    assert elegir_unidad(*ayto, [ayto, otra, cultura, fiestas]) == fiestas
    assert elegir_unidad(*ayto, [ayto, otra, cultura]) == cultura
    assert elegir_unidad(*ayto, [ayto, otra]) == ayto
    assert elegir_unidad(*ayto, [("LA4", "Regidoria de Festes")]) == ("LA4", "Regidoria de Festes")
    assert elegir_unidad(*ayto, [("LA5", "Comisión de Festejos")]) == ("LA5", "Comisión de Festejos")
