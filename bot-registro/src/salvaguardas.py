"""Salvaguardas: ante la duda, el script no envía.

- Verificación del resumen antes de firmar.
- Parada inmediata con un archivo STOP o Ctrl+C (tras el ayuntamiento en curso).
- Modo prueba obligatorio antes de la primera tanda real y tras cambiar huellas.
- Confirmación por consola antes de cada firma.
- Comprobación de los adjuntos.
- Avisos con sonido y notificación de Windows.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from comun import PATRON_CODIGO_DIR3, RAIZ, ahora_texto, contiene_municipio, normalizar, sin_tildes

ARCHIVO_STOP = RAIZ / "STOP"
ARCHIVO_PRUEBAS = RAIZ / "datos" / "pruebas_huellas.json"


# ---------------------------------------------------------------------------
# Verificación del resumen
# ---------------------------------------------------------------------------

def verificar_adjuntos(leidos: list[str], esperados: list[str]) -> list[str]:
    fallos = []
    if len(leidos) != len(esperados):
        fallos.append(f"Hay {len(leidos)} adjuntos en el resumen y se esperaban {len(esperados)} ({esperados}): {leidos}")
    for nombre in esperados:
        apariciones = sum(1 for t in leidos if nombre.lower() in t.lower())
        if apariciones != 1:
            fallos.append(f"El adjunto {nombre} aparece {apariciones} veces en el resumen")
    return fallos


def verificar_resumen_rec(leido: dict, esperado: dict) -> list[str]:
    """Compara lo que muestra la pantalla de resumen del REC con la hoja.

    esperado: municipio, dir3_ayto, dir3_destino, codigos_validos, adjuntos (nombres).
    leido: destinatario_codigo, destinatario_nombre, asunto, adjuntos.
    """
    fallos = []
    municipio = esperado["municipio"]
    codigos = PATRON_CODIGO_DIR3.findall(str(leido.get("destinatario_codigo", "")).upper())
    if esperado["dir3_destino"] not in codigos:
        fallos.append(f"El código del destinatario en pantalla ({codigos or 'ninguno'}) no es {esperado['dir3_destino']}")
    if esperado["dir3_destino"] not in esperado["codigos_validos"]:
        fallos.append(f"La unidad {esperado['dir3_destino']} no pertenece al ayuntamiento {esperado['dir3_ayto']}")
    if not contiene_municipio(leido.get("destinatario_nombre", ""), municipio):
        fallos.append(f"El nombre del destinatario {leido.get('destinatario_nombre')!r} no contiene {municipio!r}")
    if not contiene_municipio(leido.get("asunto", ""), municipio):
        fallos.append(f"El asunto {leido.get('asunto')!r} no contiene {municipio!r}")
    fallos += verificar_adjuntos(leido.get("adjuntos") or [], esperado["adjuntos"])
    return fallos


def verificar_resumen_sede(leido: dict, esperado: dict) -> list[str]:
    """Sede electrónica: municipio en la cabecera y en el resumen, dominio esperado, adjuntos y asunto."""
    fallos = []
    municipio = esperado["municipio"]
    dominio_esperado = (urlparse(esperado["url_sede"]).hostname or "").lower()
    dominio = (urlparse(leido.get("url", "")).hostname or "").lower()
    if not dominio_esperado or not (dominio == dominio_esperado or dominio.endswith("." + dominio_esperado)):
        fallos.append(f"El dominio {dominio!r} no es el de la sede {dominio_esperado!r}")
    if not contiene_municipio(leido.get("cabecera", ""), municipio):
        fallos.append(f"La cabecera {leido.get('cabecera')!r} no contiene {municipio!r}")
    if "destinatario_nombre" in leido and not contiene_municipio(leido["destinatario_nombre"], municipio):
        fallos.append(f"El resumen {leido['destinatario_nombre']!r} no contiene {municipio!r}")
    if not contiene_municipio(leido.get("asunto", ""), municipio):
        fallos.append(f"El asunto {leido.get('asunto')!r} no contiene {municipio!r}")
    fallos += verificar_adjuntos(leido.get("adjuntos") or [], esperado["adjuntos"])
    return fallos


# ---------------------------------------------------------------------------
# Adjuntos
# ---------------------------------------------------------------------------

def comprobar_documento(ruta: Path, tamano_max_mb: float) -> list[str]:
    problemas = []
    if not ruta.exists():
        return [f"No existe {ruta}"]
    if ruta.suffix.lower() != ".pdf":
        problemas.append(f"{ruta.name} no es un PDF")
    if sin_tildes(ruta.name) != ruta.name or " " in ruta.name:
        problemas.append(f"{ruta.name}: el nombre no puede llevar tildes ni espacios")
    if ruta.stat().st_size > tamano_max_mb * 1024 * 1024:
        problemas.append(f"{ruta.name} ocupa más de {tamano_max_mb} MB")
    if ruta.read_bytes()[:5] != b"%PDF-":
        problemas.append(f"{ruta.name} no parece un PDF válido")
    return problemas


# ---------------------------------------------------------------------------
# Modo prueba obligatorio
# ---------------------------------------------------------------------------

def registrar_prueba_ok(hash_huellas: str, municipios: list[str]) -> None:
    ARCHIVO_PRUEBAS.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO_PRUEBAS.write_text(json.dumps(
        {"hash_huellas": hash_huellas, "fecha": ahora_texto(), "municipios": municipios},
        ensure_ascii=False, indent=2,
    ), encoding="utf-8")


def prueba_vigente(hash_huellas: str) -> bool:
    try:
        datos = json.loads(ARCHIVO_PRUEBAS.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    return datos.get("hash_huellas") == hash_huellas


# ---------------------------------------------------------------------------
# Parada inmediata
# ---------------------------------------------------------------------------

class ControlParada:
    """Archivo STOP o Ctrl+C: la tanda se detiene tras el ayuntamiento en curso.

    Un segundo Ctrl+C interrumpe en el acto.
    """

    def __init__(self):
        self.solicitada = False
        self._anterior = None

    def instalar(self):
        self._anterior = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._manejador)
        return self

    def restaurar(self):
        if self._anterior is not None:
            signal.signal(signal.SIGINT, self._anterior)

    def _manejador(self, signum, frame):
        if self.solicitada:
            raise KeyboardInterrupt
        self.solicitada = True
        print("\n*** Ctrl+C: la tanda se detendrá al terminar el ayuntamiento en curso "
              "(pulsa Ctrl+C otra vez para cortar ya) ***")

    def debe_parar(self) -> bool:
        if ARCHIVO_STOP.exists():
            self.solicitada = True
        return self.solicitada

    def pausa(self, segundos: float) -> bool:
        """Espera en tramos de 1 s; devuelve False si se pide parar."""
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            if self.debe_parar():
                return False
            time.sleep(min(1.0, limite - time.monotonic()))
        return not self.debe_parar()


# ---------------------------------------------------------------------------
# Confirmación y avisos
# ---------------------------------------------------------------------------

def confirmar_consola(fila: dict, entrada=input) -> bool:
    print("\n" + "=" * 70)
    print(f"  Municipio:     {fila.get('municipio')}  ({fila.get('dir3_ayto')})")
    print(f"  Destinatario:  {fila.get('nombre_destino')}")
    print(f"  Código:        {fila.get('dir3_destino')}")
    print(f"  Vía:           {fila.get('via')}")
    print("=" * 70)
    while True:
        respuesta = normalizar(entrada("¿Firmar y enviar este registro? (s/n): "))
        if respuesta in ("s", "si"):
            return True
        if respuesta in ("n", "no"):
            return False


def avisar(titulo: str, mensaje: str) -> None:
    """Sonido y notificación de Windows (en otros sistemas, solo consola)."""
    print(f"\n*** {titulo}: {mensaje} ***\n")
    if sys.platform != "win32":
        print("\a", end="", flush=True)
        return
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONHAND)
    except Exception:
        pass
    titulo_ps = titulo.replace("'", "''")
    mensaje_ps = mensaje[:250].replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; $n.Icon = [System.Drawing.SystemIcons]::Warning; "
        f"$n.BalloonTipTitle = '{titulo_ps}'; $n.BalloonTipText = '{mensaje_ps}'; $n.Visible = $true; "
        "$n.ShowBalloonTip(10000); Start-Sleep -Seconds 10; $n.Dispose()"
    )
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass
