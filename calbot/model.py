"""Modelo de datos, normalización de nombres y lectura/escritura del CSV (la "base de datos")."""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Guatemala")  # UTC-6 todo el año, sin horario de verano
STATUSES = ("programado", "jugado", "aplazado", "cancelado")
KICKOFF_FMT = "%Y-%m-%d %H:%M"

# Nombre en la fuente (sin tildes, minúsculas) -> nombre para mostrar.
# Un equipo nuevo que no esté aquí se usa tal cual viene de la fuente.
TEAMS = {
    "municipal": "Municipal",
    "csd municipal": "Municipal",
    "comunicaciones": "Comunicaciones",
    "comunicaciones fc": "Comunicaciones",
    "antigua gfc": "Antigua GFC",
    "antigua": "Antigua GFC",
    "xelaju mc": "Xelajú MC",
    "xelaju": "Xelajú MC",
    "coban imperial": "Cobán Imperial",
    "suchitepequez": "Suchitepéquez",
    "deportivo suchitepequez": "Suchitepéquez",
    "guastatoya": "Guastatoya",
    "deportivo guastatoya": "Guastatoya",
    "malacateco": "Malacateco",
    "deportivo malacateco": "Malacateco",
    "mixco": "Mixco",
    "deportivo mixco": "Mixco",
    "marquense": "Marquense",
    "deportivo marquense": "Marquense",
    "aurora": "Aurora",
    "aurora fc": "Aurora",
    "san pedro": "San Pedro",
    "san pedro fc": "San Pedro",
}

FIELDS = [
    "match_id", "season", "jornada", "home", "away", "kickoff", "stadium", "status",
    "home_goals", "away_goals", "sequence", "updated_at", "note",
]


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(text)).strip("-")


def team_name(raw: str) -> str:
    return TEAMS.get(norm(raw), re.sub(r"\s+", " ", raw).strip())


def make_id(season: str, jornada: int, home: str, away: str) -> str:
    return f"{slugify(season)}-j{int(jornada):02d}-{slugify(home)}-vs-{slugify(away)}"


@dataclass
class Match:
    match_id: str
    season: str
    jornada: int
    home: str
    away: str
    kickoff: str                 # "YYYY-MM-DD HH:MM", hora de Guatemala
    stadium: str = ""
    status: str = "programado"   # programado | jugado | aplazado | cancelado
    home_goals: str = ""
    away_goals: str = ""
    sequence: int = 0            # sube cada vez que el partido cambia (los clientes lo usan para actualizar)
    updated_at: str = ""         # último cambio real, en UTC
    note: str = ""

    @property
    def uid(self) -> str:
        return f"{self.match_id}@ligagt-calendarios"

    def key(self) -> tuple:
        """Campos cuyo cambio cuenta como 'el partido cambió'."""
        return (self.kickoff, self.stadium, self.status, self.home_goals, self.away_goals)

    def kickoff_dt(self) -> datetime:
        return datetime.strptime(self.kickoff, KICKOFF_FMT).replace(tzinfo=TZ)


def load_matches(path: Path) -> dict[str, Match]:
    path = Path(path)
    if not path.exists():
        return {}
    out: dict[str, Match] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            kwargs = {k: (row.get(k) or "") for k in FIELDS}
            kwargs["jornada"] = int(kwargs["jornada"])
            kwargs["sequence"] = int(kwargs["sequence"] or 0)
            out[kwargs["match_id"]] = Match(**kwargs)
    return out


def save_matches(path: Path, matches: dict[str, Match]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(matches.values(), key=lambda m: (m.kickoff, m.jornada, m.home))
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for m in rows:
            w.writerow({k: getattr(m, k) for k in FIELDS})


def load_overrides(path: Path) -> dict[str, dict[str, str]]:
    """Lee data/overrides.csv. Columnas: match_id, kickoff, stadium, status, note.
    Una celda vacía significa "no cambiar ese campo". Las filas que empiezan con # se ignoran."""
    path = Path(path)
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            mid = (row.get("match_id") or "").strip()
            if not mid or mid.startswith("#"):
                continue
            ov = {k: (row.get(k) or "").strip() for k in ("kickoff", "stadium", "status", "note")}
            ov = {k: v for k, v in ov.items() if v}
            if "kickoff" in ov:
                try:
                    datetime.strptime(ov["kickoff"], KICKOFF_FMT)
                except ValueError:
                    raise ValueError(
                        f"overrides.csv línea {n}: kickoff '{ov['kickoff']}' debe ser AAAA-MM-DD HH:MM"
                    ) from None
            if "status" in ov and ov["status"] not in STATUSES:
                raise ValueError(
                    f"overrides.csv línea {n}: status '{ov['status']}' debe ser uno de {', '.join(STATUSES)}"
                )
            out[mid] = ov
    return out
