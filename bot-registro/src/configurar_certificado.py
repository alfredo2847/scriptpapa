"""Selección automática del certificado en Chrome (firma sin intervención).

    python src/main.py configurar-certificado            # elegir certificado y activar
    python src/main.py configurar-certificado --quitar   # desactivar

Escribe la política de Chrome AutoSelectCertificateForUrls en el registro de
Windows, limitada a los dominios de Cl@ve y del REG. Con ella Chrome presenta
el certificado elegido sin mostrar el diálogo de selección. Afecta a todo
Chrome del equipo para esos dominios (no a otras webs).

El bot no lee ni copia el certificado ni su clave: solo indica a Chrome cuál usar.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

DOMINIOS = ["https://[*.]clave.gob.es", "https://[*.]redsara.es"]
CLAVE_POLITICA = r"Software\Policies\Google\Chrome\AutoSelectCertificateForUrls"


def listar_certificados() -> list[dict]:
    script = (
        "Get-ChildItem Cert:\\CurrentUser\\My | Where-Object { $_.HasPrivateKey } | "
        "Select-Object Subject, Issuer, NotAfter | ConvertTo-Json -Compress"
    )
    salida = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                            capture_output=True, text=True, check=True).stdout.strip()
    if not salida:
        return []
    datos = json.loads(salida)
    return datos if isinstance(datos, list) else [datos]


def nombre_comun(sujeto: str) -> str:
    m = re.search(r'CN=(?:"([^"]+)"|([^,]+))', sujeto or "")
    return (m.group(1) or m.group(2)).strip() if m else ""


def _escribir(raiz, valores: list[str]) -> None:
    import winreg

    clave = winreg.CreateKeyEx(raiz, CLAVE_POLITICA, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
    with clave:
        # borrar las entradas anteriores del bot
        i = 1
        while True:
            try:
                winreg.DeleteValue(clave, str(i))
                i += 1
            except OSError:
                break
        for i, valor in enumerate(valores, start=1):
            winreg.SetValueEx(clave, str(i), 0, winreg.REG_SZ, valor)


def ejecutar(config: dict, log, quitar: bool = False, entrada=input) -> None:
    if sys.platform != "win32":
        raise SystemExit("Este comando solo funciona en Windows.")
    import winreg

    if quitar:
        for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                _escribir(raiz, [])
            except OSError:
                pass
        log.info("Selección automática de certificado desactivada. Reinicia Chrome.")
        return

    certificados = listar_certificados()
    if not certificados:
        raise SystemExit("No hay certificados con clave privada en el almacén de Windows del usuario.")
    print("\nCertificados instalados:")
    for i, c in enumerate(certificados, start=1):
        print(f"  {i}. {nombre_comun(c['Subject'])}   (emisor: {nombre_comun(c['Issuer'])}, caduca: {c['NotAfter']})")
    while True:
        eleccion = entrada("\nNúmero del certificado que debe usar el bot: ").strip()
        if eleccion.isdigit() and 1 <= int(eleccion) <= len(certificados):
            break
    elegido = certificados[int(eleccion) - 1]
    cn = nombre_comun(elegido["Subject"])
    if not cn:
        raise SystemExit("No se pudo leer el nombre del certificado elegido.")
    valores = [json.dumps({"pattern": d, "filter": {"SUBJECT": {"CN": cn}}}, ensure_ascii=False) for d in DOMINIOS]
    try:
        _escribir(winreg.HKEY_CURRENT_USER, valores)
        sitio = "usuario actual"
    except PermissionError:
        try:
            _escribir(winreg.HKEY_LOCAL_MACHINE, valores)
            sitio = "equipo"
        except PermissionError:
            raise SystemExit("Windows no deja escribir la política. Abre la ventana negra como administrador "
                             "(clic derecho en Símbolo del sistema → Ejecutar como administrador) y repite.")
    log.info(f"Chrome usará automáticamente «{cn}» en {', '.join(DOMINIOS)} (política del {sitio}).")
    log.info("Cierra todas las ventanas de Chrome y vuelve a abrirlo. Puedes comprobarlo en chrome://policy")
