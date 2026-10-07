"""Trennung von Framework und Spielstand, lokales Spielstand-Git, Migration."""

import json
import subprocess

import pytest

import datenverzeichnis as dv
import gemeinsam as g
import migriere
import pfade
import pruefe


def _log(ordner):
    return subprocess.run(["git", "log", "--format=%s"], cwd=ordner, capture_output=True, text=True).stdout.splitlines()


def test_ohne_datenverzeichnis_klare_meldung(framework, monkeypatch):
    monkeypatch.delenv("STOCKMASTER_DATA_DIR", raising=False)
    with pytest.raises(pfade.Fehler, match="STOCKMASTER_DATA_DIR ist nicht gesetzt"):
        g.pfad("portfolios")


def test_datenverzeichnis_darf_nicht_das_framework_sein(framework, monkeypatch):
    monkeypatch.setenv("STOCKMASTER_DATA_DIR", str(framework))
    with pytest.raises(pfade.Fehler, match="zeigt auf das Framework"):
        g.pfad("portfolios")


def test_konfiguration_aus_framework_spielstand_aus_daten(projekt, framework):
    assert g.pfad("trades", "x.csv") == projekt / "trades" / "x.csv"
    assert g.framework_pfad("config", "profile.json") == framework / "config" / "profile.json"
    assert g.projekt()["startkapital"] == "1000.00"
    assert not (projekt / "config").exists()


def test_einrichten_aus_vorlage(tmp_path, framework):
    ziel = tmp_path / "neu"
    assert "aus der Vorlage angelegt" in dv.einrichten(ziel)[0]
    for name in ("portfolios", "trades", "journal", "reviews", "strategie", "news", "data/kurse", "lessons.md",
                 ".gitignore", "README.md"):
        assert (ziel / name).exists(), name
    assert _log(ziel) == [_log(ziel)[0]] and _log(ziel)[0].startswith("aufbau: Datenverzeichnis aus Vorlage")
    assert subprocess.run(["git", "remote"], cwd=ziel, capture_output=True, text=True).stdout == ""
    # zweiter Aufruf ist harmlos
    assert "bereits eingerichtet" in dv.einrichten(ziel)[0]
    assert len(_log(ziel)) == 1


def test_einrichten_verweigert_fremden_inhalt(tmp_path, framework):
    ziel = tmp_path / "fremd"
    ziel.mkdir()
    (ziel / "irgendwas.txt").write_text("x")
    with pytest.raises(pfade.Fehler, match="nicht leer"):
        dv.einrichten(ziel)


def test_einrichten_entfernt_remote(tmp_path, framework):
    ziel = tmp_path / "d"
    dv.einrichten(ziel)
    subprocess.run(["git", "remote", "add", "origin", "https://example.invalid/x.git"], cwd=ziel, check=True)
    dv.einrichten(ziel)
    assert subprocess.run(["git", "remote"], cwd=ziel, capture_output=True, text=True).stdout == ""


def test_frisches_datenverzeichnis_besteht_pruefung(tmp_path, framework, monkeypatch, uhr):
    ziel = tmp_path / "d"
    dv.einrichten(ziel)
    monkeypatch.setenv("STOCKMASTER_DATA_DIR", str(ziel))
    befunde = pruefe.alle_pruefungen(historie=True)
    assert [b for b in befunde if b.stufe == "FEHLER"] == []
    assert not any("Kein Git-Repository" in b.text for b in befunde)


def test_commit_nur_mit_praefix_und_lokal(tmp_path, framework, monkeypatch):
    ziel = tmp_path / "d"
    dv.einrichten(ziel)
    monkeypatch.setenv("STOCKMASTER_DATA_DIR", str(ziel))
    (ziel / "journal" / "2026-10-12_auftraggeber-a.md").write_text("# Journal\n")
    with pytest.raises(pfade.Fehler, match="Präfix"):
        dv.commit("ohne präfix")
    assert dv.commit("session: Test")
    assert dv.commit("session: nichts") == ""
    assert _log(ziel)[0] == "session: Test"
    status = dv.status()
    assert status["git"] and status["commits"] == 2 and status["offene_aenderungen"] == 0 and status["remotes"] == []


def test_pruefe_warnt_bei_remote(tmp_path, framework, monkeypatch, uhr):
    ziel = tmp_path / "d"
    dv.einrichten(ziel)
    subprocess.run(["git", "remote", "add", "origin", "https://example.invalid/x.git"], cwd=ziel, check=True)
    monkeypatch.setenv("STOCKMASTER_DATA_DIR", str(ziel))
    assert any(b.pruefung == "Spielstand-Git" for b in pruefe.alle_pruefungen())


def test_cache_und_sperre_nicht_versioniert(tmp_path, framework, monkeypatch):
    ziel = tmp_path / "d"
    dv.einrichten(ziel)
    monkeypatch.setenv("STOCKMASTER_DATA_DIR", str(ziel))
    with g.schreibsperre():
        with g.schreibsperre():  # verschachtelt ohne Verklemmung
            g.json_schreiben(pfade.cache_pfad("markt.json"), {"x": 1})
    assert dv.commit("daten: Test") == ""


def _alte_arbeitskopie(tmp_path):
    alt = tmp_path / "alt"
    for ordner in ("portfolios", "trades", "journal", "data/kurse", "strategie", "tools", "config"):
        (alt / ordner).mkdir(parents=True)
    (alt / "portfolios" / "defensiv.json").write_text(json.dumps({"profil": "defensiv", "startdatum": "2026-10-12"}))
    (alt / "journal" / "2026-10-12_auftraggeber-a.md").write_text("# Journal\n")
    (alt / "lessons.md").write_text("# Erkenntnisregister\n")
    (alt / "STATUS.md").write_text("# Projektstatus\n\n- Startdatum des Spiels: 2026-10-12 (gesetzt)\n")
    (alt / "tools" / "x.py").write_text("print('framework')\n")
    for befehl in (["git", "init", "-q", "-b", "main"], ["git", "-c", "user.name=T", "-c", "user.email=t@example.org",
                                                         "commit", "-q", "--allow-empty", "-m", "alt"]):
        subprocess.run(befehl, cwd=alt, check=True)
    return alt


def test_migration_mit_herkunftsvermerk(tmp_path, framework, monkeypatch):
    alt = _alte_arbeitskopie(tmp_path)
    ziel = tmp_path / "daten"
    monkeypatch.setenv("STOCKMASTER_DATA_DIR", str(ziel))
    assert migriere.main(["--von", str(alt)]) == 0
    assert (ziel / "portfolios" / "defensiv.json").exists()
    assert (ziel / "journal" / "2026-10-12_auftraggeber-a.md").exists()
    assert (ziel / "lessons.md").read_text() == "# Erkenntnisregister\n"
    assert not (ziel / "tools").exists() and not (ziel / "config").exists()
    assert json.loads((ziel / "spiel.json").read_text())["startdatum"] == "2026-10-12"
    nachricht = subprocess.run(["git", "log", "-1", "--format=%B"], cwd=ziel, capture_output=True, text=True).stdout
    assert nachricht.startswith("aufbau: Spielstand aus alter Arbeitskopie übernommen")
    assert "Herkunft: Verzeichnis 'alt', Commit " in nachricht
    # zweite Migration in denselben Spielstand wird abgelehnt
    assert migriere.main(["--von", str(alt)]) == 1
