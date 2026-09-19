"""Descarga y lectura de https://ligagt.org/calendario/ (la fuente de los datos)."""
from __future__ import annotations

import re
import time

import requests
from bs4 import BeautifulSoup

from .model import Match, make_id, team_name

URL = "https://ligagt.org/calendario/"
USER_AGENT = "Mozilla/5.0 (compatible; ligagt-calendarios/1.0)"

# La primera celda mezcla la fecha ISO con la fecha en texto: "2026-07-24 18:00:05julio 24, 2026".
DATETIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*(\d{2}:\d{2})")
# Un marcador es "3 - 1"; una hora como "20:00:008:00 pm" no debe confundirse con uno.
SCORE_RE = re.compile(r"(?<![\d:])(\d{1,2})\s*-\s*(\d{1,2})(?![\d:])")
JORNADA_RE = re.compile(r"Jornada\s+(\d+)", re.IGNORECASE)
VS_RE = re.compile(r"\s+vs\.?\s+", re.IGNORECASE)

DEFAULT_COLUMNS = {"fecha": 0, "encuentro": 1, "hora/resultados": 2, "temporada": 3, "estadio": 4, "día de partido": 5}


class ScrapeError(RuntimeError):
    pass


def fetch(url: str = URL, retries: int = 3, timeout: int = 30) -> str:
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "es"}, timeout=timeout)
            r.raise_for_status()
            return r.text
        except requests.RequestException as exc:
            last = exc
            time.sleep(2 * attempt)
    raise ScrapeError(f"No se pudo descargar {url}: {last}")


def parse(html: str) -> dict[str, Match]:
    soup = BeautifulSoup(html, "html.parser")
    matches: dict[str, Match] = {}
    for table in soup.find_all("table"):
        first = table.find("tr")
        if first is None:
            continue
        headers = [c.get_text(" ", strip=True).lower() for c in first.find_all(["th", "td"])]
        col = {name: (headers.index(name) if name in headers else default) for name, default in DEFAULT_COLUMNS.items()}
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) <= max(col.values()):
                continue
            text = [c.get_text(" ", strip=True) for c in cells]
            dt = DATETIME_RE.search(text[col["fecha"]])
            jor = JORNADA_RE.search(text[col["día de partido"]])
            teams = VS_RE.split(text[col["encuentro"]], maxsplit=1)
            if not (dt and jor and len(teams) == 2):
                continue
            home, away = team_name(teams[0]), team_name(teams[1])
            season = text[col["temporada"]].strip() or "Torneo"
            stadium = text[col["estadio"]].strip()
            if stadium.upper() in ("N/D", "-", "—"):
                stadium = ""
            score = SCORE_RE.search(text[col["hora/resultados"]])
            match = Match(
                match_id=make_id(season, int(jor.group(1)), home, away),
                season=season,
                jornada=int(jor.group(1)),
                home=home,
                away=away,
                kickoff=f"{dt.group(1)} {dt.group(2)}",
                stadium=stadium,
                status="jugado" if score else "programado",
                home_goals=score.group(1) if score else "",
                away_goals=score.group(2) if score else "",
            )
            matches[match.match_id] = match
    return matches


def check_plausible(scraped: dict[str, Match], previous: dict[str, Match]) -> None:
    """Falla en voz alta en lugar de dejar que una descarga rota borre los datos buenos."""
    if not scraped:
        raise ScrapeError(
            "La página no devolvió ningún partido. Puede ser un bloqueo (Cloudflare) o que cambió el HTML de la Liga."
        )
    seasons = {m.season for m in scraped.values()}
    known = [m for m in previous.values() if m.season in seasons]
    if len(known) >= 20 and len(scraped) < 0.5 * len(known):
        raise ScrapeError(f"Solo se leyeron {len(scraped)} partidos y ya había {len(known)}; se descarta la descarga.")
