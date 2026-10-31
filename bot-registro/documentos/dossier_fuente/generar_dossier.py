"""Genera documentos/dossier.pdf a partir de dossier.html y la carpeta fotos/.

Uso (desde bot-registro, con el entorno activado):
    python documentos/dossier_fuente/generar_dossier.py
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent
DESTINO = AQUI.parent / "dossier.pdf"


def main(canal: str = "chrome") -> None:
    with sync_playwright() as p:
        navegador = p.chromium.launch(channel=canal or None)
        pagina = navegador.new_page()
        pagina.goto((AQUI / "dossier.html").as_uri(), wait_until="networkidle")
        pagina.pdf(path=str(DESTINO), prefer_css_page_size=True, print_background=True)
        navegador.close()
    print(f"Dossier generado: {DESTINO} ({DESTINO.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "chrome")
