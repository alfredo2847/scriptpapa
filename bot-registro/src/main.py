"""Bot de envío por registro a los ayuntamientos de la provincia de Valencia.

Uso:
  python src/main.py inventario [--archivo DIR3.xlsx] [--poblacion pobmun.xlsx] [--forzar]
  python src/main.py detectar [--sin-rec] [--dir3 L01462508 ...]
  python src/main.py enviar --prueba --max 5
  python src/main.py enviar --max 5 --confirmar
  python src/main.py informe
  python src/main.py grabar [--url https://rec.redsara.es/]
  python src/main.py marcar L01462508 --estado ENVIADO --num REGAGE26e00012345678
  python src/main.py validar-huellas

Principio rector: cada envío es un acto oficial firmado y no se puede deshacer.
Ante la duda, el script no envía.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from comun import ahora_texto, cargar_config, configurar_log  # noqa: E402
from hoja import ESTADOS, HojaControl  # noqa: E402


def cmd_inventario(args, config, log):
    import inventario

    inventario.ejecutar(config, log, archivo=args.archivo, poblacion=args.poblacion, forzar=args.forzar)


def cmd_detectar(args, config, log):
    import deteccion_via

    deteccion_via.ejecutar(config, log, sin_rec=args.sin_rec, solo=args.dir3, solo_rec=args.solo_rec)


def cmd_enviar(args, config, log):
    import envio

    confirmar = True if args.confirmar else (False if args.sin_confirmar else None)
    envio.ejecutar(config, log, prueba=args.prueba, maximo=args.max, confirmar=confirmar,
                   solo=args.dir3, reintentar_errores=args.reintentar_errores)


def cmd_informe(args, config, log):
    import informe

    informe.ejecutar(config, log)


def cmd_grabar(args, config, log):
    import grabador

    grabador.ejecutar(config, log, url=args.url)


def cmd_analizar(args, config, log):
    import analizar_capturas

    analizar_capturas.ejecutar(config, log, carpeta=args.carpeta)


def cmd_explorar(args, config, log):
    import explorar_reg

    explorar_reg.ejecutar(config, log)


def cmd_certificado(args, config, log):
    import configurar_certificado

    configurar_certificado.ejecutar(config, log, quitar=args.quitar)


def cmd_marcar(args, config, log):
    hoja = HojaControl()
    fila = hoja.get(args.dir3)
    if not fila:
        raise SystemExit(f"{args.dir3} no está en la hoja de control")
    hoja.copia_seguridad()
    anterior = fila.get("estado")
    fila["estado"] = args.estado
    if args.num:
        fila["num_registro"] = args.num
    if args.estado == "ENVIADO" and not fila.get("fecha_envio"):
        fila["fecha_envio"] = args.fecha or ahora_texto()
    elif args.fecha:
        fila["fecha_envio"] = args.fecha
    if args.justificante:
        fila["justificante"] = args.justificante
    if args.nota is not None:
        fila["notas"] = args.nota
    hoja.guardar()
    log.info(f"{fila['municipio']} ({args.dir3}): {anterior} -> {args.estado}")


def cmd_validar_huellas(args, config, log):
    from motor import CARPETA_HUELLAS, Flujo, hash_huellas

    for ruta in sorted(CARPETA_HUELLAS.rglob("*.yaml")):
        if ruta.name == "plataformas.yaml" or ruta.name.startswith("borrador"):
            continue
        flujo = Flujo(ruta)
        estado = "verificada" if flujo.verificada else "SIN VERIFICAR"
        log.info(f"{ruta.relative_to(CARPETA_HUELLAS)}: válida, {len(flujo.pantallas)} pantallas, {estado}")
    log.info(f"Huella del conjunto: {hash_huellas()}")


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Bot de envío por registro a ayuntamientos")
    p.add_argument("--config", help="ruta de config.yaml")
    sub = p.add_subparsers(dest="orden", required=True)

    s = sub.add_parser("inventario", help="fase 1: lista de ayuntamientos desde el DIR3")
    s.add_argument("--archivo", help="listado DIR3 ya descargado (xlsx, csv o zip)")
    s.add_argument("--poblacion", help="fichero de población del INE (pobmunXX.xlsx)")
    s.add_argument("--forzar", action="store_true", help="guardar aunque el recuento no sea 266")
    s.set_defaults(func=cmd_inventario)

    s = sub.add_parser("detectar", help="fase 2: vía de envío de cada ayuntamiento (no envía nada)")
    s.add_argument("--sin-rec", action="store_true", help="no abrir el REC; solo buscar sedes")
    s.add_argument("--solo-rec", action="store_true", help="solo comprobar el REC (no vuelve a buscar sedes)")
    s.add_argument("--dir3", nargs="+", help="solo estos ayuntamientos")
    s.set_defaults(func=cmd_detectar)

    s = sub.add_parser("enviar", help="fases 3 y 4: presentar los registros")
    s.add_argument("--prueba", action="store_true", help="todo menos firmar; marca PRUEBA_OK")
    s.add_argument("--max", type=int, help="máximo de ayuntamientos en esta tanda")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--confirmar", action="store_true", help="pedir s/n antes de cada firma")
    g.add_argument("--sin-confirmar", action="store_true", help="no pedir confirmación por consola")
    s.add_argument("--dir3", nargs="+", help="solo estos ayuntamientos")
    s.add_argument("--reintentar-errores", action="store_true",
                   help="incluir los que están en ERROR (nunca los ENVIADO ni REVISAR)")
    s.set_defaults(func=cmd_enviar)

    s = sub.add_parser("informe", help="resumen y datos/manuales.xlsx")
    s.set_defaults(func=cmd_informe)

    s = sub.add_parser("grabar", help="capturar un envío manual de referencia para escribir las huellas")
    s.add_argument("--url", help="página de inicio (por defecto la del REC)")
    s.set_defaults(func=cmd_grabar)

    s = sub.add_parser("analizar-capturas", help="resumir campos y botones de las capturas de referencia")
    s.add_argument("--carpeta", help="carpeta capturas/referencia_<fecha> (por defecto la última)")
    s.set_defaults(func=cmd_analizar)

    s = sub.add_parser("explorar-reg", help="leer la estructura del formulario del REG (no envía nada)")
    s.set_defaults(func=cmd_explorar)

    s = sub.add_parser("configurar-certificado", help="que Chrome elija solo el certificado en Cl@ve y el REG")
    s.add_argument("--quitar", action="store_true", help="desactivar la selección automática")
    s.set_defaults(func=cmd_certificado)

    s = sub.add_parser("marcar", help="anotar a mano el resultado de un ayuntamiento")
    s.add_argument("dir3")
    s.add_argument("--estado", required=True, choices=ESTADOS)
    s.add_argument("--num", help="número de registro")
    s.add_argument("--fecha", help="fecha y hora del registro")
    s.add_argument("--justificante", help="ruta del PDF del justificante")
    s.add_argument("--nota", help="texto para la columna notas")
    s.set_defaults(func=cmd_marcar)

    s = sub.add_parser("validar-huellas", help="comprobar la sintaxis de huellas/")
    s.set_defaults(func=cmd_validar_huellas)
    return p


def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        try:  # consolas de Windows con codificaciones antiguas
            flujo.reconfigure(errors="replace")
        except AttributeError:
            pass
    args = construir_parser().parse_args(argv)
    config = cargar_config(Path(args.config) if args.config else None)
    log = configurar_log(args.orden)
    log.info(f"=== {args.orden} {ahora_texto()} ===")
    try:
        args.func(args, config, log)
    except KeyboardInterrupt:
        log.error("Interrumpido por el usuario.")
        return 130
    except Exception as e:  # noqa: BLE001 - mensaje claro en consola y traza completa en el log
        nombre = type(e).__name__
        if nombre in ("InventarioError", "EnvioNoPermitido", "HuellaInvalida", "HojaBloqueada"):
            log.error(f"{e}")
        else:
            log.exception(f"Error inesperado: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
