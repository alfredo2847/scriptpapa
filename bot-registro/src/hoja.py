"""Hoja de control (datos/ayuntamientos.xlsx).

La clave única es dir3_ayto. Ninguna operación borra filas ni el estado de
envíos ya hechos.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from comun import RAIZ, marca_tiempo

PENDIENTE = "PENDIENTE"
PRUEBA_OK = "PRUEBA_OK"
ENVIADO = "ENVIADO"
ERROR = "ERROR"
MANUAL = "MANUAL"
REVISAR = "REVISAR"
ESTADOS = (PENDIENTE, PRUEBA_OK, ENVIADO, ERROR, MANUAL, REVISAR)

# Estados en los que nunca se vuelve a enviar.
ESTADOS_BLOQUEADOS = (ENVIADO, REVISAR)

VIA_REC = "REC"
VIA_MANUAL = "MANUAL"

COLUMNAS = [
    "dir3_ayto",
    "municipio",
    "poblacion",
    "prioridad",
    "via",
    "dir3_destino",
    "nombre_destino",
    "url_sede",
    "estado",
    "num_registro",
    "fecha_envio",
    "justificante",
    "notas",
    "email_contacto",
    # columnas auxiliares
    "web_dir3",
    "nif_ayto",
    "plataforma_sede",
    "fecha_deteccion",
]

COLUMNAS_UNIDADES = ["dir3_ayto", "codigo", "nombre", "codigo_superior"]

RUTA_HOJA = RAIZ / "datos" / "ayuntamientos.xlsx"

COLORES_ESTADO = {
    ENVIADO: "C6EFCE",
    PRUEBA_OK: "DDEBF7",
    ERROR: "FFC7CE",
    REVISAR: "FFEB9C",
    MANUAL: "EDEDED",
}


class HojaBloqueada(Exception):
    pass


class HojaControl:
    def __init__(self, ruta: Path = RUTA_HOJA):
        self.ruta = Path(ruta)
        self.filas: dict[str, dict] = {}
        self.unidades: dict[str, list[dict]] = {}
        self.columnas_extra: list[str] = []
        if self.ruta.exists():
            self._leer()

    # -- lectura -----------------------------------------------------------
    def _leer(self) -> None:
        libro = load_workbook(self.ruta)
        hoja = libro["control"] if "control" in libro.sheetnames else libro.worksheets[0]
        filas = list(hoja.iter_rows(values_only=True))
        if not filas:
            return
        cabecera = [str(c).strip() if c is not None else "" for c in filas[0]]
        self.columnas_extra = [c for c in cabecera if c and c not in COLUMNAS]
        for valores in filas[1:]:
            fila = {c: ("" if v is None else v) for c, v in zip(cabecera, valores) if c}
            codigo = str(fila.get("dir3_ayto", "")).strip()
            if not codigo:
                continue
            for c in COLUMNAS:
                fila.setdefault(c, "")
            fila["dir3_ayto"] = codigo
            if not fila["estado"]:
                fila["estado"] = PENDIENTE
            self.filas[codigo] = fila
        if "unidades" in libro.sheetnames:
            hoja_u = libro["unidades"]
            filas_u = list(hoja_u.iter_rows(values_only=True))
            if filas_u:
                cab = [str(c) for c in filas_u[0]]
                for valores in filas_u[1:]:
                    u = {c: ("" if v is None else str(v)) for c, v in zip(cab, valores)}
                    if u.get("dir3_ayto"):
                        self.unidades.setdefault(u["dir3_ayto"], []).append(u)

    # -- acceso ------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.filas)

    def __iter__(self):
        return iter(self.filas.values())

    def get(self, dir3: str) -> dict | None:
        return self.filas.get(dir3)

    def nueva_fila(self, dir3: str) -> dict:
        fila = {c: "" for c in COLUMNAS + self.columnas_extra}
        fila["dir3_ayto"] = dir3
        fila["estado"] = PENDIENTE
        self.filas[dir3] = fila
        return fila

    def actualizar(self, dir3: str, **campos) -> dict:
        fila = self.filas[dir3]
        fila.update(campos)
        return fila

    def anotar(self, dir3: str, nota: str) -> None:
        fila = self.filas[dir3]
        fila["notas"] = nota

    def unidades_de(self, dir3: str) -> list[tuple[str, str]]:
        return [(u["codigo"], u["nombre"]) for u in self.unidades.get(dir3, [])]

    def ordenadas(self) -> list[dict]:
        """Por prioridad (1 primero) y, dentro de cada prioridad, por población descendente."""
        def clave(f):
            try:
                prioridad = int(f.get("prioridad") or 9)
            except (TypeError, ValueError):
                prioridad = 9
            try:
                poblacion = int(f.get("poblacion") or 0)
            except (TypeError, ValueError):
                poblacion = 0
            return (prioridad, -poblacion, str(f.get("municipio", "")))
        return sorted(self.filas.values(), key=clave)

    # -- escritura ---------------------------------------------------------
    def copia_seguridad(self) -> Path | None:
        """Copia ayuntamientos.xlsx con fecha y hora antes de cada ejecución."""
        if not self.ruta.exists():
            return None
        carpeta = self.ruta.parent / "copias"
        carpeta.mkdir(exist_ok=True)
        destino = carpeta / f"{self.ruta.stem}_{marca_tiempo()}{self.ruta.suffix}"
        shutil.copy2(self.ruta, destino)
        return destino

    def guardar(self, intentos: int = 30) -> None:
        libro = Workbook()
        hoja = libro.active
        hoja.title = "control"
        columnas = COLUMNAS + [c for c in self.columnas_extra if c not in COLUMNAS]
        hoja.append(columnas)
        for fila in self.filas.values():
            hoja.append([fila.get(c, "") for c in columnas])
        negrita = Font(bold=True)
        for celda in hoja[1]:
            celda.font = negrita
        indice_estado = columnas.index("estado") + 1
        for fila_celdas in hoja.iter_rows(min_row=2):
            color = COLORES_ESTADO.get(str(fila_celdas[indice_estado - 1].value))
            if color:
                fila_celdas[indice_estado - 1].fill = PatternFill("solid", fgColor=color)
        anchos = {"municipio": 28, "nombre_destino": 40, "url_sede": 40, "notas": 60, "justificante": 40}
        for i, c in enumerate(columnas, start=1):
            hoja.column_dimensions[get_column_letter(i)].width = anchos.get(c, 14)
        hoja.freeze_panes = "C2"
        hoja.auto_filter.ref = hoja.dimensions

        hoja_u = libro.create_sheet("unidades")
        hoja_u.append(COLUMNAS_UNIDADES)
        for lista in self.unidades.values():
            for u in lista:
                hoja_u.append([u.get(c, "") for c in COLUMNAS_UNIDADES])
        for celda in hoja_u[1]:
            celda.font = negrita

        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.ruta.with_name(f"~tmp_{self.ruta.name}")
        libro.save(temporal)
        # En Windows, si la hoja está abierta en Excel no se puede sustituir.
        for intento in range(intentos):
            try:
                os.replace(temporal, self.ruta)
                return
            except PermissionError:
                if intento == 0:
                    print(f"\n*** No se puede guardar {self.ruta.name}: ¿está abierto en Excel? "
                          "Ciérralo; se reintenta cada 10 s. ***")
                time.sleep(10)
        raise HojaBloqueada(f"No se pudo guardar {self.ruta}. Los cambios están en {temporal}")
