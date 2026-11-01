# Vigilante de licitaciones de paellas

Busca en los datos públicos de la **Plataforma de Contratación del Sector
Público** (PLACSP) los contratos de paellas, comidas populares y catering de
fiestas en la **Comunitat Valenciana** (Valencia, Alicante y Castellón). Lo de
fuera de la Comunitat se descarta.

**Es independiente del bot de registro:** tiene su propia carpeta, su propio
entorno y sus propias hojas. No lee ni escribe nada de `bot-registro/`, así que
puede funcionar mientras el bot está enviando.

- **No envía nada** ni presenta ofertas.
- **No usa certificado:** solo descarga datos abiertos.
- **No toca** `ayuntamientos.xlsx` ni la configuración del bot.

## Qué hace

| Comando | Qué saca | Hoja |
|---|---|---|
| `compradores` | Historial de contratos menores de paellas: qué ayuntamientos las contratan, en qué mes, por cuánto y a qué empresa | `historial_contratos_menores/` |
| `buscar` | Licitaciones abiertas, con plazo, que encajan | `datos/licitaciones.xlsx` |

### Historial (`compradores`): tres documentos

Es un análisis aparte de las licitaciones abiertas: mira los contratos de
paellas de los últimos años para saber qué ayuntamientos las contratan, cuándo
y por cuánto. Solo cuentan los que hablan de paellas. Salen tres documentos,
cada uno en su carpeta:

| Carpeta | Documento | Qué analiza |
|---|---|---|
| `historial_contratos_menores\` | `ANALISIS_CONTRATOS_MENORES.html` + `contratos_menores.xlsx` | Contratos menores (adjudicados directamente, sin licitación) |
| `historial_licitaciones\` | `ANALISIS_LICITACIONES.html` + `licitaciones_pasadas.xlsx` | Licitaciones pasadas (PLACSP y plataformas agregadas) |
| `historial_conjunto\` | `ANALISIS_CONJUNTO.html` + `conjunto.xlsx` | Las dos cosas juntas: **qué ayuntamientos piden más paellas**, ordenados por número de contratos, con cuántos fueron contratos menores y cuántos licitaciones |

Con `--fuentes menores` solo se hace el primero; con
`--fuentes licitaciones,agregadas`, solo el segundo. El conjunto sale cuando
se analizan las dos cosas. Al terminar se abre el último en el navegador.

Las licitaciones pasadas ocupan mucho (varios GB por año, de toda España).
Con `--borrar-descargas` cada archivo se borra en cuanto se ha leído.

El informe contiene:

1. **Resumen en cifras:** contratos, ayuntamientos, clientes recurrentes,
   importe típico, rango de importes.
2. **Calendario de envíos:** mes a mes, a qué ayuntamientos conviene enviar la
   propuesta (2 meses antes de cuando suelen contratar; `meses_antelacion`).
3. **Ayuntamientos:** prioridad (1 = ha contratado paellas en 2 o más años
   distintos; 2 = en los 2 últimos años; 3 = hace más tiempo), provincia,
   número de contratos, años, importe medio, mínimo y máximo, mes habitual,
   último contrato y empresa habitual.
4. **En qué meses se contratan**, con su importe medio.
5. **Por provincia.**
6. **Competencia:** empresas adjudicatarias, contratos e importes.
7. **Todos los contratos**, con enlace a la Plataforma.
8. **Limitaciones de los datos.**

La columna `dir3_ayto` es el mismo código que usa la hoja
del bot de registro; si quieres usar algo en el bot, cópialo tú.

### `licitaciones.xlsx`

Cada búsqueda añade las nuevas (en amarillo, `seguimiento = NUEVA`) y
actualiza las que ya estaban **sin borrar lo que escribes** en las columnas
`seguimiento` y `notas`. En `seguimiento` puedes poner:

| Valor | Uso |
|---|---|
| NUEVA | La pone el vigilante |
| ME INTERESA | Avisa cuando falten 3 días o menos para el plazo |
| PRESENTADA | Ya has presentado la oferta |
| DESCARTADA | No interesa (queda en gris al final) |

La oferta se presenta a mano en la PLACSP, siguiendo los pliegos de cada
licitación.

### Carpeta de cada licitación (`fichas/`)

Cada licitación que sirve (encaje Alto o Medio) tiene su carpeta en
`fichas/`, con la fecha del plazo delante para que salgan ordenadas:

```
fichas\2026-11-20 Sueca - Servicio de paellas gigantes Fiestas Mayores\
    00_RESUMEN.txt
    pliego_administrativo_PCAP.pdf
    pliego_tecnico_PPT.pdf
```

`00_RESUMEN.txt` contiene:

- **Valoración de 0 a 100** y de dónde sale cada punto: encaje, si habla de
  paellas, importe, días de plazo, tipo de procedimiento.
  70 o más: muy interesante; 50-69: interesante; 30-49: revisar.
- **Datos principales:** organismo, importe, plazo, procedimiento, forma de
  presentación, duración, lotes, enlace.
- **Criterios de adjudicación** con sus puntos, **garantías** y **solvencia
  exigida**, tal como los publica la plataforma.
- **Frases clave de los pliegos** (raciones, fechas, registro sanitario,
  solvencia…), sacadas automáticamente de los PDF.

En `licitaciones.xlsx` aparecen la valoración y un enlace a la carpeta, y la
hoja se ordena de mayor a menor valoración. La carpeta se actualiza si la
licitación cambia (por ejemplo, si se publica un pliego nuevo), y los pliegos
ya descargados no se vuelven a descargar.

Los márgenes de importe y qué encajes tienen carpeta se cambian en
`config.yaml` (`fichas:`).

### Solo paellas

Por defecto (`solo_paellas: true` en `config.yaml`) solo se quedan los contratos
que hablan de paellas en el título, el objeto o algún lote: paella, paelles,
paellada, concurso de paellas, paellera, arroz gigante… **Nada de catering,
comidas populares ni comidas genéricas.** Lo que ya estaba en la hoja de antes
y no es de paellas se retira en la siguiente búsqueda (salvo lo marcado
ME INTERESA o PRESENTADA), y su carpeta se mueve a `fichas\_no_paella`.

### Encaje (solo con `solo_paellas: false`)

- **Alto:** menciona paella, paellada, comida popular, dinar/sopar de germanor…
- **Medio:** una palabra de fiesta (fiestas, festes, fira, fallas, moros y
  cristianos…) junto a una de comida (comida, catering, dinar, arroz…), o
  fiestas con CPV de comidas.
- **Dudoso:** CPV de comidas o catering sin mención de fiestas.
- **Descartados:** comedores escolares, residencias, ayuda a domicilio,
  hospitales, etc., salvo que mencionen paellas.

Las listas de palabras están en `src/comun.py` y se pueden cambiar en `config.yaml`.

## Funcionamiento automático

`programar.bat` lo deja funcionando solo:

- Crea una tarea de Windows que se ejecuta **cada día a las 08:40**. Si el PC
  estaba apagado a esa hora, se ejecuta al encenderlo.
- **En temporada (febrero a septiembre) busca cada día**, que es cuando los
  ayuntamientos licitan las paellas de sus fiestas. **El resto del año busca una
  vez por semana**, para no perder nada. Los meses se cambian en `config.yaml`
  (`temporada:`).
- Crea en el escritorio el acceso directo **"Licitaciones de paellas"**, que
  abre `LISTA_LICITACIONES.html`: la lista de licitaciones de paellas abiertas,
  de mayor a menor valoración, con plazo, importe, enlace a la Plataforma y a
  su carpeta, más las presentadas y las vencidas de las últimas semanas. Se
  rehace en cada ejecución.
- Cuando aparece una nueva, o vence pronto una marcada ME INTERESA, sale un
  aviso de Windows.

Si cambias el seguimiento en `licitaciones.xlsx` y quieres verlo ya en la lista:
`python src/vigilante.py lista`.

## Instalación (Windows)

1. Descarga
   <https://github.com/alfredo2847/scriptpapa/archive/refs/heads/claude/confident-lamport-7e55jw.zip>,
   descomprímelo y copia la carpeta `vigilante-licitaciones` donde quieras (por
   ejemplo, al lado de `bot-registro`).
2. Doble clic en `instalar.bat`.
3. Doble clic en `programar.bat` (ver "Funcionamiento automático").

Para actualizar más adelante: `actualizar.bat`. Solo toca esta carpeta y nunca
sobrescribe `config.yaml`, `datos/` ni `logs/`.

## Uso

```bat
.venv\Scripts\activate
python src/vigilante.py compradores                     :: los tres documentos, últimos 3 años
python src/vigilante.py compradores --borrar-descargas  :: igual, borrando cada descarga tras leerla
python src/vigilante.py compradores --fuentes menores   :: solo contratos menores
python src/vigilante.py compradores --fuentes licitaciones,agregadas   :: solo licitaciones pasadas
python src/vigilante.py buscar                 :: licitaciones nuevas desde la última búsqueda
python src/vigilante.py buscar --dias 60       :: mirar 60 días atrás (y crear las carpetas que falten)
python src/vigilante.py buscar --sin-fichas    :: solo la hoja, sin carpetas ni pliegos
python src/vigilante.py lista                  :: rehacer LISTA_LICITACIONES.html sin buscar
```

Las descargas se guardan en `datos/descargas/` y no se repiten. Se pueden
borrar cuando ya tengas los informes de historial.

Si la PLACSP cambia las direcciones de descarga, se ponen en `config.yaml`
(`fuentes:`), o se descargan los ZIP a mano y se usan con
`python src/vigilante.py compradores --archivo <zip> <zip> ...`.

## De dónde salen los datos

Feeds de sindicación ATOM (formato CODICE) de la PLACSP, en
`contrataciondelsectorpublico.gob.es/sindicacion/`:

- `sindicacion_643`: licitaciones de los perfiles de contratante alojados en la PLACSP;
- `sindicacion_1044`: plataformas agregadas (Generalitat Valenciana y otras);
- `sindicacion_1143`: contratos menores.

Si una fuente falla (por ejemplo, porque la plataforma cambia una dirección),
el vigilante lo dice, sigue con las demás y guarda lo encontrado. La fuente
que falló se vuelve a mirar desde su última lectura correcta en la siguiente
búsqueda.

Los meses y años cerrados se publican en ZIP (`..._2025.zip`, `..._202601.zip`).
Un ayuntamiento que publique solo en su propia web y no en la PLACSP no aparecerá.

## Pruebas

```bat
python -m pytest
```
