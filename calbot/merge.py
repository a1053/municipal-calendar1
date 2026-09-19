"""Combina lo ya guardado, lo descargado de la fuente y las correcciones manuales."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from .model import Match

OVERRIDABLE = ("kickoff", "stadium", "status")


def iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def merge(
    previous: dict[str, Match],
    scraped: dict[str, Match] | None,
    overrides: dict[str, dict[str, str]],
    now: datetime,
) -> tuple[dict[str, Match], list[str]]:
    """Devuelve (estado nuevo, mensajes de log).

    - `scraped` es None si no se descargó nada (falló o se pidió --no-scrape): se conserva lo guardado.
    - La fuente manda sobre lo guardado, y `overrides` manda sobre la fuente.
    - `sequence` y `updated_at` solo cambian cuando el partido cambia de verdad; así el archivo .ics
      no varía entre ejecuciones sin novedades y los clientes de calendario detectan las actualizaciones.
    """
    log: list[str] = []
    base = {mid: replace(m) for mid, m in previous.items()}

    if scraped is not None:
        seasons = {m.season for m in scraped.values()}
        for mid, raw in scraped.items():
            base[mid] = replace(raw)
        for mid, old in previous.items():
            if mid not in scraped and old.season in seasons:
                log.append(f"AVISO: {mid} ya no aparece en la fuente; se conserva el último dato conocido.")

    for mid, ov in overrides.items():
        m = base.get(mid)
        if m is None:
            log.append(f"AVISO: override '{mid}' no coincide con ningún partido (revisa el match_id en data/matches.csv).")
            continue
        raw = scraped.get(mid) if scraped else None
        if raw is not None and all(getattr(raw, f) == v for f, v in ov.items() if f in OVERRIDABLE):
            log.append(f"INFO: la fuente ya refleja el override de {mid}; puedes borrarlo de data/overrides.csv.")
        for f in OVERRIDABLE:
            if f in ov:
                setattr(m, f, ov[f])
        if "note" in ov:
            m.note = ov["note"]

    stamp = iso(now)
    for mid, m in base.items():
        prev = previous.get(mid)
        if prev is None:
            m.sequence, m.updated_at = 0, stamp
        elif prev.key() != m.key():
            m.sequence, m.updated_at = prev.sequence + 1, stamp
            changed = [
                f"{name}: {a or '-'} -> {b or '-'}"
                for name, a, b in zip(("hora", "estadio", "estado", "goles local", "goles visita"), prev.key(), m.key())
                if a != b
            ]
            log.append(f"CAMBIO: {mid} ({'; '.join(changed)})")
        else:
            m.sequence, m.updated_at = prev.sequence, prev.updated_at
    return base, log
