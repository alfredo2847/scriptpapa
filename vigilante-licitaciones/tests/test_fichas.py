from datetime import datetime

from conftest import entrada, feed

import fichas
from placsp import leer_atom

AHORA = datetime(2026, 11, 1, 9, 0)


class RedFalsa:
    def __init__(self):
        self.pedidas = []

    def descargar_documento(self, url, carpeta, nombre):
        self.pedidas.append(url)
        if "ppt" in url:
            raise OSError("caído")
        destino = carpeta / (nombre if nombre.endswith(".pdf") else nombre + ".pdf")
        destino.write_bytes(b"no es un pdf de verdad")
        return destino


def uno(**kw):
    kw.setdefault("objeto", "Servicio de paellas gigantes Fiestas Mayores")
    return next(leer_atom(feed(entrada("1", **kw))))


def test_lee_datos_para_la_ficha():
    c = uno()
    assert c.documentos == [("pliego_administrativo", "PCAP paellas.pdf", "https://doc/pcap/1"),
                            ("pliego_tecnico", "PPT", "https://doc/ppt/1")]
    assert c.criterios == [("Precio", "70"), ("Mejoras", "30")]
    assert c.garantias == ["Definitiva: 5 %"]
    assert c.solvencia[0].startswith("Técnica: Relación")
    assert c.ejecucion == "3 días"
    assert c.presentacion == "1"


def test_valoracion(config):
    puntos, etiqueta, razones = fichas.valorar(uno(), "Alto", AHORA, config)
    # 40 encaje + 10 paellas + 20 importe + 15 plazo (19 días) + 10 simplificado + 5 servicios
    assert puntos == 100 and etiqueta == "Muy interesante"
    puntos, etiqueta, _ = fichas.valorar(uno(objeto="Catering fiestas", importe="800", plazo="2026-11-02",
                                             procedimiento="1"), "Medio", AHORA, config)
    assert puntos == 25 + 0 + 0 + 5 + 5 and etiqueta == "Revisar"


def test_crea_carpeta_y_no_repite_descargas(tmp_path, config):
    red = RedFalsa()
    carpeta, puntos, _ = fichas.crear(uno(), "Alto", "menciona paella", "Sueca", AHORA, config,
                                      red=red, base=tmp_path)
    assert carpeta.name == "2026-11-20 Sueca - Servicio de paellas gigantes Fiestas Mayores"
    resumen = (carpeta / fichas.RESUMEN).read_text(encoding="utf-8-sig")
    assert "VALORACIÓN: 100/100 - Muy interesante" in resumen
    assert "Precio: 70 puntos" in resumen
    assert "Definitiva: 5 %" in resumen
    assert "pliego_administrativo_PCAP paellas.pdf" in resumen
    assert "No se pudieron descargar" in resumen and "PPT" in resumen
    # Segunda vez: misma carpeta, el PCAP no se vuelve a pedir
    red2 = RedFalsa()
    otra, _, _ = fichas.crear(uno(), "Alto", "menciona paella", "Sueca", AHORA, config,
                              red=red2, base=tmp_path, carpeta=carpeta)
    assert otra == carpeta and red2.pedidas == ["https://doc/ppt/1"]


def test_frases_clave():
    texto = ("El servicio consistirá en 3.000 raciones de paella valenciana. "
             "La comida popular se celebrará el 15 de agosto en la plaza.\n"
             "El adjudicatario dispondrá de registro sanitario y seguro de responsabilidad civil.\n"
             "Garantía definitiva: 5 % del importe de adjudicación.")
    frases = fichas.frases_clave(texto)
    assert "3.000 raciones" in frases["Raciones / personas"][0]
    assert "15 de agosto" in frases["Fechas"][0]
    assert frases["Requisitos sanitarios y seguro"]
    assert frases["Garantía"]
