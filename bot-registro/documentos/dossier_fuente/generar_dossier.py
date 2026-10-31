"""Genera documentos/dossier.pdf y documentos/carta.pdf a partir de dossier.html,
carta.html y la carpeta fotos/.

Uso (desde bot-registro, con el entorno activado):
    python documentos/dossier_fuente/generar_dossier.py
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent
DOCUMENTOS = {"dossier.html": AQUI.parent / "dossier.pdf", "carta.html": AQUI.parent / "carta.pdf"}


def main(canal: str = "chrome") -> None:
    with sync_playwright() as p:
        navegador = p.chromium.launch(channel=canal or None)
        pagina = navegador.new_page()
        for origen, destino in DOCUMENTOS.items():
            pagina.goto((AQUI / origen).as_uri(), wait_until="networkidle")
            pagina.pdf(path=str(destino), prefer_css_page_size=True, print_background=True)
            print(f"Generado: {destino} ({destino.stat().st_size / 1024 / 1024:.1f} MB)")
        navegador.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "chrome")
