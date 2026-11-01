"""Vigilante de contratos públicos de paellas para fiestas.

    python src/vigilante.py compradores [--anos 3]   histórico -> datos/compradores.xlsx
    python src/vigilante.py buscar                   licitaciones abiertas -> datos/licitaciones.xlsx

Solo lee datos públicos de la Plataforma de Contratación del Sector Público.
No envía nada, no usa certificados y no toca la carpeta del bot de registro.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402

import compradores  # noqa: E402
import licitaciones  # noqa: E402
from comun import DATOS, DESCARGAS, PROVINCIAS, avisar, cargar_config, configurar_log  # noqa: E402
from placsp import Red, leer_archivo, leer_feed_reciente, urls_historico  # noqa: E402

RUTA_ESTADO = DATOS / "estado.json"


def _fuente_de_archivo(ruta: Path) -> str:
    nombre = ruta.name.lower()
    if "menor" in nombre:
        return "menores"
    if "agregad" in nombre:
        return "agregadas"
    return "licitaciones"


def cmd_compradores(args, config, log) -> int:
    anos = args.anos or config["compradores"]["anos"]
    provincias = ", ".join(PROVINCIAS[p]["nombre"] for p in config["provincias"])
    log.info(f"Histórico de contratos de los últimos {anos} años en {provincias}")

    archivos: list[tuple[Path, str]] = []
    fallidas: list[str] = []
    if args.archivo:
        archivos = [(Path(a), _fuente_de_archivo(Path(a))) for a in args.archivo]
    else:
        red = Red(config["red"]["timeout_seg"], config["red"]["reintentos"])
        fuentes = args.fuentes.split(",") if args.fuentes else config["compradores"]["fuentes"]
        for fuente in fuentes:
            for url in urls_historico(config["fuentes"][fuente], anos):
                destino = DESCARGAS / fuente / url.rsplit("/", 1)[-1]
                ya = destino.exists()
                log.info(f"{'Ya descargado' if ya else 'Descargando'}: {url}")
                try:
                    archivos.append((red.descargar(url, destino), fuente))
                except requests.RequestException as e:
                    log.warning(f"  No se pudo descargar ({e})")
                    fallidas.append(url)

    def todos():
        for ruta, fuente in archivos:
            log.info(f"Leyendo {ruta.name}")
            try:
                yield from leer_archivo(ruta, fuente)
            except Exception as e:  # un archivo dañado no debe parar el resto
                log.warning(f"  No se pudo leer {ruta.name}: {e}")

    hallazgos = compradores.filtrar(todos(), config)
    res = compradores.guardar(hallazgos, config["compradores"]["meses_antelacion"])
    log.info(f"\nListo: {res['contratos']} contratos en {res['municipios']} municipios "
             f"({res['prioridad_1']} con prioridad 1). Hoja: {compradores.RUTA}")
    if fallidas:
        log.warning(f"\n{len(fallidas)} archivos no se pudieron descargar (puede que aún no existan). "
                    "Si faltan años enteros, descárgalos a mano y usa --archivo <ruta>.")
    return 0


def _leer_estado() -> dict:
    try:
        return json.loads(RUTA_ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def cmd_buscar(args, config, log) -> int:
    ahora = datetime.now()
    opciones = config["buscar"]
    estado = _leer_estado()
    if args.dias:
        desde = ahora - timedelta(days=args.dias)
    elif estado.get("ultima_busqueda"):
        desde = datetime.fromisoformat(estado["ultima_busqueda"]) - timedelta(days=opciones["solape_dias"])
    else:
        desde = ahora - timedelta(days=opciones["dias_primera_vez"])

    contratos = []
    if args.archivo:
        for a in args.archivo:
            contratos.extend(leer_archivo(Path(a), _fuente_de_archivo(Path(a))))
    else:
        red = Red(config["red"]["timeout_seg"], config["red"]["reintentos"])
        log.info(f"Buscando licitaciones publicadas o cambiadas desde el {desde:%d/%m/%Y %H:%M}")
        for fuente in ("licitaciones", "agregadas"):
            try:
                encontrados, paginas = leer_feed_reciente(
                    config["fuentes"][fuente], desde, fuente, red.obtener, opciones["max_paginas"])
            except requests.RequestException as e:
                log.error(f"No se pudo leer la fuente '{fuente}': {e}")
                avisar("Vigilante de licitaciones", f"No se pudo consultar la plataforma ({fuente}). Mira el log.")
                return 1
            log.info(f"  {fuente}: {len(encontrados)} expedientes en {paginas} páginas")
            if paginas >= opciones["max_paginas"]:
                log.warning(f"  Se alcanzó el máximo de {paginas} páginas; puede faltar lo más antiguo.")
            contratos.extend(encontrados)

    encontradas = licitaciones.abiertas(contratos, config, ahora)
    existentes = licitaciones.cargar()
    nuevas = licitaciones.actualizar(existentes, encontradas, ahora)
    licitaciones.guardar(existentes, ahora)
    if not args.archivo:
        DATOS.mkdir(parents=True, exist_ok=True)
        RUTA_ESTADO.write_text(json.dumps({"ultima_busqueda": ahora.isoformat(timespec="seconds")}),
                               encoding="utf-8")

    log.info(f"\n{len(encontradas)} licitaciones abiertas que encajan; {len(nuevas)} nuevas. "
             f"Hoja: {licitaciones.RUTA}")
    for f in nuevas:
        plazo = f["plazo"].strftime("%d/%m %H:%M") if f.get("plazo") else "sin plazo"
        importe = f"{f['importe']:,.0f} €".replace(",", ".") if f.get("importe") else "importe ?"
        log.info(f"  NUEVA [{f['encaje']}] {f['municipio'] or f['organo']}: {f['objeto']} ({importe}, plazo {plazo})")

    pronto = licitaciones.recordatorios(existentes, ahora, opciones["aviso_dias_plazo"])
    for f in pronto:
        log.info(f"  VENCE PRONTO: {f['municipio'] or f['organo']}: {f['objeto']} (plazo {f['plazo']:%d/%m %H:%M})")

    mensajes = []
    if nuevas:
        lista = "; ".join(f"{f['municipio'] or f['organo']} ({f['encaje']})" for f in nuevas[:5])
        mensajes.append(f"{len(nuevas)} nueva(s): {lista}")
    if pronto:
        mensajes.append(f"{len(pronto)} marcada(s) ME INTERESA vence(n) pronto")
    if mensajes:
        avisar("Licitaciones de paellas", ". ".join(mensajes))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vigilante de contratos públicos de paellas para fiestas")
    sub = parser.add_subparsers(dest="comando", required=True)

    s = sub.add_parser("compradores", help="histórico de contratos: quién contrata paellas, cuándo y a quién")
    s.add_argument("--anos", type=int, help="años completos hacia atrás (por defecto, config.yaml)")
    s.add_argument("--fuentes", help="menores,licitaciones,agregadas (por defecto, todas)")
    s.add_argument("--archivo", nargs="+", help="usar ZIP/ATOM ya descargados en vez de descargarlos")

    s = sub.add_parser("buscar", help="licitaciones abiertas que encajan -> datos/licitaciones.xlsx")
    s.add_argument("--dias", type=float, help="mirar N días atrás en vez de desde la última búsqueda")
    s.add_argument("--archivo", nargs="+", help="usar ATOM/ZIP ya descargados (pruebas)")

    args = parser.parse_args(argv)
    config = cargar_config()
    log = configurar_log(args.comando)
    if args.comando == "compradores":
        return cmd_compradores(args, config, log)
    return cmd_buscar(args, config, log)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrumpido.")
        sys.exit(130)
