# Bot de envío por registro a ayuntamientos

Presenta por registro de entrada la misma carta y el mismo dossier a los 266
ayuntamientos de la provincia de Valencia, dirigidos al Alcalde/sa y al
Concejal/a de Fiestas, y deja constancia de cada envío en una hoja de control.

**Principio rector:** cada envío es un acto oficial firmado y no se puede
deshacer. Ante la duda, el script no envía.

- **No firma:** cada firma la confirma una persona con Autofirma o el PIN del certificado.
- **No toca el certificado:** usa el que ya está instalado en Windows, a través de Chrome.
- **No improvisa:** si una pantalla no coincide con su huella, se para y avisa.

## Instalación (Windows)

Requisitos: Python 3.12 o superior, Google Chrome, Autofirma y el certificado instalado en Windows.

```bat
instalar.bat
```

o a mano:

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

No hace falta `playwright install`: el bot usa el Chrome instalado (`navegador.canal: chrome`).

Antes de la primera tanda:

1. Copia `carta.pdf` y `dossier.pdf` definitivos en `documentos/`.
2. Completa `config.yaml`. El bot no envía mientras queden campos `[ENTRE CORCHETES]`.

## Uso

```bat
python src/main.py inventario                 :: fase 1: genera datos/ayuntamientos.xlsx
python src/main.py detectar                   :: fase 2: vía de cada ayuntamiento (no envía nada)
python src/main.py grabar                     :: envío manual de referencia: capturas y borrador de huellas
python src/main.py validar-huellas            :: comprueba huellas/
python src/main.py enviar --prueba --max 5    :: todo menos firmar; marca PRUEBA_OK
python src/main.py enviar --max 5 --confirmar :: primera tanda real
python src/main.py informe                    :: resumen y datos/manuales.xlsx
python src/main.py marcar L01462508 --estado ENVIADO --num REGAGE...   :: anotar un envío manual o un REVISAR
```

### Fase 1: inventario

Necesita el listado de unidades DIR3 de entidades locales, que es público. Se
descarga en la sede del Ministerio (administracionelectronica.gob.es, DIR3,
Descargas) o en datos.gob.es. Hay dos formas de usarlo:

- pon la URL en `config.yaml` (`inventario.url_dir3`) y ejecuta `inventario`, o
- descárgalo a mano y ejecuta `python src/main.py inventario --archivo <ruta>` (xlsx, csv o zip).

El original se guarda sin tocar en `datos/dir3_bruto/`. Se filtran los códigos
`L0146xxxx` vigentes y se excluyen mancomunidades, entidades locales menores y
organismos. Si no salen 266, se para sin tocar la hoja y muestra la lista. Con
`--poblacion pobmunXX.xlsx` (INE) se rellena la población, se calcula la
prioridad y se listan los municipios que faltan o sobran.

Si el DIR3 cambia los nombres de columna, se indican en `inventario.columnas`.

Las unidades hijas de cada ayuntamiento van a la pestaña `unidades` de la hoja.
Como destinatario se sugiere la de Fiestas, Festejos o Festes; si no hay, la de
Cultura; y si tampoco, el propio ayuntamiento.

### Fase 2: detección de la vía

Orden de preferencia: **REC**, después **sede con plataforma conocida** y por
último **MANUAL**. Al terminar muestra cuántos ayuntamientos van por cada vía y
qué plataformas llegan a 10 o más (las únicas a las que les compensa un
adaptador). Repítelo antes de cada tanda: solo procesa los que no se han enviado.

La comprobación en el REC necesita `huellas/rec.yaml` verificado. Mientras no lo
esté, solo se buscan sedes. Las huellas de plataformas están en `huellas/plataformas.yaml`.

### Fase 3: envío por el REC

1. **Envío manual de referencia:** `python src/main.py grabar` abre Chrome con el
   perfil del bot. Haces un envío real a mano y, en cada pantalla, pulsas Enter en
   la consola. Se guardan la captura, el HTML y un borrador de huella en
   `huellas/borrador_<fecha>.yaml`.
2. Con esas capturas se completan los `TODO` de `huellas/rec.yaml` y se pone
   `verificada: true`. El bot se niega a usar una huella verificada que aún tenga `TODO`.
3. `enviar --prueba --max 5`: hace todo menos firmar y verifica el resumen.
   Es obligatorio antes de la primera tanda real y después de cualquier cambio en `huellas/`.
4. `enviar --max 5 --confirmar`: primera tanda real. Revisa los justificantes.
5. Tandas de 20 o 30 por orden de prioridad.

Antes de firmar, el bot comprueba en el resumen que:

- el código del destinatario es `dir3_destino` y pertenece al ayuntamiento;
- el nombre del destinatario y el asunto contienen el nombre del municipio;
- hay exactamente dos adjuntos con los nombres esperados.

Si falla cualquiera de estas comprobaciones, guarda una captura, marca el
ayuntamiento como ERROR y pasa al siguiente sin firmar.

### Fase 4: sedes electrónicas

Hay un adaptador por plataforma, no por municipio. Para crear uno, copia
`huellas/sedes/_plantilla.yaml` como `huellas/sedes/<plataforma>.yaml` y
complétalo con un envío manual hecho con `grabar --url <sede>`. Solo puede
llevar al trámite "Instancia general" o "Solicitud genérica". Antes de firmar,
el bot comprueba el dominio de la sede y que el nombre del municipio aparece en
la cabecera y en el resumen. `informe` genera `datos/manuales.xlsx` con los
ayuntamientos restantes y los textos listos para copiar.

## Estados de la hoja de control

| Estado     | Significado |
|------------|-------------|
| PENDIENTE  | Aún no se ha hecho nada |
| PRUEBA_OK  | Ha pasado el modo prueba (no se ha firmado) |
| ENVIADO    | Registrado, con número y justificante. Nunca se repite |
| ERROR      | Algo no cuadró **antes** de firmar. Se reintenta solo con `--reintentar-errores` |
| REVISAR    | Se pulsó firmar pero no se confirmó el justificante. **Comprobar a mano**; nunca se reintenta |
| MANUAL     | Se presenta a mano |

## Salvaguardas

- **Huellas de pantalla:** antes de actuar se comparan la URL, el título y las
  etiquetas de cada pantalla. Si no coinciden, se para la tanda, se guardan la
  captura y el HTML en `capturas/` y avisa con sonido y una notificación.
- **Parada inmediata:** crea un archivo `STOP` en la carpeta del proyecto o pulsa
  Ctrl+C. La tanda se detiene al terminar el ayuntamiento en curso; un segundo
  Ctrl+C corta en el acto.
- **Errores seguidos:** con 3 errores seguidos (`max_errores_seguidos`) se para la tanda.
- **Copia de la hoja:** antes de cada ejecución se guarda en `datos/copias/`.
- **Registro:** cada paso queda en `logs/` con la hora, el municipio y el resultado.
- **Credenciales:** el bot no guarda ni pide contraseñas ni el PIN. La elección del
  certificado y la firma pasan por las ventanas de Windows y de Autofirma.
- **Hoja abierta en Excel:** si `ayuntamientos.xlsx` está abierto, el bot espera
  a que lo cierres antes de guardar.

**Cuando cambia un formulario,** el script no se repara solo. Se para y deja la
captura y el HTML. Con ellos se actualiza la huella y el selector, y se vuelve a
pasar el modo prueba.

## Pruebas

```bat
python -m pytest
```

Incluyen un REC simulado (`tests/mock_rec/`) con el que se recorre el flujo
entero: inventario, detección, prueba, envío, error de verificación, REVISAR
tras una firma sin justificante, STOP y cambio de huellas.
