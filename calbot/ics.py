"""Generación de archivos iCalendar (.ics) a partir de los partidos."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .model import Match, norm

DURATION = timedelta(hours=2)
REFRESH = "PT6H"  # sugerencia de refresco para clientes que la respetan (Apple, Outlook, Thunderbird)


def esc(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\n").replace("\n", "\\n")
    )


def fold(line: str) -> str:
    """Corta líneas a 75 bytes (UTF-8) como exige el estándar; las continuaciones empiezan con un espacio."""
    out: list[str] = []
    cur, size = "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > 75:
            out.append(cur)
            cur, size = " " + ch, 1 + n
        else:
            cur += ch
            size += n
    out.append(cur)
    return "\r\n".join(out)


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _stamp(iso_text: str) -> str:
    return iso_text.replace("-", "").replace(":", "") if iso_text else "19700101T000000Z"


def is_clasico(m: Match) -> bool:
    return {norm(m.home), norm(m.away)} == {"municipal", "comunicaciones"}


def summary(m: Match) -> str:
    core = (
        f"{m.home} {m.home_goals}-{m.away_goals} {m.away}"
        if m.status == "jugado" and m.home_goals != "" and m.away_goals != ""
        else f"{m.home} vs {m.away}"
    )
    prefix = {"aplazado": "APLAZADO: ", "cancelado": "CANCELADO: "}.get(m.status, "")
    return f"{prefix}{'Clásico: ' if is_clasico(m) else ''}{core} (J{m.jornada})"


def description(m: Match) -> str:
    start = m.kickoff_dt()
    parts = [f"{m.season} · Jornada {m.jornada}", f"Hora de Guatemala: {start:%d/%m/%Y %H:%M}"]
    if m.status == "aplazado":
        parts.append("Partido aplazado: la fecha y hora pueden cambiar.")
    if m.note:
        parts.append(m.note)
    return "\n".join(parts)


def vevent(m: Match, alarm: bool) -> list[str]:
    start = m.kickoff_dt()
    stamp = _stamp(m.updated_at)
    status = {"cancelado": "CANCELLED", "aplazado": "TENTATIVE"}.get(m.status, "CONFIRMED")
    lines = [
        "BEGIN:VEVENT",
        f"UID:{m.uid}",
        f"DTSTAMP:{stamp}",
        f"LAST-MODIFIED:{stamp}",
        f"SEQUENCE:{m.sequence}",
        f"DTSTART:{_utc(start)}",
        f"DTEND:{_utc(start + DURATION)}",
        f"SUMMARY:{esc(summary(m))}",
        f"DESCRIPTION:{esc(description(m))}",
        f"STATUS:{status}",
        "TRANSP:OPAQUE",
    ]
    if m.stadium:
        lines.append(f"LOCATION:{esc(m.stadium)}")
    if alarm and m.status in ("programado", "aplazado"):
        lines += [
            "BEGIN:VALARM",
            "TRIGGER:-PT1H",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{esc(summary(m))} en 1 hora",
            "END:VALARM",
        ]
    lines.append("END:VEVENT")
    return lines


def build_calendar(matches: list[Match], name: str, desc: str, alarm: bool = True) -> str:
    """Devuelve el texto completo del .ics. Es determinista: la misma entrada da el mismo archivo."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ligagt-calendarios//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(name)}",
        f"X-WR-CALDESC:{esc(desc)}",
        "X-WR-TIMEZONE:America/Guatemala",
        f"REFRESH-INTERVAL;VALUE=DURATION:{REFRESH}",
        f"X-PUBLISHED-TTL:{REFRESH}",
    ]
    for m in sorted(matches, key=lambda x: (x.kickoff, x.jornada, x.home)):
        lines += vevent(m, alarm)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"
