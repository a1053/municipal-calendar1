"""Ejecutar con:  python -m unittest discover -s tests -v"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from calbot.__main__ import main
from calbot.ics import build_calendar, fold
from calbot.merge import merge
from calbot.model import load_matches, load_overrides, make_id, slugify, team_name
from calbot.scrape import ScrapeError, check_plausible, parse

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "calendario.html"
NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
J10 = "apertura-2026-j10-antigua-gfc-vs-municipal"


def fixture_matches():
    return parse(FIXTURE.read_text(encoding="utf-8"))


class ParseTests(unittest.TestCase):
    def test_lee_los_132_partidos_de_la_fuente(self):
        self.assertEqual(len(fixture_matches()), 132)

    def test_partido_jugado_tiene_marcador_y_estado(self):
        m = fixture_matches()["apertura-2026-j01-municipal-vs-mixco"]
        self.assertEqual((m.status, m.home_goals, m.away_goals), ("jugado", "2", "0"))
        self.assertEqual(m.kickoff, "2026-07-24 20:00")

    def test_partido_pendiente_no_confunde_la_hora_con_un_marcador(self):
        m = fixture_matches()["apertura-2026-j11-municipal-vs-suchitepequez"]
        self.assertEqual((m.status, m.home_goals), ("programado", ""))
        self.assertEqual(m.stadium, "")  # "N/D" en la fuente

    def test_nombres_normalizados_con_tildes(self):
        self.assertEqual(team_name("Xelaju MC"), "Xelajú MC")
        self.assertEqual(team_name("  coban   imperial "), "Cobán Imperial")
        self.assertEqual(team_name("Equipo Nuevo"), "Equipo Nuevo")
        self.assertEqual(slugify("Suchitepéquez"), "suchitepequez")

    def test_id_estable(self):
        self.assertEqual(make_id("Apertura 2026", 10, "Antigua GFC", "Municipal"), J10)

    def test_html_vacio_o_bloqueado_falla_en_voz_alta(self):
        with self.assertRaises(ScrapeError):
            check_plausible(parse("<html><body>Just a moment...</body></html>"), {})

    def test_descarga_parcial_se_descarta(self):
        previous = fixture_matches()
        partial = dict(list(previous.items())[:10])
        with self.assertRaises(ScrapeError):
            check_plausible(partial, previous)


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.raw = fixture_matches()
        self.override = {J10: {"kickoff": "2026-10-08 19:00", "stadium": "Estadio Pensativo", "note": "Fecha FIFA"}}

    def test_override_gana_sobre_la_fuente(self):
        state, _ = merge({}, self.raw, self.override, NOW)
        self.assertEqual(state[J10].kickoff, "2026-10-08 19:00")
        self.assertEqual(state[J10].stadium, "Estadio Pensativo")
        self.assertEqual(state[J10].note, "Fecha FIFA")

    def test_sin_novedades_no_cambia_nada(self):
        first, _ = merge({}, self.raw, self.override, NOW)
        second, log = merge(first, self.raw, self.override, LATER)
        self.assertEqual(first, second)
        self.assertFalse([l for l in log if l.startswith("CAMBIO")])

    def test_reprogramacion_sube_sequence_y_updated_at(self):
        first, _ = merge({}, self.raw, self.override, NOW)
        moved = {mid: replace(m) for mid, m in self.raw.items()}
        moved["apertura-2026-j11-municipal-vs-suchitepequez"].kickoff = "2026-09-25 19:00"
        second, log = merge(first, moved, self.override, LATER)
        m = second["apertura-2026-j11-municipal-vs-suchitepequez"]
        self.assertEqual(m.sequence, 1)
        self.assertEqual(m.updated_at, "2026-09-25T12:00:00Z")
        self.assertTrue(any(l.startswith("CAMBIO") for l in log))
        # el resto no se tocó
        self.assertEqual(second[J10].sequence, 0)

    def test_resultado_nuevo_cuenta_como_cambio(self):
        first, _ = merge({}, self.raw, {}, NOW)
        played = {mid: replace(m) for mid, m in self.raw.items()}
        p = played["apertura-2026-j11-municipal-vs-suchitepequez"]
        p.status, p.home_goals, p.away_goals = "jugado", "3", "1"
        second, _ = merge(first, played, {}, LATER)
        self.assertEqual(second[p.match_id].sequence, 1)

    def test_si_la_descarga_falla_se_conserva_lo_guardado(self):
        first, _ = merge({}, self.raw, self.override, NOW)
        second, _ = merge(first, None, self.override, LATER)
        self.assertEqual(first, second)

    def test_avisa_cuando_la_fuente_ya_refleja_el_override(self):
        caught_up = {mid: replace(m) for mid, m in self.raw.items()}
        caught_up[J10].kickoff, caught_up[J10].stadium = "2026-10-08 19:00", "Estadio Pensativo"
        _, log = merge({}, caught_up, self.override, NOW)
        self.assertTrue(any("ya refleja" in l for l in log))

    def test_override_con_id_inexistente_avisa(self):
        _, log = merge({}, self.raw, {"no-existe": {"kickoff": "2026-10-08 19:00"}}, NOW)
        self.assertTrue(any("no coincide" in l for l in log))

    def test_partido_cancelado_por_override(self):
        state, _ = merge({}, self.raw, {J10: {"status": "cancelado"}}, NOW)
        text = build_calendar([state[J10]], "x", "y")
        self.assertIn("STATUS:CANCELLED", text)
        self.assertIn("SUMMARY:CANCELADO: ", text)
        self.assertNotIn("BEGIN:VALARM", text)


class IcsTests(unittest.TestCase):
    def setUp(self):
        state, _ = merge({}, fixture_matches(), {J10: {"kickoff": "2026-10-08 19:00"}}, NOW)
        self.state = state
        self.muni = [m for m in state.values() if "Municipal" in (m.home, m.away)]
        self.text = build_calendar(self.muni, "Municipal", "Prueba")

    def test_municipal_tiene_22_partidos(self):
        self.assertEqual(len(self.muni), 22)
        self.assertEqual(self.text.count("BEGIN:VEVENT"), 22)

    def test_hora_de_guatemala_se_convierte_a_utc(self):
        self.assertIn("DTSTART:20261009T010000Z", self.text)  # 8 oct 19:00 GT = 9 oct 01:00 UTC

    def test_formato_valido(self):
        self.assertTrue(self.text.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(self.text.endswith("END:VCALENDAR\r\n"))
        for line in self.text.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75, line)
        self.assertEqual(self.text.count("BEGIN:VALARM"), self.text.count("END:VALARM"))

    def test_jugados_sin_recordatorio_y_con_marcador(self):
        self.assertIn("Clásico: Comunicaciones 0-1 Municipal (J6)", self.text)
        self.assertEqual(self.text.count("BEGIN:VALARM"), 13)  # solo los 13 pendientes

    def test_es_determinista(self):
        self.assertEqual(self.text, build_calendar(self.muni, "Municipal", "Prueba"))

    def test_fold_no_parte_caracteres_multibyte(self):
        line = "SUMMARY:" + "é" * 60
        folded = fold(line).split("\r\n")
        self.assertEqual("".join([folded[0]] + [p[1:] for p in folded[1:]]), line)
        self.assertTrue(all(len(p.encode("utf-8")) <= 75 for p in folded))


class OverridesTests(unittest.TestCase):
    def test_valida_formato(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "o.csv"
            p.write_text("match_id,kickoff,stadium,status,note\nx,8/10/2026 7pm,,,\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_overrides(p)
            p.write_text("match_id,kickoff,stadium,status,note\nx,,,pospuesto,\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_overrides(p)


class CliTests(unittest.TestCase):
    def make_root(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "data").mkdir()
        (tmp / "data" / "overrides.csv").write_text(
            "match_id,kickoff,stadium,status,note\n"
            f"{J10},2026-10-08 19:00,Estadio Pensativo,,Fecha FIFA\n",
            encoding="utf-8",
        )
        return tmp

    def test_dos_ejecuciones_seguidas_no_cambian_los_archivos(self):
        root = self.make_root()
        args = ["update", "--root", str(root), "--html", str(FIXTURE)]
        self.assertEqual(main(args), 0)
        snap = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        self.assertEqual(main(args), 0)
        again = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        self.assertEqual(snap, again)

    def test_si_falla_la_descarga_devuelve_2_pero_regenera_calendarios(self):
        root = self.make_root()
        self.assertEqual(main(["update", "--root", str(root), "--html", str(FIXTURE)]), 0)
        shutil.rmtree(root / "docs")
        blocked = root / "blocked.html"
        blocked.write_text("<html>Just a moment...</html>", encoding="utf-8")
        self.assertEqual(main(["update", "--root", str(root), "--html", str(blocked)]), 2)
        self.assertTrue((root / "docs" / "calendars" / "municipal.ics").exists())
        self.assertEqual(len(load_matches(root / "data" / "matches.csv")), 132)  # datos intactos

    def test_override_invalido_no_escribe_nada(self):
        root = self.make_root()
        (root / "data" / "overrides.csv").write_text("match_id,kickoff,stadium,status,note\nx,mal,,,\n", encoding="utf-8")
        self.assertEqual(main(["update", "--root", str(root), "--html", str(FIXTURE)]), 1)
        self.assertFalse((root / "docs").exists())


if __name__ == "__main__":
    unittest.main()
