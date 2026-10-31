"""Motor de huellas: comprueba cada pantalla antes de actuar y ejecuta pasos declarados en YAML.

Cada plataforma (REC o una sede) se describe en un archivo de huellas/ con:

  pantallas:   huella de cada pantalla (patrón de URL, título y etiquetas esperadas)
  apertura:    pasos hasta tener el formulario abierto (acceso, inicio de sesión, trámite)
  rellenado:   pasos para rellenar interesado, textos, destinatario y adjuntos hasta el resumen
  destinatario, resumen, firma, justificante: secciones especiales

Un paso es un diccionario con:
  pantalla: <nombre>          la pantalla tiene que coincidir con su huella antes de actuar
  si_pantalla: <nombre>       el paso solo se ejecuta si estamos en esa pantalla (p. ej. login)
  esperar_pantalla: <nombre>  espera a que la persona actúe hasta llegar a esa pantalla
  timeout_seg: N              tiempo máximo de espera_pantalla
  mensaje: texto              aviso para la persona
  acciones: [ ... ]           lista de acciones (ver ACCIONES)

Si una pantalla no coincide con su huella, se lanza PantallaDesconocida: se para la tanda.
Si una acción falla en una pantalla conocida, se lanza ErrorAyuntamiento: se salta ese ayuntamiento.
"""

from __future__ import annotations

import hashlib
import re
import sys
import time
from pathlib import Path

import yaml

from comun import PATRON_CODIGO_DIR3, RAIZ, marca_tiempo, nombre_archivo_seguro, normalizar, rellenar_plantilla

CARPETA_HUELLAS = RAIZ / "huellas"
CARPETA_CAPTURAS = RAIZ / "capturas"

CLAVES_PASO = {"pantalla", "si_pantalla", "esperar_pantalla", "timeout_seg", "mensaje", "acciones", "nota"}
ACCIONES = {
    "ir",                   # ir: "{url_inicio}"
    "clic",                 # clic: "selector"
    "clic_nueva_pestana",   # clic que abre una pestaña nueva; se continúa en ella
    "rellenar",             # rellenar: {selector: "...", valor: "{asunto}"}
    "seleccionar",          # seleccionar: {selector: "...", valor: "..."} (opción de un desplegable)
    "marcar",               # marcar: "selector" (casilla)
    "adjuntar",             # adjuntar: {selector: "...", archivo: carta | dossier | todos}
    "pulsar",               # pulsar: {selector: "...", tecla: "Enter"}
    "esperar",              # esperar: 2 (segundos)
    "esperar_selector",     # esperar_selector: "selector"
    "elegir_destinatario",  # elegir_destinatario: true (usa la sección destinatario)
}


class DetenerTanda(Exception):
    """Detiene la tanda entera."""


class PantallaDesconocida(DetenerTanda):
    """La pantalla no coincide con la huella esperada."""


class ErrorAyuntamiento(Exception):
    """Detiene el envío de ese ayuntamiento; la tanda sigue."""


class HuellaInvalida(Exception):
    pass


def hash_huellas(carpeta: Path = CARPETA_HUELLAS) -> str:
    """Huella de todos los archivos de huellas: si cambia alguno, hay que repetir el modo prueba."""
    h = hashlib.sha256()
    for ruta in sorted(carpeta.rglob("*.yaml")):
        if ruta.name.startswith(("_", "borrador")):
            continue
        h.update(str(ruta.relative_to(carpeta)).encode())
        h.update(ruta.read_bytes())
    return h.hexdigest()[:16]


class Flujo:
    """Archivo de huellas y pasos de una plataforma."""

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        with open(self.ruta, encoding="utf-8") as f:
            self.datos = yaml.safe_load(f) or {}
        self.nombre = self.datos.get("plataforma", self.ruta.stem)
        self.verificada = bool(self.datos.get("verificada"))
        self.pantallas: dict = self.datos.get("pantallas") or {}
        self.validar()

    def seccion(self, nombre: str, obligatoria: bool = True):
        valor = self.datos.get(nombre)
        if valor is None and obligatoria:
            raise HuellaInvalida(f"{self.ruta.name}: falta la sección '{nombre}'")
        return valor

    def _validar_pasos(self, pasos, donde):
        for i, paso in enumerate(pasos or []):
            if not isinstance(paso, dict):
                raise HuellaInvalida(f"{self.ruta.name} {donde}[{i}]: un paso debe ser un diccionario")
            sobran = set(paso) - CLAVES_PASO
            if sobran:
                raise HuellaInvalida(f"{self.ruta.name} {donde}[{i}]: claves desconocidas {sorted(sobran)}")
            for clave in ("pantalla", "si_pantalla", "esperar_pantalla"):
                if clave in paso and paso[clave] not in self.pantallas:
                    raise HuellaInvalida(f"{self.ruta.name} {donde}[{i}]: pantalla '{paso[clave]}' sin huella")
            self._validar_acciones(paso.get("acciones"), f"{donde}[{i}]")

    def _validar_acciones(self, acciones, donde):
        for j, accion in enumerate(acciones or []):
            if not isinstance(accion, dict) or len(accion) != 1:
                raise HuellaInvalida(f"{self.ruta.name} {donde}.acciones[{j}]: cada acción es un diccionario de una clave")
            (nombre,) = accion
            if nombre not in ACCIONES:
                raise HuellaInvalida(f"{self.ruta.name} {donde}.acciones[{j}]: acción desconocida '{nombre}'")

    def validar(self):
        if self.verificada and "TODO" in self.ruta.read_text(encoding="utf-8"):
            raise HuellaInvalida(f"{self.ruta.name}: marcada como verificada pero aún contiene TODO")
        for nombre, huella in self.pantallas.items():
            if not isinstance(huella, dict) or not (huella.get("url") or huella.get("titulo") or huella.get("etiquetas")):
                raise HuellaInvalida(f"{self.ruta.name}: la pantalla '{nombre}' necesita url, titulo o etiquetas")
        for seccion in ("apertura", "rellenado", "deteccion"):
            self._validar_pasos(self.datos.get(seccion), seccion)
        self._validar_pasos((self.datos.get("firma") or {}).get("pasos"), "firma.pasos")
        destinatario = self.datos.get("destinatario") or {}
        for clave in ("abrir", "despues", "cerrar"):
            self._validar_acciones(destinatario.get(clave), f"destinatario.{clave}")
        for seccion in ("resumen", "firma", "justificante"):
            datos = self.datos.get(seccion) or {}
            if datos.get("pantalla") and datos["pantalla"] not in self.pantallas:
                raise HuellaInvalida(f"{self.ruta.name} {seccion}: pantalla '{datos['pantalla']}' sin huella")
            self._validar_acciones(datos.get("acciones"), seccion)
            self._validar_acciones(datos.get("cancelar"), f"{seccion}.cancelar")


# ---------------------------------------------------------------------------
# Navegador
# ---------------------------------------------------------------------------

class Navegador:
    """Chrome real con un perfil propio del bot (perfil_chrome/)."""

    def __init__(self, config: dict):
        from playwright.sync_api import sync_playwright

        nav = config["navegador"]
        perfil = Path(nav.get("perfil") or RAIZ / "perfil_chrome")
        perfil.mkdir(parents=True, exist_ok=True)
        headless = bool(nav.get("headless"))
        opciones = dict(
            user_data_dir=str(perfil),
            headless=headless,
            accept_downloads=True,
            handle_sigint=False,  # Ctrl+C lo gestiona el bot para terminar el ayuntamiento en curso
            # En Windows, con sandbox (evita el aviso de Chrome sobre --no-sandbox).
            chromium_sandbox=bool(nav.get("sandbox", sys.platform == "win32")),
            no_viewport=not headless,
        )
        if nav.get("canal"):
            opciones["channel"] = nav["canal"]
        self._pw = sync_playwright().start()
        self.contexto = self._pw.chromium.launch_persistent_context(**opciones)
        self.pagina = self.contexto.pages[0] if self.contexto.pages else self.contexto.new_page()

    def cerrar(self):
        try:
            self.contexto.close()
        finally:
            self._pw.stop()


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

class Motor:
    def __init__(self, navegador: Navegador, flujo: Flujo, config: dict, log):
        self.navegador = navegador
        self.flujo = flujo
        self.log = log
        self.contexto: dict = {}
        ejecucion = config["ejecucion"]
        self.timeout_pantalla = float(ejecucion.get("timeout_pantalla_seg", 20))
        self.timeout_accion = float(ejecucion.get("timeout_accion_seg", 15)) * 1000
        self.aceptar_dialogos = False
        self.dialogos: list[str] = []
        self._paginas_con_dialogo: set[int] = set()
        self._vigilar_dialogos(navegador.pagina)

    @property
    def pagina(self):
        return self.navegador.pagina

    def _vigilar_dialogos(self, pagina):
        if id(pagina) in self._paginas_con_dialogo:
            return
        self._paginas_con_dialogo.add(id(pagina))
        pagina.on("dialog", self._dialogo)

    def _dialogo(self, dialogo):
        self.dialogos.append(f"{dialogo.type}: {dialogo.message}")
        self.log.info(f"    diálogo del navegador ({dialogo.type}): {dialogo.message!r}")
        if dialogo.type == "beforeunload" or self.aceptar_dialogos:
            dialogo.accept()
        else:
            dialogo.dismiss()

    def _pausa(self, segundos: float) -> None:
        """Espera sin bloquear los eventos del navegador (time.sleep congelaría page.url)."""
        try:
            self.pagina.wait_for_timeout(segundos * 1000)
        except Exception:
            time.sleep(segundos)

    # -- huellas -------------------------------------------------------------
    def _texto(self) -> str:
        try:
            return self.pagina.inner_text("body", timeout=2000)
        except Exception:
            return ""

    def coincide(self, nombre: str) -> bool:
        huella = self.flujo.pantallas[nombre]
        if huella.get("url") and not re.search(huella["url"], self.pagina.url):
            return False
        if huella.get("titulo"):
            try:
                titulo = self.pagina.title()
            except Exception:
                return False
            if normalizar(huella["titulo"]) not in normalizar(titulo):
                return False
        etiquetas = huella.get("etiquetas") or []
        if etiquetas:
            texto = normalizar(self._texto())
            if not all(normalizar(e) in texto for e in etiquetas):
                return False
        return True

    def pantalla_actual(self) -> str | None:
        return next((n for n in self.flujo.pantallas if self.coincide(n)), None)

    def _esperar_coincidencia(self, nombre: str, segundos: float) -> bool:
        limite = time.monotonic() + segundos
        while True:
            try:
                if self.coincide(nombre):
                    return True
            except Exception:
                pass  # la página está navegando
            if time.monotonic() >= limite:
                return False
            self._pausa(0.5)

    def exigir(self, nombre: str, segundos: float | None = None) -> None:
        if not self._esperar_coincidencia(nombre, self.timeout_pantalla if segundos is None else segundos):
            actual = self.pantalla_actual()
            raise PantallaDesconocida(
                f"Se esperaba la pantalla '{nombre}' y la actual "
                + (f"coincide con '{actual}'" if actual else "no coincide con ninguna huella")
                + f" (URL {self.pagina.url})"
            )

    # -- pasos ---------------------------------------------------------------
    def ejecutar_pasos(self, pasos: list | None) -> None:
        for paso in pasos or []:
            if "si_pantalla" in paso:
                if not self._esperar_coincidencia(paso["si_pantalla"], min(5, self.timeout_pantalla)):
                    continue
            if "esperar_pantalla" in paso:
                if paso.get("mensaje"):
                    self.log.info(f"    >>> {paso['mensaje']}")
                if not self._esperar_coincidencia(paso["esperar_pantalla"], float(paso.get("timeout_seg", 300))):
                    raise PantallaDesconocida(
                        f"No se llegó a la pantalla '{paso['esperar_pantalla']}' en {paso.get('timeout_seg', 300)} s"
                    )
            elif "pantalla" in paso:
                self.exigir(paso["pantalla"])
                if paso.get("mensaje"):
                    self.log.info(f"    >>> {paso['mensaje']}")
            for accion in paso.get("acciones") or []:
                self.accion(accion)

    def ejecutar_acciones(self, acciones: list | None) -> None:
        for accion in acciones or []:
            self.accion(accion)

    def _valor(self, texto) -> str:
        return rellenar_plantilla(texto, self.contexto)

    def localizar(self, selector: str, base=None):
        """Localiza exactamente un elemento visible; si hay varios o ninguno, es un error."""
        from playwright.sync_api import Error as ErrorPlaywright

        loc = (base or self.pagina).locator(selector)
        try:
            loc.wait_for(state="visible", timeout=self.timeout_accion)
        except ErrorPlaywright as e:
            mensaje = str(e).splitlines()[0]
            if "strict mode violation" in mensaje:
                raise ErrorAyuntamiento(f"El selector {selector!r} encuentra varios elementos") from None
            raise ErrorAyuntamiento(f"No aparece el elemento {selector!r}: {mensaje}") from None
        return loc

    def accion(self, accion: dict) -> None:
        from playwright.sync_api import Error as ErrorPlaywright

        (nombre, arg), = accion.items()
        try:
            self._accion(nombre, arg)
        except (ErrorAyuntamiento, DetenerTanda):
            raise
        except ErrorPlaywright as e:
            raise ErrorAyuntamiento(f"Falló la acción {nombre} {arg!r}: {str(e).splitlines()[0]}") from None

    def _accion(self, nombre: str, arg) -> None:
        timeout = self.timeout_accion
        if nombre == "ir":
            self.pagina.goto(self._valor(arg), timeout=max(timeout, 30000))
        elif nombre == "clic":
            self.localizar(arg).click(timeout=timeout)
        elif nombre == "clic_nueva_pestana":
            with self.navegador.contexto.expect_page(timeout=max(timeout, 30000)) as nueva:
                self.localizar(arg).click(timeout=timeout)
            pagina = nueva.value
            pagina.wait_for_load_state()
            self.navegador.pagina = pagina
            self._vigilar_dialogos(pagina)
        elif nombre == "rellenar":
            valor = self._valor(arg["valor"])
            campo = self.localizar(arg["selector"])
            campo.fill(valor, timeout=timeout)
            leido = campo.input_value(timeout=timeout)
            if normalizar(leido) != normalizar(valor):
                raise ErrorAyuntamiento(f"El campo {arg['selector']!r} no conserva el texto escrito")
        elif nombre == "seleccionar":
            campo = self.localizar(arg["selector"])
            valor = self._valor(arg["valor"])
            try:
                campo.select_option(label=valor, timeout=timeout)
            except Exception:
                campo.select_option(value=valor, timeout=timeout)
        elif nombre == "marcar":
            self.localizar(arg).check(timeout=timeout)
        elif nombre == "adjuntar":
            adjuntos: dict = self.contexto["adjuntos"]
            clave = arg.get("archivo", "todos")
            if clave == "todos":
                archivos = [str(p) for p in adjuntos.values()]
            elif clave in adjuntos:
                archivos = [str(adjuntos[clave])]
            else:
                raise ErrorAyuntamiento(f"Adjunto desconocido {clave!r}")
            loc = self.pagina.locator(arg["selector"])
            if loc.count() != 1:
                raise ErrorAyuntamiento(f"El selector de adjuntos {arg['selector']!r} encuentra {loc.count()} elementos")
            loc.set_input_files(archivos, timeout=timeout)
        elif nombre == "pulsar":
            self.localizar(arg["selector"]).press(arg.get("tecla", "Enter"), timeout=timeout)
        elif nombre == "esperar":
            self._pausa(float(arg))
        elif nombre == "esperar_selector":
            self.localizar(arg)
        elif nombre == "elegir_destinatario":
            if arg:
                self.elegir_destinatario()
        else:  # validado al cargar la huella
            raise HuellaInvalida(f"Acción desconocida {nombre}")

    # -- destinatario --------------------------------------------------------
    def buscar_destinatario(self, codigo: str) -> list[dict]:
        """Busca un código DIR3 en el buscador de destinatarios y lee los resultados.

        Devuelve [{codigo, nombre, fila}] (fila es el localizador de esa fila).
        """
        cfg = self.flujo.seccion("destinatario")
        if cfg.get("pantalla"):
            self.exigir(cfg["pantalla"])
        self.ejecutar_acciones(cfg.get("abrir"))
        campo = self.localizar(cfg["campo_busqueda"])
        campo.fill(codigo)
        if cfg.get("boton_buscar"):
            self.localizar(cfg["boton_buscar"]).click()
        else:
            campo.press("Enter")
        filas = self.pagina.locator(cfg["filas_resultado"])
        limite = time.monotonic() + self.timeout_accion / 1000
        while filas.count() == 0 and time.monotonic() < limite:
            self._pausa(0.5)
        if cfg.get("espera_resultados_seg"):
            self._pausa(float(cfg["espera_resultados_seg"]))
        resultados = []
        for i in range(filas.count()):
            fila = filas.nth(i)
            texto = fila.inner_text()
            if cfg.get("codigo_en_fila"):
                texto_codigo = fila.locator(cfg["codigo_en_fila"]).first.inner_text()
            else:
                texto_codigo = texto
            codigos = PATRON_CODIGO_DIR3.findall(texto_codigo.upper())
            if not codigos:
                continue
            if cfg.get("nombre_en_fila"):
                nombre = fila.locator(cfg["nombre_en_fila"]).first.inner_text().strip()
            else:
                nombre = PATRON_CODIGO_DIR3.sub("", texto).strip(" -|\t\n")
            resultados.append({"codigo": codigos[0], "nombre": nombre, "fila": fila})
        return resultados

    def cerrar_busqueda(self) -> None:
        cfg = self.flujo.seccion("destinatario")
        self.ejecutar_acciones(cfg.get("cerrar"))

    def elegir_destinatario(self) -> tuple[str, str]:
        from comun import elegir_unidad

        cfg = self.flujo.seccion("destinatario")
        dir3_ayto = self.contexto["dir3_ayto"]
        validos = set(self.contexto.get("codigos_validos") or {dir3_ayto})
        resultados = self.buscar_destinatario(dir3_ayto)
        propios = [r for r in resultados if r["codigo"] in validos]
        if not propios:
            vistos = [r["codigo"] for r in resultados]
            raise ErrorAyuntamiento(f"El buscador de destinatarios no devuelve unidades de {dir3_ayto} (vistos: {vistos})")
        codigo, nombre = elegir_unidad(
            dir3_ayto, self.contexto.get("nombre_ayto", ""), [(r["codigo"], r["nombre"]) for r in propios]
        )
        elegidos = [r for r in propios if r["codigo"] == codigo]
        if not elegidos:
            raise ErrorAyuntamiento(f"El ayuntamiento {dir3_ayto} no aparece como destinatario seleccionable")
        fila = elegidos[0]["fila"]
        nombre = elegidos[0]["nombre"] or nombre
        if cfg.get("seleccionar_en_fila"):
            self.localizar(cfg["seleccionar_en_fila"], base=fila).click()
        else:
            fila.click()
        self.ejecutar_acciones(cfg.get("despues"))
        self.contexto["dir3_destino"] = codigo
        self.contexto["nombre_destino"] = nombre
        self.log.info(f"    destinatario elegido: {codigo} {nombre}")
        return codigo, nombre

    # -- resumen y justificante ----------------------------------------------
    def leer_campos(self, campos: dict) -> dict:
        leido = {}
        for nombre, selector in (campos or {}).items():
            leido[nombre] = self.localizar(selector).inner_text().strip()
        return leido

    def leer_resumen(self) -> dict:
        cfg = self.flujo.seccion("resumen")
        self.exigir(cfg["pantalla"])
        leido = self.leer_campos(cfg.get("campos"))
        if cfg.get("adjuntos"):
            leido["adjuntos"] = [t.strip() for t in self.pagina.locator(cfg["adjuntos"]).all_inner_texts() if t.strip()]
        leido["url"] = self.pagina.url
        return leido

    def capturar(self, etiqueta: str) -> list[Path]:
        CARPETA_CAPTURAS.mkdir(exist_ok=True)
        base = CARPETA_CAPTURAS / f"{marca_tiempo()}_{nombre_archivo_seguro(etiqueta)}"
        rutas = []
        try:
            self.pagina.screenshot(path=str(base.with_suffix(".png")), full_page=True)
            rutas.append(base.with_suffix(".png"))
        except Exception as e:
            self.log.warning(f"    no se pudo hacer la captura: {e}")
        try:
            base.with_suffix(".html").write_text(self.pagina.content(), encoding="utf-8")
            rutas.append(base.with_suffix(".html"))
        except Exception as e:
            self.log.warning(f"    no se pudo guardar el HTML: {e}")
        return rutas
