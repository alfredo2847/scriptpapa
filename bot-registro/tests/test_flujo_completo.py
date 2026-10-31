"""Prueba de punta a punta contra un REC simulado (tests/mock_rec/sitio).

Recorre inventario -> detectar -> enviar --prueba -> enviar real, y comprueba las
salvaguardas: verificación del resumen, REVISAR tras una firma sin justificante,
nada se envía dos veces, modo prueba obligatorio y archivo STOP.
"""

import functools
import http.server
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import yaml

pytest.importorskip("playwright")

AQUI = Path(__file__).parent
PROYECTO = AQUI.parent
PDF_MINIMO = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

ALBAL, BETERA, CATADAU, DAIMUS, EMPERADOR = "L01460011", "L01460022", "L01460033", "L01460044", "L01460055"


class _Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def servidor():
    manejador = functools.partial(_Silencioso, directory=str(AQUI / "mock_rec" / "sitio"))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), manejador)
    hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture(scope="module")
def proyecto(tmp_path_factory, servidor):
    raiz = tmp_path_factory.mktemp("bot-registro")
    shutil.copytree(PROYECTO / "src", raiz / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(PROYECTO / "huellas", raiz / "huellas", ignore=shutil.ignore_patterns("borrador_*"))
    shutil.copy(AQUI / "mock_rec" / "rec.yaml", raiz / "huellas" / "rec.yaml")
    (raiz / "documentos").mkdir()
    (raiz / "documentos" / "carta.pdf").write_bytes(PDF_MINIMO)
    (raiz / "documentos" / "dossier.pdf").write_bytes(PDF_MINIMO)
    config = yaml.safe_load((PROYECTO / "config.yaml").read_text(encoding="utf-8"))
    config["interesado"] = {"tipo": "sociedad", "razon_social": "Paellas Prueba SL", "cif": "B00000000",
                            "direccion": "Calle Mayor 1, Valencia", "email": "prueba@example.com",
                            "telefono": "600000000", "via_tipo": "Calle", "via_nombre": "Mayor 1",
                            "provincia": "València/Valencia", "poblacion": "València", "cp": "46001"}
    config["textos"]["expone"] = "Que Paellas Prueba SL elabora paellas para eventos."
    config["ejecucion"].update(pausa_entre_envios_seg=[0, 0], espera_firma_seg=5,
                               timeout_pantalla_seg=5, timeout_accion_seg=5)
    config["inventario"]["total_esperado"] = 5
    config["deteccion"].update(timeout_http_seg=2, hilos=5)
    config["rec"]["url_inicio"] = f"{servidor}/index.html"
    config["navegador"] = {"canal": "", "headless": True}
    (raiz / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return raiz


def ejecutar(proyecto, *args, entrada=""):
    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, str(proyecto / "src" / "main.py"), *args], input=entrada,
                       capture_output=True, text=True, encoding="utf-8", env=entorno, timeout=300)
    return r.returncode, r.stdout + r.stderr


def hoja(proyecto):
    sys.path.insert(0, str(PROYECTO / "src"))
    from hoja import HojaControl

    return HojaControl(proyecto / "datos" / "ayuntamientos.xlsx")


def test_flujo_completo(proyecto):
    # Fase 1: inventario
    codigo, salida = ejecutar(proyecto, "inventario", "--archivo", str(AQUI / "dir3_prueba.csv"))
    assert codigo == 0, salida
    h = hoja(proyecto)
    assert sorted(f["dir3_ayto"] for f in h) == [ALBAL, BETERA, CATADAU, DAIMUS, EMPERADOR]
    assert h.get(ALBAL)["dir3_destino"] == "LA0000001"          # Fiestas
    assert h.get(BETERA)["dir3_destino"] == "LA0000003"         # Cultura (unidad nieta)
    assert h.get(CATADAU)["dir3_destino"] == CATADAU            # el ayuntamiento
    assert h.get(BETERA)["municipio"] == "Bétera"
    assert (proyecto / "datos" / "dir3_bruto").glob("*dir3_prueba.csv")

    # Fase 2: detección (REC simulado; Emperador no está en el REC ni tiene sede)
    codigo, salida = ejecutar(proyecto, "detectar")
    assert codigo == 0, salida
    h = hoja(proyecto)
    assert [h.get(c)["via"] for c in (ALBAL, BETERA, CATADAU, DAIMUS)] == ["REC"] * 4
    assert h.get(EMPERADOR)["via"] == "MANUAL"

    # Sin modo prueba no se envía nada de verdad
    codigo, salida = ejecutar(proyecto, "enviar", "--sin-confirmar")
    assert codigo == 1 and "modo prueba" in salida

    # Modo prueba sobre Albal y Bétera: se para en el resumen y no firma
    codigo, salida = ejecutar(proyecto, "enviar", "--prueba", "--dir3", ALBAL, BETERA)
    assert codigo == 0, salida
    h = hoja(proyecto)
    assert h.get(ALBAL)["estado"] == h.get(BETERA)["estado"] == "PRUEBA_OK"
    assert "Modo prueba superado" in salida

    # Envío real con confirmación: Albal sí, Bétera no
    codigo, salida = ejecutar(proyecto, "enviar", "--max", "2", "--confirmar", "--dir3", ALBAL, BETERA,
                              entrada="s\nn\n")
    assert codigo == 0, salida
    h = hoja(proyecto)
    albal = h.get(ALBAL)
    assert albal["estado"] == "ENVIADO"
    assert albal["num_registro"] == "REGAGE26e00004242"
    assert (proyecto / albal["justificante"]).read_bytes().startswith(b"%PDF")
    assert h.get(BETERA)["estado"] == "PRUEBA_OK"
    assert h.get(BETERA)["notas"] == "Envío no confirmado por consola"

    # Nunca se repite un envío
    codigo, salida = ejecutar(proyecto, "enviar", "--sin-confirmar", "--dir3", ALBAL)
    assert codigo == 0 and "No hay ayuntamientos pendientes" in salida

    # Daimús: el resumen muestra otro destinatario -> ERROR sin firmar
    codigo, salida = ejecutar(proyecto, "enviar", "--sin-confirmar", "--dir3", DAIMUS)
    assert codigo == 0, salida
    daimus = hoja(proyecto).get(DAIMUS)
    assert daimus["estado"] == "ERROR"
    assert "Verificación del resumen" in daimus["notas"]
    assert list((proyecto / "capturas").glob(f"*error_{DAIMUS}.png"))

    # Catadau (prioridad 1, va primero): tras firmar aparece una pantalla inesperada
    # -> REVISAR y tanda detenida
    h = hoja(proyecto)
    h.get(CATADAU)["prioridad"] = 1
    h.guardar()
    codigo, salida = ejecutar(proyecto, "enviar", "--sin-confirmar", "--dir3", CATADAU, BETERA)
    assert codigo == 0, salida
    h = hoja(proyecto)
    assert h.get(CATADAU)["estado"] == "REVISAR"
    assert "TANDA DETENIDA" in salida
    assert h.get(BETERA)["estado"] == "PRUEBA_OK"  # no se llegó a procesar

    # REVISAR nunca se reintenta, ni siquiera con --reintentar-errores
    codigo, salida = ejecutar(proyecto, "enviar", "--sin-confirmar", "--reintentar-errores", "--dir3", CATADAU)
    assert "No hay ayuntamientos pendientes" in salida

    # Archivo STOP: la tanda no empieza
    (proyecto / "STOP").write_text("")
    codigo, salida = ejecutar(proyecto, "enviar", "--sin-confirmar", "--dir3", BETERA)
    assert "Parada solicitada" in salida
    assert hoja(proyecto).get(BETERA)["estado"] == "PRUEBA_OK"
    (proyecto / "STOP").unlink()

    # Cambiar una huella obliga a repetir el modo prueba
    rec = proyecto / "huellas" / "rec.yaml"
    rec.write_text(rec.read_text(encoding="utf-8") + "\n# cambio\n", encoding="utf-8")
    codigo, salida = ejecutar(proyecto, "enviar", "--sin-confirmar", "--dir3", BETERA)
    assert codigo == 1 and "modo prueba" in salida

    # Re-inventario: conserva los estados ya hechos
    codigo, salida = ejecutar(proyecto, "inventario", "--archivo", str(AQUI / "dir3_prueba.csv"))
    assert codigo == 0, salida
    h = hoja(proyecto)
    assert h.get(ALBAL)["estado"] == "ENVIADO" and h.get(CATADAU)["estado"] == "REVISAR"

    # Informe y hoja de manuales
    codigo, salida = ejecutar(proyecto, "informe")
    assert codigo == 0, salida
    assert "Comprobar a mano" in salida
    assert (proyecto / "datos" / "manuales.xlsx").exists()

    # Anotar a mano el resultado de un MANUAL
    codigo, salida = ejecutar(proyecto, "marcar", EMPERADOR, "--estado", "ENVIADO", "--num", "REG-1")
    assert codigo == 0, salida
    assert hoja(proyecto).get(EMPERADOR)["num_registro"] == "REG-1"


def test_recuento_incorrecto_no_toca_la_hoja(tmp_path):
    raiz = tmp_path / "bot"
    shutil.copytree(PROYECTO / "src", raiz / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(PROYECTO / "huellas", raiz / "huellas", ignore=shutil.ignore_patterns("borrador_*"))
    shutil.copy(PROYECTO / "config.yaml", raiz / "config.yaml")  # total_esperado: 266
    codigo, salida = ejecutar(raiz, "inventario", "--archivo", str(AQUI / "dir3_prueba.csv"))
    assert codigo == 1
    assert "se esperaban 266" in salida
    assert not (raiz / "datos" / "ayuntamientos.xlsx").exists()
