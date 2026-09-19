# Calendarios de la Liga Nacional de Guatemala

Calendarios `.ics` de los 12 equipos (y de toda la liga) que **se actualizan solos** cuando la Liga reprograma un partido. Tú te suscribes una vez y tu app de calendario hace el resto.

Fuente de los datos: <https://ligagt.org/calendario/>

## Cómo funciona

```
ligagt.org/calendario ──► calbot (GitHub Actions, cada 6 h) ──► data/matches.csv   (base de datos)
                               ▲                                └► docs/calendars/*.ics  ──► GitHub Pages ──► tu calendario
                    data/overrides.csv (correcciones manuales)
```

1. Cada 6 horas un workflow descarga el calendario de la Liga.
2. Compara con `data/matches.csv`. Si un partido cambió (hora, estadio, resultado), sube su `SEQUENCE` para que los clientes de calendario lo actualicen en vez de duplicarlo.
3. Aplica tus correcciones de `data/overrides.csv` (ver abajo).
4. Regenera `docs/calendars/*.ics` y hace commit **solo si algo cambió**.
5. GitHub Pages sirve `docs/` en una URL pública a la que te suscribes.

## Puesta en marcha (5 minutos)

1. Crea un repositorio **público** en GitHub y sube esta carpeta (Pages gratis requiere repo público).
2. **Settings → Actions → General → Workflow permissions:** elige *Read and write permissions* y guarda.
3. **Settings → Pages:** *Source* = `Deploy from a branch`, rama `main`, carpeta `/docs`.
4. **Actions → Actualizar calendarios → Run workflow** para la primera ejecución.
5. Abre `https://TU-USUARIO.github.io/NOMBRE-DEL-REPO/`: ahí están los botones de suscripción para cada equipo (Google Calendar, Apple/Outlook, copiar URL).

> Si ya importaste los archivos `.ics` sueltos que te di antes, bórralos del calendario antes de suscribirte: usan otros identificadores y aparecerían duplicados.

## Cuando la Liga reprograma un partido

Normalmente no haces nada: el workflow lo detecta en la siguiente ejecución.

Si la página de la Liga tarda en actualizarse (pasó con Antigua vs Municipal: el partido seguía en la fecha vieja días después del anuncio), corrígelo tú en `data/overrides.csv` **desde la web de GitHub** (lápiz de editar → commit). El workflow se dispara solo y regenera los calendarios.

```csv
match_id,kickoff,stadium,status,note
apertura-2026-j10-antigua-gfc-vs-municipal,2026-10-08 19:00,"Estadio Pensativo, Antigua Guatemala",,Reprogramado por la fecha FIFA
```

- `match_id`: cópialo de la primera columna de `data/matches.csv`.
- `kickoff`: `AAAA-MM-DD HH:MM`, hora de Guatemala.
- Una celda vacía significa "no cambiar ese campo".
- `status`: `programado`, `aplazado` (fecha por confirmar; se marca como tentativo), `cancelado` o `jugado`.
- Las correcciones **ganan** sobre la fuente. Cuando el log del workflow diga *"la fuente ya refleja el override"*, puedes borrar esa fila.
- `data/matches.csv` lo administra el bot: si lo editas a mano y la descarga funciona, la fuente lo sobrescribe. Para cambios manuales usa siempre `overrides.csv`.

## Límites que conviene conocer

- **Velocidad de refresco:** Google Calendar decide cuándo relee una suscripción (suele tardar entre 12 y 24 horas y no se puede forzar). Apple y Outlook respetan mejor el intervalo de 6 horas.
- **Bloqueos:** ligagt.org está detrás de Cloudflare y podría bloquear las IP de GitHub Actions, o la Liga puede cambiar el HTML. Si pasa, el workflow **falla en rojo y te llega un correo**, pero los calendarios se siguen publicando con los últimos datos y puedes mantenerlos con `overrides.csv`. Nunca borra datos por una descarga rota.
- **Pausa por inactividad:** GitHub desactiva los workflows programados tras 60 días sin actividad en el repo (por ejemplo, entre temporadas). Se reactivan con un clic en la pestaña *Actions*.
- **Zona horaria:** se asume que las horas de la página son de Guatemala (UTC-6, sin horario de verano) y cada partido dura 2 horas en el calendario.
- **Equipos nuevos:** si asciende un equipo, aparece con el nombre que use la Liga. Para darle tildes o un nombre corto, agrégalo al diccionario `TEAMS` de `calbot/model.py`.

## Estructura

```
calbot/            código (scrape, merge, ics, site)
data/matches.csv   base de datos: un partido por fila
data/overrides.csv correcciones manuales
docs/              lo que publica GitHub Pages (index.html + calendars/*.ics)
tests/             pruebas (unittest, sin dependencias extra)
.github/workflows/ actualizar.yml (cada 6 h) · pruebas.yml (al cambiar código)
```

## Uso local

```bash
pip install -r requirements.txt
python -m calbot update                      # descarga, fusiona y regenera
python -m calbot update --no-scrape          # solo regenera desde data/
python -m calbot update --html pagina.html   # usa un HTML guardado
python -m unittest discover -s tests -v      # pruebas
```

Códigos de salida: `0` bien · `1` override o datos inválidos (no escribe nada) · `2` falló la descarga (regenera igual con lo guardado).
