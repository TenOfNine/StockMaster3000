"""Sicherung und Wiederherstellung: lokales Git enthalten, Secrets nur ausdrücklich und verschlüsselt."""

import io
import json
import subprocess
import tarfile

import pytest
from conftest import ADMIN_PW

TOKEN = "sk-ant-oat01-" + "C" * 40 + "9876"


@pytest.fixture
def kopie(app, demo_repo, tmp_path, monkeypatch):
    """Eigene Kopie des Demo-Datenverzeichnisses (die Wiederherstellung ersetzt es)."""
    import shutil

    from stockmaster import config
    from stockmaster.spiel import lesen

    ziel = tmp_path / "daten"
    shutil.copytree(demo_repo, ziel)
    monkeypatch.setenv("STOCKMASTER_DATA_DIR", str(ziel))
    config.einstellungen.cache_clear()
    lesen.zuruecksetzen()
    yield ziel
    lesen.zuruecksetzen()


def _namen(inhalt: bytes) -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(inhalt), mode="r:gz") as tar:
        return tar.getnames()


def test_export_ohne_secrets(kopie, admin):
    from stockmaster import appdaten

    appdaten.geheimnis_setzen("claude_token", TOKEN)
    antwort = admin.post("/api/sicherung/export", json={})
    assert antwort.status_code == 200 and antwort.headers["content-type"] == "application/gzip"
    namen = _namen(antwort.content)
    assert "MANIFEST.json" in namen and "spielstand/.git/HEAD" in namen and "spielstand/trades/aggressiv.csv" in namen
    assert "app/einstellungen.json" in namen and "app/geheimnisse.enc.json" not in namen
    assert not any(".cache" in n or "master.key" in n or "geheimnisse.json" in n for n in namen)
    assert TOKEN.encode() not in antwort.content
    with tarfile.open(fileobj=io.BytesIO(antwort.content), mode="r:gz") as tar:
        for info in tar.getmembers():
            if info.isfile():
                assert TOKEN.encode() not in tar.extractfile(info).read()
    assert "sicherung_export" in [z["aktion"] for z in admin.get("/api/admin/audit").json()]


def test_export_mit_secrets_nur_bestaetigt_mit_passwort(kopie, admin):
    assert admin.post("/api/sicherung/export", json={"mit_geheimnissen": True, "sicherungs_passwort": "x" * 12}
                      ).status_code == 422
    assert admin.post("/api/sicherung/export", json={"mit_geheimnissen": True, "bestaetigt": True,
                                                     "sicherungs_passwort": "kurz"}).status_code == 422


def test_rundlauf_mit_secrets(kopie, admin, tmp_path):
    from stockmaster import appdaten

    appdaten.geheimnis_setzen("claude_token", TOKEN)
    appdaten.bereich_speichern("news", {"intervall_minuten": 30})
    kopf_vorher = subprocess.run(["git", "rev-parse", "HEAD"], cwd=kopie, capture_output=True, text=True).stdout
    antwort = admin.post("/api/sicherung/export", json={"mit_geheimnissen": True, "bestaetigt": True,
                                                        "sicherungs_passwort": "ein-langes-passwort"})
    assert antwort.status_code == 200 and "app/geheimnisse.enc.json" in _namen(antwort.content)
    assert TOKEN.encode() not in antwort.content
    # Zustand verändern, dann wiederherstellen
    (kopie / "lessons.md").write_text("verändert\n")
    appdaten.geheimnis_loeschen("claude_token")
    appdaten.bereich_speichern("news", {"intervall_minuten": 60})
    ohne_passwort = admin.post("/api/sicherung/wiederherstellen", content=antwort.content)
    assert ohne_passwort.status_code == 403
    falsch = admin.post("/api/sicherung/wiederherstellen", content=antwort.content,
                        headers={"X-Bestaetigung-Passwort": ADMIN_PW, "X-Sicherung-Passwort": "falsch-falsch-falsch"})
    assert falsch.status_code == 422 and "Sicherungspasswort falsch" in falsch.json()["detail"]
    gut = admin.post("/api/sicherung/wiederherstellen", content=antwort.content,
                     headers={"X-Bestaetigung-Passwort": ADMIN_PW, "X-Sicherung-Passwort": "ein-langes-passwort"})
    assert gut.status_code == 200, gut.text
    assert gut.json()["geheimnisse"] == ["claude_token"]
    assert "verändert" not in (kopie / "lessons.md").read_text()
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=kopie, capture_output=True, text=True).stdout == kopf_vorher
    assert appdaten.geheimnis("claude_token") == TOKEN
    assert appdaten.laden()["news"]["intervall_minuten"] == 30
    vorher = list((tmp_path / "app" / "sicherungen").glob("vor-wiederherstellung-*.tar.gz"))
    assert len(vorher) == 1
    # Nach der Wiederherstellung liest die API den neuen Stand
    assert admin.get("/api/spiel/ueberblick").status_code == 200


def test_wiederherstellung_lehnt_boese_archive_ab(kopie, admin):
    def archiv(eintraege):
        puffer = io.BytesIO()
        with tarfile.open(fileobj=puffer, mode="w:gz") as tar:
            for name, inhalt, typ in eintraege:
                info = tarfile.TarInfo(name)
                info.type = typ
                if typ == tarfile.SYMTYPE:
                    info.linkname = "/etc/passwd"
                daten = inhalt.encode()
                info.size = len(daten) if typ == tarfile.REGTYPE else 0
                tar.addfile(info, io.BytesIO(daten) if typ == tarfile.REGTYPE else None)
        return puffer.getvalue()

    manifest = ("MANIFEST.json", json.dumps({"format": "stockmaster-sicherung", "version": 1}), tarfile.REGTYPE)
    kopf = {"X-Bestaetigung-Passwort": ADMIN_PW}
    for boese, text in (([manifest, ("../ausbruch.txt", "x", tarfile.REGTYPE)], "Unzulässiger Pfad"),
                        ([manifest, ("spielstand/link", "", tarfile.SYMTYPE)], "Unzulässiger Eintrag"),
                        ([manifest, ("anderes/datei", "x", tarfile.REGTYPE)], "Unbekannter Eintrag"),
                        ([("spielstand/a.txt", "x", tarfile.REGTYPE)], "Keine StockMaster-Sicherung"),
                        ([manifest, ("spielstand/a.txt", "x", tarfile.REGTYPE)], "kein Spielstand-Git")):
        antwort = admin.post("/api/sicherung/wiederherstellen", content=archiv(boese), headers=kopf)
        assert antwort.status_code == 422 and text in antwort.json()["detail"], (text, antwort.text)
    assert admin.post("/api/sicherung/wiederherstellen", content=b"kein tar", headers=kopf).status_code == 422
    assert (kopie / ".git").is_dir() and (kopie / "portfolios" / "defensiv.json").exists()


def test_wiederherstellung_nicht_waehrend_session(kopie, admin):
    (kopie / "session.lock").write_text(json.dumps({"person": "auftraggeber-a", "start": "2099-01-01T00:00:00+01:00"}))
    antwort = admin.post("/api/sicherung/export", json={})
    ergebnis = admin.post("/api/sicherung/wiederherstellen", content=antwort.content,
                          headers={"X-Bestaetigung-Passwort": ADMIN_PW})
    assert ergebnis.status_code == 422 and "Session" in ergebnis.json()["detail"]


def test_nur_admin(nutzer):
    assert nutzer.post("/api/sicherung/export", json={}).status_code == 404


def test_cli_rundlauf(kopie, tmp_path, monkeypatch):
    from stockmaster import __main__ as cli
    from stockmaster import appdaten

    appdaten.geheimnis_setzen("kurs_key_finnhub", "finnhub-key-424242")
    monkeypatch.setenv("SM_SICHERUNG_PASSWORT", "noch-ein-langes-passwort")
    datei = tmp_path / "s.tar.gz"
    assert cli.main(["sicherung-export", "--datei", str(datei), "--mit-geheimnissen"]) == 0
    appdaten.geheimnis_loeschen("kurs_key_finnhub")
    assert cli.main(["sicherung-import", "--datei", str(datei), "--geheimnisse"]) == 0
    assert appdaten.geheimnis("kurs_key_finnhub") == "finnhub-key-424242"
