"""Umbau v2, Punkt 4: Migration bestehender Instanzen (viertes Portfolio) auf einer Kopie eines Datenverzeichnisses."""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import bewertung
import gemeinsam as g
import init
import pruefe
from helfer import git_commit, git_init, sperre

WURZEL = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def altbestand(tmp_path_factory):
    """Datenverzeichnis wie vor dem Umbau: drei Portfolios mit Historie, ohne Overnight."""
    ziel = tmp_path_factory.mktemp("alt") / "daten"
    subprocess.run([sys.executable, str(WURZEL / "webui" / "demo" / "demo_daten.py"), "--ziel", str(ziel), "--tage", "40",
                    "--ende", "2026-09-30"], check=True, capture_output=True, cwd=WURZEL)
    for pfad in ("portfolios/overnight.json", "trades/overnight.csv", "data/nav/overnight.csv", "strategie/overnight.md"):
        (ziel / pfad).unlink()
    benchmark = ziel / "data" / "benchmark.csv"
    zeilen = [z.split(",") for z in benchmark.read_text().splitlines()]
    spalte = zeilen[0].index("overnight")
    benchmark.write_text("\n".join(",".join(v for i, v in enumerate(z) if i != spalte) for z in zeilen) + "\n")
    lessons = ziel / "lessons.md"
    if lessons.exists():
        lessons.write_text(lessons.read_text().split("## H-OVERNIGHT-1")[0])
    shutil.rmtree(ziel / ".git")  # Verlauf des Altbestands: ein Commit ohne Overnight
    git_init(ziel)
    return ziel


def pruefsummen(wurzel: Path) -> dict:
    return {str(p.relative_to(wurzel)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(wurzel.rglob("*")) if p.is_file() and ".git" not in p.parts}


@pytest.fixture
def kopie(altbestand, tmp_path, monkeypatch, framework):
    ziel = tmp_path / "daten"
    shutil.copytree(altbestand, ziel)
    monkeypatch.setenv("STOCKMASTER_DATA_DIR", str(ziel))
    return ziel


def test_migration_ergaenzt_overnight_ohne_die_historie_anzufassen(kopie, uhr):
    uhr.stellen("2026-10-12T07:00")
    assert g.vorhandene_profile() == ["defensiv", "ausgewogen", "aggressiv"]
    vorher = pruefsummen(kopie)
    meldungen = init.profile_ergaenzen()
    assert any("Portfolio overnight: 1000.00 EUR ab 2026-10-12" in m for m in meldungen)
    nachher = pruefsummen(kopie)
    neu = {pfad for pfad in nachher if pfad not in vorher}
    assert neu == {"portfolios/overnight.json", "trades/overnight.csv", "data/nav/overnight.csv", "strategie/overnight.md"}
    geaendert = {pfad for pfad in nachher if pfad in vorher and nachher[pfad] != vorher[pfad]}
    assert geaendert <= {"spiel.json", "lessons.md", "data/benchmark.csv"}, geaendert
    p = g.portfolio_laden("overnight")
    assert p["cash"] == "1000.00" and p["startdatum"] == "2026-10-12" and p["verarbeitet_bis"] == "2026-10-11"
    assert g.spiel_lesen()["profile_ergaenzt"][0]["profil"] == "overnight"
    assert "H-OVERNIGHT-1" in (kopie / "lessons.md").read_text()
    assert "Standard-Richtlinie" in (kopie / "strategie" / "overnight.md").read_text()
    # bestehende Portfolios, Trades und Journal sind Byte für Byte unverändert
    for pfad in vorher:
        if pfad.startswith(("portfolios/", "trades/", "journal/", "reviews/", "data/nav/")):
            assert nachher[pfad] == vorher[pfad], pfad


def test_migration_ist_idempotent(kopie, uhr):
    uhr.stellen("2026-10-12T07:00")
    assert init.profile_ergaenzen()
    zwischen = pruefsummen(kopie)
    assert init.profile_ergaenzen() == []
    assert pruefsummen(kopie) == zwischen


def test_migration_wartet_auf_laufende_session_und_kennt_kein_backdating(kopie, uhr):
    uhr.stellen("2026-10-12T07:00")
    sperre(kopie, start="2026-10-12T06:30:00+02:00")
    with pytest.raises(g.Fehler, match="Session"):
        init.profile_ergaenzen()
    assert not g.portfolio_pfad("overnight").exists()
    (kopie / "session.lock").unlink()
    init.profile_ergaenzen()
    assert g.portfolio_laden("overnight")["startdatum"] == g.heute().isoformat()  # heute, nie früher


def test_nach_der_migration_prueft_und_berichtet_alles_mit_unterschiedlichen_startdaten(kopie, uhr, quelle):
    uhr.stellen("2026-10-12T07:00")
    init.profile_ergaenzen()
    git_commit(kopie, "session: Migration viertes Portfolio")
    sperre(kopie, start="2026-10-12T06:55:00+02:00")
    assert bewertung.main(["bericht"]) == 0
    ranking = (kopie / "ranking.md").read_text()
    assert "Overnight" in ranking and "| Startdatum |" in ranking and "unterschiedliche Startdaten" in ranking
    benchmark = g.csv_lesen(kopie / "data" / "benchmark.csv")
    assert "overnight" in benchmark[0] and all(z["overnight"] == "" for z in benchmark)  # noch kein eigener Kurstag
    fehler = [b for b in pruefe.alle_pruefungen(historie=True) if b.stufe == "FEHLER"]
    assert fehler == [], fehler
