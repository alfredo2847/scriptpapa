"""Fase 2: detección de la vía de envío de cada ayuntamiento. No firma ni presenta nada.

Orden de preferencia:
 1. REC: el ayuntamiento aparece en el buscador de destinatarios del REC con su código DIR3.
 2. Sede con plataforma conocida: campo web del DIR3, patrones de dominio habituales
    y enlaces "sede" de la web municipal; la plataforma se reconoce por su huella.
 3. MANUAL: sede no encontrada o plataforma sin adaptador.

Solo se procesan los ayuntamientos PENDIENTES (o en ERROR/PRUEBA_OK, que aún no se han enviado).
"""

from __future__ import annotations

import html as html_lib
import re
import warnings
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

from comun import PATRON_AYTO_VALENCIA, ahora_texto, contiene_municipio, slugs_municipio, variantes_municipio
from hoja import ERROR, PENDIENTE, PRUEBA_OK, VIA_MANUAL, VIA_REC, HojaControl
from sedes.base import cargar_plataformas, identificar_plataforma

ESTADOS_A_DETECTAR = (PENDIENTE, PRUEBA_OK, ERROR, "")

PATRONES_SEDE = (
    "https://sede.{slug}.es",
    "https://{slug}.sedelectronica.es",
    "https://{slug}.sedipualba.es",
)
PATRONES_WEB = ("https://www.{slug}.es", "https://{slug}.es")

CABECERAS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9,ca;q=0.8",
}


def _descargar(sesion, url: str, timeout: float) -> tuple[str, str] | None:
    """Devuelve (url_final, html) o None. Solo lectura de páginas públicas."""
    import requests
    from urllib3.exceptions import InsecureRequestWarning

    for verificar_tls in (True, False):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", InsecureRequestWarning)
                r = sesion.get(url, timeout=timeout, verify=verificar_tls, allow_redirects=True)
            if r.status_code >= 400:
                return None
            tipo = r.headers.get("content-type", "")
            if "html" not in tipo and "text" not in tipo:
                return None
            return r.url, r.text[:400_000]
        except requests.exceptions.SSLError:
            continue  # muchas webs municipales tienen certificados mal configurados
        except requests.RequestException:
            return None
    return None


def _enlaces_sede(url_base: str, html: str) -> list[str]:
    enlaces = []
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
        href, texto = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
        if re.search(r"\bsede\b|sedelectronica|sedipualba|seu electr", href + " " + texto, re.IGNORECASE):
            enlaces.append(urljoin(url_base, href))
    return list(dict.fromkeys(enlaces))[:5]


def texto_visible(html: str) -> str:
    sin_scripts = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    return html_lib.unescape(re.sub(r"<[^>]+>", " ", sin_scripts))


def menciona_municipio(html: str, municipio: str) -> bool:
    """La página habla de ese municipio (título o texto visible).

    Algunas plataformas responden con una página genérica a cualquier subdominio
    (p. ej. pueblo-inventado.sedelectronica.es); sin el nombre del municipio no
    se puede saber si la sede es suya.
    """
    return contiene_municipio(texto_visible(html), municipio)


def es_de_valencia(html: str, nif: str = "") -> bool:
    """La página es de un ayuntamiento de la provincia de Valencia.

    Se exige el NIF del ayuntamiento, un código postal 46xxx o la provincia
    entre paréntesis.
    """
    texto = texto_visible(html)
    if nif and nif.upper() in texto.upper().replace("-", ""):
        return True
    if re.search(r"(?<!\d)46\d{3}(?!\d)", texto):
        return True
    return bool(re.search(r"\((val[eè]ncia|valencia/val[eè]ncia|val[eè]ncia/valencia)\)", texto, re.IGNORECASE))


def leer_homonimos(texto: str) -> list[tuple[str, str]]:
    """'Alcúdia (L01070034); Alcúdia de Crespins (L01460207)' -> [(nombre, código), ...]."""
    return re.findall(r"\s*(.+?) \((L\w+)\)(?:;|$)", texto or "")


def es_sede_de(html: str, municipio: str, nif: str = "", homonimos: list[tuple[str, str]] = ()) -> bool:
    """La página es la del ayuntamiento de `municipio` y no la de un homónimo.

    - Tiene que nombrar al municipio.
    - Si nombra a un ayuntamiento de nombre más largo que lo contiene
      (Castelló de la Plana para Castelló), se descarta.
    - Si hay un ayuntamiento con el mismo nombre fuera de Valencia, la página
      tiene que demostrar que es de la provincia (NIF, código postal o provincia).
    """
    texto = texto_visible(html)
    if not contiene_municipio(texto, municipio):
        return False
    propias = set(variantes_municipio(municipio))
    mismo_nombre_fuera = False
    for nombre, codigo in homonimos:
        if propias & set(variantes_municipio(nombre)):
            mismo_nombre_fuera = mismo_nombre_fuera or not PATRON_AYTO_VALENCIA.match(codigo)
        elif contiene_municipio(texto, nombre):
            return False
    return es_de_valencia(html, nif) if mismo_nombre_fuera else True


def buscar_sede(municipio: str, web_dir3: str, timeout: float, plataformas: dict,
                nif: str = "", homonimos: list[tuple[str, str]] = ()) -> tuple[str, str]:
    """Devuelve (url_sede, plataforma). plataforma vacía si no se reconoce; url vacía si no hay sede.

    Solo cuentan las páginas que son de ese ayuntamiento (ver es_sede_de).
    """
    import requests

    sesion = requests.Session()
    sesion.headers.update(CABECERAS)
    slugs = slugs_municipio(municipio)
    primera_sede = ""

    def es_suya(html: str) -> bool:
        return es_sede_de(html, municipio, nif, homonimos)

    def probar(url: str) -> tuple[str, str] | None:
        nonlocal primera_sede
        respuesta = _descargar(sesion, url, timeout)
        if not respuesta:
            return None
        url_final, html = respuesta
        if not es_suya(html):
            return None
        plataforma = identificar_plataforma(url_final, html, plataformas)
        if plataforma:
            return url_final, plataforma
        if not primera_sede and re.search(r"sede|seu", urlparse(url_final).hostname or "", re.IGNORECASE):
            primera_sede = url_final
        return None

    webs = []
    if web_dir3:
        web = web_dir3 if web_dir3.startswith("http") else f"https://{web_dir3}"
        resultado = probar(web)
        if resultado:
            return resultado
        webs.append(web)
    for patron in PATRONES_SEDE:
        for slug in slugs:
            resultado = probar(patron.format(slug=slug))
            if resultado:
                return resultado
    webs += [p.format(slug=s) for p in PATRONES_WEB for s in slugs]
    for web in webs:
        respuesta = _descargar(sesion, web, timeout)
        if not respuesta:
            continue
        url_final, html = respuesta
        if not es_suya(html):
            continue  # el dominio existe pero no es la web de este ayuntamiento
        for enlace in _enlaces_sede(url_final, html):
            resultado = probar(enlace)
            if resultado:
                return resultado
        break  # basta con la primera web municipal que responde
    return primera_sede, ""


def ejecutar(config: dict, log, sin_rec: bool = False, solo: list[str] | None = None,
             solo_rec: bool = False) -> None:
    hoja = HojaControl()
    if not len(hoja):
        raise SystemExit("La hoja de control está vacía: ejecuta antes 'python src/main.py inventario'.")
    copia = hoja.copia_seguridad()
    if copia:
        log.info(f"Copia de la hoja en {copia}")

    if not any(f.get("nif_ayto") for f in hoja):
        raise SystemExit("La hoja no tiene los datos nuevos del inventario (NIF y homónimos). "
                         "Ejecuta antes: python src/main.py inventario --archivo <DIR3>")
    filas = [f for f in hoja.ordenadas() if f.get("estado", "") in ESTADOS_A_DETECTAR]
    if solo:
        filas = [f for f in filas if f["dir3_ayto"] in solo]
    log.info(f"Detección de vía para {len(filas)} ayuntamientos pendientes")

    en_rec: set[str] | None = None
    if not sin_rec:
        en_rec = _detectar_rec(config, log, hoja, filas)
    rec_comprobado = en_rec is not None
    en_rec = en_rec or set()

    if solo_rec:
        hoja.guardar()
        resumen(hoja, config, log)
        return

    plataformas = cargar_plataformas()
    timeout = float(config["deteccion"].get("timeout_http_seg", 10))
    restantes = [f for f in filas if f["dir3_ayto"] not in en_rec]
    log.info(f"Buscando sede electrónica de {len(restantes)} ayuntamientos")
    hechos = 0
    with ThreadPoolExecutor(max_workers=int(config["deteccion"].get("hilos", 6))) as grupo:
        tareas = {
            grupo.submit(buscar_sede, f["municipio"], str(f.get("web_dir3") or ""), timeout, plataformas,
                         str(f.get("nif_ayto") or ""), leer_homonimos(str(f.get("homonimos") or ""))): f
            for f in restantes
        }
        for tarea in as_completed(tareas):
            fila = tareas[tarea]
            try:
                url, plataforma = tarea.result()
            except Exception as e:  # una web rota no para la detección
                url, plataforma = "", ""
                log.warning(f"{fila['municipio']}: error buscando la sede: {e}")
            fila["url_sede"] = url  # sin restos de detecciones anteriores
            fila["plataforma_sede"] = plataforma
            if fila.get("via") == VIA_REC and not rec_comprobado:
                pass  # sin comprobar el REC en esta pasada se mantiene la vía preferida
            else:
                fila["via"] = plataforma or VIA_MANUAL
            fila["fecha_deteccion"] = ahora_texto()
            log.info(f"{fila['municipio']:<35} {fila['via']:<14} {fila['url_sede']}")
            hechos += 1
            if hechos % 20 == 0:
                hoja.guardar()
    hoja.guardar()
    resumen(hoja, config, log)


def _detectar_rec(config, log, hoja, filas) -> set[str] | None:
    """Devuelve los ayuntamientos encontrados en el REC, o None si no se ha podido comprobar."""
    from motor import ErrorAyuntamiento, HuellaInvalida, Navegador, PantallaDesconocida
    from rec import DetectorREC, cargar_flujo_rec
    from salvaguardas import avisar

    try:
        flujo = cargar_flujo_rec()
    except (FileNotFoundError, HuellaInvalida) as e:
        log.warning(f"No se comprueba el REC: {e}")
        return None
    if not flujo.verificada or not flujo.datos.get("deteccion"):
        log.warning("No se comprueba el REC: huellas/rec.yaml aún no está verificado con el envío manual "
                    "de referencia (fase 3 del plan). Se buscan solo las sedes.")
        return None

    en_rec: set[str] = set()
    comprobados: set[str] = set()
    completa = True
    navegador = Navegador(config)
    try:
        detector = DetectorREC(navegador, flujo, config, log)
        detector.preparar()
        for fila in filas:
            try:
                encontrado, _ = detector.esta_en_rec(fila["dir3_ayto"])
            except ErrorAyuntamiento as e:
                log.warning(f"{fila['municipio']}: no se pudo comprobar en el REC ({e})")
                completa = False
                continue
            comprobados.add(fila["dir3_ayto"])
            if encontrado:
                en_rec.add(fila["dir3_ayto"])
                fila["via"] = VIA_REC
                fila["fecha_deteccion"] = ahora_texto()
            log.info(f"{fila['municipio']:<35} {'REC' if encontrado else 'no está en el REC'}")
    except (PantallaDesconocida, ErrorAyuntamiento) as e:
        detector.motor.capturar("deteccion_rec_parada")
        avisar("Detección REC detenida", str(e))
        log.error(f"Detección REC detenida: {e}")
        completa = False
    finally:
        hoja.guardar()
        navegador.cerrar()
    if not completa:
        log.warning("La comprobación del REC no fue completa: no se cambia la vía de quienes ya estaban en REC.")
        # Para los que no se han podido comprobar se conserva la vía REC previa.
        for fila in filas:
            if fila.get("via") == VIA_REC and fila["dir3_ayto"] not in comprobados:
                en_rec.add(fila["dir3_ayto"])
    return en_rec


def resumen(hoja: HojaControl, config: dict, log) -> None:
    pendientes = [f for f in hoja if f.get("estado", "") in ESTADOS_A_DETECTAR]
    vias = Counter(f.get("via") or "(sin detectar)" for f in pendientes)
    minimo = int(config["deteccion"].get("min_ayuntamientos_adaptador", 10))
    log.info("\nResumen de vías (ayuntamientos pendientes):")
    for via, n in vias.most_common():
        nota = ""
        if via not in (VIA_REC, VIA_MANUAL, "(sin detectar)"):
            nota = "  -> merece adaptador" if n >= minimo else f"  -> menos de {minimo}: irán a MANUAL"
        log.info(f"  {via:<20} {n:>4}{nota}")
