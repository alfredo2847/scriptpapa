"""Vigilante de contratos públicos de paellas para fiestas.

    python src/vigilante.py compradores [--anos 3]   historial: contratos menores, licitaciones pasadas y conjunto
    python src/vigilante.py buscar                   licitaciones abiertas -> datos/licitaciones.xlsx

Solo lee datos públicos de la Plataforma de Contratación del Sector Público.
No envía nada, no usa certificados y no toca la carpeta del bot de registro.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402

import compradores  # noqa: E402
import fichas  # noqa: E402
import informe_compradores  # noqa: E402
import licitaciones  # noqa: E402
import lista  # noqa: E402
from comun import DATOS, DESCARGAS, PROVINCIAS, VERSION, avisar, cargar_config, configurar_log  # noqa: E402
from xml.etree.ElementTree import ParseError  # noqa: E402

from placsp import FeedNoValido, Red, leer_archivo, leer_feed_reciente, urls_historico  # noqa: E402

RUTA_ESTADO = DATOS / "estado.json"


def _fuente_de_archivo(ruta: Path) -> str:
    nombre = ruta.name.lower()
    if "menor" in nombre:
        return "menores"
    if "agregad" in nombre:
        return "agregadas"
    return "licitaciones"


RAIZ_PROYECTO = Path(__file__).resolve().parent.parent

# Un documento por análisis, cada uno en su carpeta:
# (carpeta, informe, hoja, título, orden del ranking)
SALIDAS = {
    "menores": ("historial_contratos_menores", "ANALISIS_CONTRATOS_MENORES.html", "contratos_menores.xlsx",
                "Historial de contratos menores de paellas", "prioridad"),
    "licitaciones": ("historial_licitaciones", "ANALISIS_LICITACIONES.html", "licitaciones_pasadas.xlsx",
                     "Historial de licitaciones de paellas", "prioridad"),
    "conjunto": ("historial_conjunto", "ANALISIS_CONJUNTO.html", "conjunto.xlsx",
                 "Ayuntamientos que más contratan paellas (contratos menores y licitaciones)", "demanda"),
}


def analisis_a_generar(fuentes: list[str]) -> list[str]:
    """Qué documentos salen según las fuentes leídas."""
    hay_menores = "menores" in fuentes
    hay_licitaciones = bool({"licitaciones", "agregadas"} & set(fuentes))
    salida = (["menores"] if hay_menores else []) + (["licitaciones"] if hay_licitaciones else [])
    return salida + (["conjunto"] if hay_menores and hay_licitaciones else [])


def cmd_compradores(args, config, log) -> int:
    anos = args.anos or config["compradores"]["anos"]
    provincias = ", ".join(PROVINCIAS[p]["nombre"] for p in config["provincias"])
    antelacion = config["compradores"]["meses_antelacion"]

    if args.archivo:
        archivos = [(Path(a), _fuente_de_archivo(Path(a))) for a in args.archivo]
        fuentes = sorted({f for _, f in archivos}, key=["menores", "licitaciones", "agregadas"].index)
    else:
        fuentes = args.fuentes.split(",") if args.fuentes else config["compradores"]["fuentes"]
        red = Red(config["red"]["timeout_seg"], config["red"]["reintentos"])
        archivos = [(DESCARGAS / f / url.rsplit("/", 1)[-1], f, url)
                    for f in fuentes for url in urls_historico(config["fuentes"][f], anos)]
    log.info(f"Historial de contratos de paellas de los últimos {anos} años en {provincias} "
             f"(fuentes: {', '.join(fuentes)})")
    fallidas: list[str] = []

    def todos():
        """Descarga cada archivo justo antes de leerlo (y lo borra después si se pide)."""
        for entrada in archivos:
            ruta, fuente = entrada[0], entrada[1]
            if not args.archivo:
                url = entrada[2]
                log.info(f"{'Ya descargado' if ruta.exists() else 'Descargando'}: {url}")
                try:
                    red.descargar(url, ruta)
                except requests.RequestException as e:
                    log.warning(f"  No se pudo descargar ({e})")
                    fallidas.append(url)
                    continue
            log.info(f"Leyendo {ruta.name}")
            try:
                yield from leer_archivo(ruta, fuente)
            except Exception as e:  # un archivo dañado no debe parar el resto
                log.warning(f"  No se pudo leer {ruta.name}: {e}")
            if args.borrar_descargas and not args.archivo:
                ruta.unlink(missing_ok=True)

    hallazgos = compradores.filtrar(todos(), config)
    # Los informes cuentan solo el servicio de paella contratado por ayuntamientos; lo demás
    # (leña, orquestas, ingredientes, otros organismos...) va a la pestaña otros_contratos.
    principales = [h for h in hallazgos if h.principal]
    otros = [h for h in hallazgos if not h.principal]
    grupos = {
        "menores": [h for h in principales if h.via == "Contrato menor"],
        "licitaciones": [h for h in principales if h.via == "Licitación"],
        "conjunto": principales,
    }
    otros_grupo = {
        "menores": [h for h in otros if h.via == "Contrato menor"],
        "licitaciones": [h for h in otros if h.via == "Licitación"],
        "conjunto": otros,
    }
    avisos = []
    if fallidas:
        avisos.append(f"{len(fallidas)} archivos no se pudieron descargar, así que puede faltar parte del "
                      "historial. Se reintentan en la próxima ejecución.")

    informes = []
    ahora = datetime.now()
    for clave in analisis_a_generar(fuentes):
        carpeta, nombre_informe, nombre_hoja, titulo, orden = SALIDAS[clave]
        carpeta = RAIZ_PROYECTO / carpeta
        carpeta.mkdir(parents=True, exist_ok=True)
        res = compradores.guardar(grupos[clave], antelacion, carpeta / nombre_hoja, orden=orden,
                                  otros=otros_grupo[clave])
        informe = informe_compradores.generar(res["analisis"], ahora, carpeta / nombre_informe, avisos, titulo)
        informes.append(informe)
        log.info(f"\n{titulo}: {res['contratos']} contratos en {res['municipios']} ayuntamientos "
                 f"({res['prioridad_1']} clientes recurrentes)")
        for f in res["analisis"]["municipios"][:10]:
            importe = f"{f['importe_medio']:,.0f} €".replace(",", ".") if f["importe_medio"] else "importe ?"
            log.info(f"  [{f['prioridad']}] {f['municipio']} ({f['provincia'] or '?'}): "
                     f"{f['contratos']} contrato(s), {importe} de media, suele contratar en "
                     f"{f['mes_habitual'] or '?'} -> enviar propuesta en {f['enviar_propuesta_en'] or '?'}")
        log.info(f"  Carpeta: {carpeta}")

    if fallidas:
        log.warning(f"\n{len(fallidas)} archivos no se pudieron descargar (puede que aún no existan). "
                    "Si faltan años enteros, descárgalos a mano y usa --archivo <ruta>.")
    if informes and not args.no_abrir and sys.platform == "win32":
        try:
            os.startfile(informes[-1])  # type: ignore[attr-defined]
        except OSError:
            pass
    return 0


def _leer_estado() -> dict:
    try:
        return json.loads(RUTA_ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def crear_fichas(encontradas: dict, existentes: dict, config: dict, ahora: datetime, red, log) -> None:
    """Carpeta con valoración y pliegos para cada licitación que sirve."""
    for ident, fila in encontradas.items():
        if fila["encaje"] not in config["fichas"]["encajes"]:
            continue
        previa = existentes.get(ident, {}).get("carpeta")
        log.info(f"  Ficha: {fila['municipio'] or fila['organo']}: {fila['objeto'][:70]}")
        try:
            carpeta, puntos, etiqueta = fichas.crear(
                fila["_contrato"], fila["encaje"], fila["motivo"], fila["municipio"], ahora, config,
                red=red, log=log, carpeta=Path(previa) if previa else None)
        except OSError as e:
            log.warning(f"    No se pudo crear la carpeta: {e}")
            continue
        fila["valoracion"] = puntos
        fila["carpeta"] = str(carpeta)


def toca_buscar(ahora: datetime, ultimas: dict, temporada: dict) -> tuple[bool, str]:
    """En temporada, siempre; fuera de temporada, si hace N días de la última búsqueda."""
    if ahora.month in temporada["meses"]:
        return True, "temporada: búsqueda diaria"
    fechas = [datetime.fromisoformat(v) for v in ultimas.values() if v]
    if not fechas:
        return True, "primera búsqueda"
    dias = (ahora - min(fechas)).days
    if dias >= temporada["dias_fuera_de_temporada"]:
        return True, f"fuera de temporada: búsqueda semanal (la última fue hace {dias} días)"
    proxima = min(fechas) + timedelta(days=temporada["dias_fuera_de_temporada"])
    return False, f"fuera de temporada: la próxima búsqueda será a partir del {proxima:%d/%m/%Y}"


def cmd_lista(args, config, log) -> int:
    ruta = lista.generar(licitaciones.cargar(), datetime.now())
    log.info(f"Lista: {ruta}")
    return 0


def cmd_buscar(args, config, log) -> int:
    ahora = datetime.now()
    opciones = config["buscar"]
    estado = _leer_estado()
    ultimas = estado.get("ultima_busqueda") or {}
    if isinstance(ultimas, str):  # formato antiguo: una fecha para todas las fuentes
        ultimas = {"licitaciones": ultimas, "agregadas": ultimas}
    if args.programada:
        toca, motivo = toca_buscar(ahora, ultimas, config["temporada"])
        log.info(f"Búsqueda automática: {motivo}")
        if not toca:
            lista.generar(licitaciones.cargar(), ahora)  # refresca días restantes y vencidas
            return 0

    def desde_para(fuente: str) -> datetime:
        if args.dias:
            return ahora - timedelta(days=args.dias)
        if ultimas.get(fuente):
            return datetime.fromisoformat(ultimas[fuente]) - timedelta(days=opciones["solape_dias"])
        return ahora - timedelta(days=opciones["dias_primera_vez"])

    contratos = []
    red = None
    fallidas = []
    if args.archivo:
        for a in args.archivo:
            contratos.extend(leer_archivo(Path(a), _fuente_de_archivo(Path(a))))
    else:
        red = Red(config["red"]["timeout_seg"], config["red"]["reintentos"])
        for fuente in ("licitaciones", "agregadas"):
            desde = desde_para(fuente)
            log.info(f"Fuente '{fuente}': publicadas o cambiadas desde el {desde:%d/%m/%Y %H:%M}")
            try:
                encontrados, paginas = leer_feed_reciente(
                    config["fuentes"][fuente], desde, fuente, red.obtener, opciones["max_paginas"])
            except (requests.RequestException, FeedNoValido, ParseError) as e:
                log.error(f"  No se pudo leer la fuente '{fuente}': {e}")
                log.error("  Se sigue con las demás; esta se volverá a mirar en la próxima búsqueda.")
                fallidas.append(fuente)
                continue
            log.info(f"  {fuente}: {len(encontrados)} expedientes en {paginas} páginas")
            if paginas >= opciones["max_paginas"]:
                log.warning(f"  Se alcanzó el máximo de {paginas} páginas; puede faltar lo más antiguo.")
            contratos.extend(encontrados)
            ultimas[fuente] = ahora.isoformat(timespec="seconds")

    encontradas = licitaciones.abiertas(contratos, config, ahora)
    existentes = licitaciones.cargar()
    retiradas = licitaciones.retirar_sin_paellas(existentes, config, fichas.CARPETA, log)
    if retiradas:
        log.info(f"Retiradas {len(retiradas)} de la hoja que no son de paellas "
                 f"(sus carpetas están en {fichas.CARPETA / '_no_paella'})")
    if not args.sin_fichas:
        crear_fichas(encontradas, existentes, config, ahora, None if args.archivo else red, log)
    nuevas = licitaciones.actualizar(existentes, encontradas, ahora)
    licitaciones.guardar(existentes, ahora)
    aviso = f"No se pudo consultar: {', '.join(fallidas)}. Se volverá a intentar en la próxima búsqueda." \
        if fallidas else ""
    ruta_lista = lista.generar(existentes, ahora, aviso)
    log.info(f"Lista actualizada: {ruta_lista}")
    if not args.archivo:
        DATOS.mkdir(parents=True, exist_ok=True)
        RUTA_ESTADO.write_text(json.dumps({"ultima_busqueda": ultimas}), encoding="utf-8")

    log.info(f"\n{len(encontradas)} licitaciones abiertas que encajan; {len(nuevas)} nuevas. "
             f"Hoja: {licitaciones.RUTA}")
    if not args.sin_fichas:
        log.info(f"Carpetas con la valoración de cada una: {fichas.CARPETA}")
    for f in nuevas:
        plazo = f["plazo"].strftime("%d/%m %H:%M") if f.get("plazo") else "sin plazo"
        importe = f"{f['importe']:,.0f} €".replace(",", ".") if f.get("importe") else "importe ?"
        nota = f", {f['valoracion']}/100" if f.get("valoracion") is not None else ""
        log.info(f"  NUEVA [{f['encaje']}{nota}] {f['municipio'] or f['organo']}: {f['objeto']} "
                 f"({importe}, plazo {plazo})")

    pronto = licitaciones.recordatorios(existentes, ahora, opciones["aviso_dias_plazo"])
    for f in pronto:
        log.info(f"  VENCE PRONTO: {f['municipio'] or f['organo']}: {f['objeto']} (plazo {f['plazo']:%d/%m %H:%M})")

    mensajes = []
    if fallidas:
        mensajes.append(f"no se pudo leer: {', '.join(fallidas)} (mira el log)")
    if nuevas:
        resumen = "; ".join(f"{f['municipio'] or f['organo']} ({f['encaje']})" for f in nuevas[:5])
        mensajes.append(f"{len(nuevas)} nueva(s): {resumen}")
    if pronto:
        mensajes.append(f"{len(pronto)} marcada(s) ME INTERESA vence(n) pronto")
    if mensajes:
        mensajes.append("Abre 'Licitaciones de paellas' en el escritorio")
        avisar("Licitaciones de paellas", ". ".join(mensajes))
    return 1 if fallidas and not contratos else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vigilante de contratos públicos de paellas para fiestas")
    sub = parser.add_subparsers(dest="comando", required=True)

    s = sub.add_parser("compradores", help="histórico de contratos: quién contrata paellas, cuándo y a quién")
    s.add_argument("--anos", type=int, help="años completos hacia atrás (por defecto, config.yaml)")
    s.add_argument("--fuentes", help="por defecto las tres: menores,licitaciones,agregadas")
    s.add_argument("--archivo", nargs="+", help="usar ZIP/ATOM ya descargados en vez de descargarlos")
    s.add_argument("--no-abrir", action="store_true", help="no abrir el informe al terminar")
    s.add_argument("--borrar-descargas", action="store_true",
                   help="borrar cada archivo descargado después de leerlo (ahorra disco)")

    s = sub.add_parser("buscar", help="licitaciones abiertas que encajan -> datos/licitaciones.xlsx")
    s.add_argument("--dias", type=float, help="mirar N días atrás en vez de desde la última búsqueda")
    s.add_argument("--archivo", nargs="+", help="usar ATOM/ZIP ya descargados (pruebas)")
    s.add_argument("--sin-fichas", action="store_true", help="no crear carpetas ni descargar pliegos")
    s.add_argument("--programada", action="store_true",
                   help="la usa la tarea de Windows: diaria en temporada, semanal fuera de ella")

    sub.add_parser("lista", help="rehacer LISTA_LICITACIONES.html desde la hoja (sin buscar)")

    args = parser.parse_args(argv)
    config = cargar_config()
    log = configurar_log(args.comando)
    provincias = ", ".join(PROVINCIAS[p]["nombre"] for p in config["provincias"])
    filtro = "solo paellas" if config.get("solo_paellas", True) else "paellas, catering y comidas de fiestas"
    log.info(f"Vigilante versión {VERSION}. Provincias: {provincias}. Filtro: {filtro}.")
    if args.comando == "compradores":
        return cmd_compradores(args, config, log)
    if args.comando == "lista":
        return cmd_lista(args, config, log)
    return cmd_buscar(args, config, log)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrumpido.")
        sys.exit(130)
