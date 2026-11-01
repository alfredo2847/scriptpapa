# Vigilante de licitaciones de paellas

Busca en los datos públicos de la **Plataforma de Contratación del Sector
Público** (PLACSP) los contratos de paellas, comidas populares y catering de
fiestas en la provincia de Valencia (configurable).

**Es independiente del bot de registro:** tiene su propia carpeta, su propio
entorno y sus propias hojas. No lee ni escribe nada de `bot-registro/`, así que
puede funcionar mientras el bot está enviando.

- **No envía nada** ni presenta ofertas.
- **No usa certificado:** solo descarga datos abiertos.
- **No toca** `ayuntamientos.xlsx` ni la configuración del bot.

## Qué hace

| Comando | Qué saca | Hoja |
|---|---|---|
| `compradores` | Histórico de contratos (sobre todo contratos menores): qué ayuntamientos contratan paellas, en qué mes, por cuánto y a qué empresa | `datos/compradores.xlsx` |
| `buscar` | Licitaciones abiertas, con plazo, que encajan | `datos/licitaciones.xlsx` |

### `compradores.xlsx`

- **municipios:** uno por fila, con `prioridad_sugerida` (1 = ya ha contratado
  paellas o comidas populares; 2 = catering de fiestas; 3 = dudoso), los
  `meses_en_que_contrata`, en qué mes conviene `enviar_propuesta_en` (2 meses
  antes, configurable) y el `dir3_ayto`, que es el mismo código que la hoja del
  bot de registro. Si quieres usar la prioridad en el bot, cópiala tú a mano.
- **contratos:** cada contrato encontrado con su enlace.
- **competencia:** empresas que se llevan esos contratos.

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

### Encaje

- **Alto:** menciona paella, paellada, comida popular, dinar/sopar de germanor…
- **Medio:** una palabra de fiesta (fiestas, festes, fira, fallas, moros y
  cristianos…) junto a una de comida (comida, catering, dinar, arroz…), o
  fiestas con CPV de comidas.
- **Dudoso:** CPV de comidas o catering sin mención de fiestas.
- **Descartados:** comedores escolares, residencias, ayuda a domicilio,
  hospitales, etc., salvo que mencionen paellas.

Las listas de palabras están en `src/comun.py` y se pueden cambiar en `config.yaml`.

## Instalación (Windows)

1. Descarga
   <https://github.com/alfredo2847/scriptpapa/archive/refs/heads/claude/confident-lamport-7e55jw.zip>,
   descomprímelo y copia la carpeta `vigilante-licitaciones` donde quieras (por
   ejemplo, al lado de `bot-registro`).
2. Doble clic en `instalar.bat`.
3. Doble clic en `programar.bat` para que `buscar` se ejecute solo cada día a
   las 08:40 (con la sesión de Windows iniciada).

Para actualizar más adelante: `actualizar.bat`. Solo toca esta carpeta y nunca
sobrescribe `config.yaml`, `datos/` ni `logs/`.

## Uso

```bat
.venv\Scripts\activate
python src/vigilante.py compradores            :: últimos 3 años (la primera vez tarda: descarga varios GB)
python src/vigilante.py compradores --anos 1 --fuentes menores   :: prueba rápida
python src/vigilante.py buscar                 :: licitaciones nuevas desde la última búsqueda
python src/vigilante.py buscar --dias 60       :: mirar 60 días atrás
```

Las descargas se guardan en `datos/descargas/` y no se repiten. Se pueden
borrar cuando ya tengas `compradores.xlsx`.

Si la PLACSP cambia las direcciones de descarga, se ponen en `config.yaml`
(`fuentes:`), o se descargan los ZIP a mano y se usan con
`python src/vigilante.py compradores --archivo <zip> <zip> ...`.

## De dónde salen los datos

Feeds de sindicación ATOM (formato CODICE) de la PLACSP, en
`contrataciondelsectorpublico.gob.es/sindicacion/`:

- `sindicacion_643`: licitaciones de los perfiles de contratante alojados en la PLACSP;
- `sindicacion_1143`: plataformas agregadas (Generalitat Valenciana y otras);
- `sindicacion_1044`: contratos menores.

Los meses y años cerrados se publican en ZIP (`..._2025.zip`, `..._202601.zip`).
Un ayuntamiento que publique solo en su propia web y no en la PLACSP no aparecerá.

## Pruebas

```bat
python -m pytest
```
