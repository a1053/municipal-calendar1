"""Uso: python -m calbot update [--no-scrape] [--html archivo.html] [--root .]

Códigos de salida: 0 todo bien · 1 datos u overrides inválidos (no se escribe nada)
                   2 falló la descarga (los calendarios se regeneran igual con los datos guardados)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .merge import merge
from .model import load_matches, load_overrides, save_matches
from .scrape import ScrapeError, check_plausible, fetch, parse
from .site import write_site


def update(root: Path, scrape: bool, html_file: str | None) -> int:
    data = root / "data"
    previous = load_matches(data / "matches.csv")
    try:
        overrides = load_overrides(data / "overrides.csv")
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    scraped = None
    scrape_failed = False
    if scrape:
        try:
            text = Path(html_file).read_text(encoding="utf-8") if html_file else fetch()
            scraped = parse(text)
            check_plausible(scraped, previous)
            print(f"Fuente leída: {len(scraped)} partidos.")
        except (ScrapeError, OSError) as exc:
            scraped, scrape_failed = None, True
            print(f"ERROR de descarga: {exc}\nSe regeneran los calendarios con los últimos datos guardados.")

    merged, log = merge(previous, scraped, overrides, datetime.now(timezone.utc))
    for line in log:
        print(line)

    save_matches(data / "matches.csv", merged)
    cals = write_site(merged, root / "docs")
    print(f"Listo: {len(merged)} partidos, {len(cals)} calendarios.")
    return 2 if scrape_failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="calbot")
    sub = parser.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("update", help="descargar, fusionar con overrides y regenerar los .ics")
    up.add_argument("--no-scrape", action="store_true", help="no descargar; regenerar solo desde data/")
    up.add_argument("--html", help="leer este archivo HTML en lugar de descargar la página")
    up.add_argument("--root", default=".", help="carpeta raíz del repositorio")
    args = parser.parse_args(argv)
    return update(Path(args.root), scrape=not args.no_scrape, html_file=args.html)


if __name__ == "__main__":
    sys.exit(main())
