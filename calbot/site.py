"""Escribe docs/: un .ics por equipo, uno con toda la liga y la página índice para GitHub Pages."""
from __future__ import annotations

import html
from pathlib import Path

from .ics import build_calendar
from .model import Match, slugify

LEAGUE_SLUG = "liga-completa"


def calendars_for(matches: dict[str, Match]) -> list[dict]:
    """Un calendario por equipo (con recordatorios) y uno de toda la liga (sin recordatorios)."""
    by_team: dict[str, list[Match]] = {}
    for m in matches.values():
        for team in (m.home, m.away):
            by_team.setdefault(team, []).append(m)

    seasons = sorted({m.season for m in matches.values()})
    season_txt = " / ".join(seasons) if seasons else "Liga Nacional"
    out = []
    for team in sorted(by_team, key=lambda t: slugify(t)):
        out.append(
            {
                "slug": slugify(team),
                "title": team,
                "name": f"{team} · Liga Nacional de Guatemala",
                "desc": f"Partidos de {team} en {season_txt}. Hora de Guatemala.",
                "matches": by_team[team],
                "alarm": True,
            }
        )
    out.append(
        {
            "slug": LEAGUE_SLUG,
            "title": "Toda la liga",
            "name": "Liga Nacional de Guatemala",
            "desc": f"Todos los partidos de {season_txt}. Hora de Guatemala.",
            "matches": list(matches.values()),
            "alarm": False,
        }
    )
    return out


def write_site(matches: dict[str, Match], out_dir: Path) -> list[dict]:
    out_dir = Path(out_dir)
    cal_dir = out_dir / "calendars"
    cal_dir.mkdir(parents=True, exist_ok=True)
    cals = calendars_for(matches)

    wanted = {f"{c['slug']}.ics" for c in cals}
    for old in cal_dir.glob("*.ics"):
        if old.name not in wanted:
            old.unlink()
    for c in cals:
        text = build_calendar(c["matches"], c["name"], c["desc"], alarm=c["alarm"])
        (cal_dir / f"{c['slug']}.ics").write_bytes(text.encode("utf-8"))

    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    last = max((m.updated_at for m in matches.values()), default="")
    (out_dir / "index.html").write_text(render_index(cals, last), encoding="utf-8")
    return cals


def render_index(cals: list[dict], last_change: str) -> str:
    items = []
    for c in cals:
        n = len(c["matches"])
        items.append(
            f'<li data-file="{html.escape(c["slug"])}.ics">'
            f'<div class="t"><strong>{html.escape(c["title"])}</strong><span>{n} partidos</span></div>'
            f'<div class="b"><a class="btn sub" href="#">Apple / Outlook</a>'
            f'<a class="btn goog" href="#" target="_blank" rel="noopener">Google Calendar</a>'
            f'<button class="btn copy" type="button">Copiar URL</button>'
            f'<a class="btn dl" href="#" download>.ics</a></div></li>'
        )
    stamp = html.escape(last_change or "sin datos")
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calendarios · Liga Nacional de Guatemala</title>
<style>
:root {{ --bg:#fff; --fg:#1a1a1a; --mut:#666; --card:#f5f5f5; --acc:#c8102e; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141414; --fg:#eee; --mut:#999; --card:#1f1f1f; --acc:#ff5a5f; }} }}
body {{ font-family: system-ui, sans-serif; background:var(--bg); color:var(--fg); max-width:640px; margin:0 auto; padding:1.25rem; line-height:1.4; }}
h1 {{ font-size:1.4rem; margin:.2rem 0; }} p {{ color:var(--mut); margin:.3rem 0 1rem; }}
ul {{ list-style:none; padding:0; margin:0; display:grid; gap:.6rem; }}
li {{ background:var(--card); border-radius:10px; padding:.7rem .8rem; }}
.t {{ display:flex; justify-content:space-between; gap:.5rem; }} .t span {{ color:var(--mut); font-size:.85rem; }}
.b {{ display:flex; flex-wrap:wrap; gap:.4rem; margin-top:.5rem; }}
.btn {{ font:inherit; font-size:.85rem; padding:.3rem .6rem; border-radius:6px; border:1px solid var(--acc); color:var(--acc); background:none; text-decoration:none; cursor:pointer; }}
.ok {{ background:var(--acc); color:#fff; }}
small {{ color:var(--mut); }}
</style>
</head>
<body>
<h1>Calendarios · Liga Nacional de Guatemala</h1>
<p>Suscríbete y tu calendario se actualiza solo cuando la Liga reprograma un partido. Horas de Guatemala.</p>
<ul>
{chr(10).join(items)}
</ul>
<p><small>Último cambio en algún partido: {stamp}. Los datos vienen de ligagt.org/calendario.</small></p>
<script>
const base = new URL('calendars/', location.href);
document.querySelectorAll('li[data-file]').forEach(li => {{
  const url = new URL(li.dataset.file, base).href;
  const webcal = url.replace(/^https?:/, 'webcal:');
  li.querySelector('.sub').href = webcal;
  li.querySelector('.goog').href = 'https://calendar.google.com/calendar/r?cid=' + encodeURIComponent(webcal);
  li.querySelector('.dl').href = url;
  const copy = li.querySelector('.copy');
  copy.addEventListener('click', async () => {{
    try {{ await navigator.clipboard.writeText(url); copy.textContent = 'Copiada'; copy.classList.add('ok'); }}
    catch (e) {{ prompt('Copia esta URL:', url); }}
    setTimeout(() => {{ copy.textContent = 'Copiar URL'; copy.classList.remove('ok'); }}, 1800);
  }});
}});
</script>
</body>
</html>
"""
