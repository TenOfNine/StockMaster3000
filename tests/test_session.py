"""AP8: Session-Sperre: freie, eigene, fremde und verwaiste Sperre."""

import json
import subprocess

import gemeinsam as g
import session
from helfer import git_init, sperre


def lock(projekt):
    return json.loads((projekt / "session.lock").read_text())


def test_freie_sperre(projekt, uhr):
    uhr.stellen("2026-10-12T10:00:00")
    assert session.main(["start", "--person", "Auftraggeber-A", "--ohne-git"]) == 0
    assert lock(projekt) == {"person": "auftraggeber-a", "start": "2026-10-12T10:00:00+02:00", "art": "trading"}
    assert session.main(["ende", "--ohne-git"]) == 0
    assert not (projekt / "session.lock").exists()


def test_eigene_sperre_laeuft_weiter(projekt, uhr, capsys):
    uhr.stellen("2026-10-12T12:00:00")
    sperre(projekt, "auftraggeber-a", "2026-10-12T10:00:00+02:00")
    assert session.main(["start", "--person", "auftraggeber-a", "--ohne-git"]) == 0
    assert "Session läuft weiter" in capsys.readouterr().out
    assert lock(projekt)["start"] == "2026-10-12T10:00:00+02:00"


def test_fremde_sperre_bricht_ab(projekt, uhr, capsys):
    uhr.stellen("2026-10-12T15:59:00")
    sperre(projekt, "auftraggeber-b", "2026-10-12T10:00:00+02:00")
    assert session.main(["start", "--person", "auftraggeber-a", "--ohne-git"]) == 1
    assert "Session von auftraggeber-b läuft" in capsys.readouterr().err
    assert lock(projekt)["person"] == "auftraggeber-b"


def test_verwaiste_sperre_wird_uebernommen(projekt, uhr, capsys):
    uhr.stellen("2026-10-12T16:00:00")
    sperre(projekt, "auftraggeber-b", "2026-10-12T10:00:00+02:00")
    assert session.main(["start", "--person", "auftraggeber-a", "--ohne-git"]) == 0
    assert "verwaiste Sperre von auftraggeber-b" in capsys.readouterr().out
    assert lock(projekt) == {"person": "auftraggeber-a", "start": "2026-10-12T16:00:00+02:00", "art": "trading"}


def test_unbekannte_person(projekt, uhr):
    assert session.main(["start", "--person", "Mallory", "--ohne-git"]) == 1


def test_start_und_ende_committen_lokal_ohne_push(projekt, uhr, tmp_path_factory):
    remote = tmp_path_factory.mktemp("remote") / "repo.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    git_init(projekt)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=projekt, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "main"], cwd=projekt, check=True)
    remote_vorher = subprocess.run(["git", "rev-parse", "main"], cwd=remote, capture_output=True, text=True).stdout
    uhr.stellen("2026-10-12T10:00:00")
    assert session.main(["start", "--person", "auftraggeber-b"]) == 0
    log = subprocess.run(["git", "log", "--format=%s", "-1"], cwd=projekt, capture_output=True,
                         text=True).stdout.strip()
    assert log == "session: Start auftraggeber-b"
    assert session.main(["ende"]) == 0
    log = subprocess.run(["git", "log", "--format=%s", "-1"], cwd=projekt, capture_output=True,
                         text=True).stdout.strip()
    assert log == "session: Ende auftraggeber-b"
    assert not (projekt / "session.lock").exists()
    # Spielstand bleibt lokal: selbst ein vorhandenes Remote wird nie beschrieben.
    assert subprocess.run(["git", "rev-parse", "main"], cwd=remote, capture_output=True, text=True).stdout == remote_vorher


def test_ohne_spielstand_git_raeumt_auf(projekt, uhr):
    assert session.main(["start", "--person", "auftraggeber-a"]) == 1
    assert not (projekt / "session.lock").exists()


def test_testsession_ohne_warnung_zum_session_eintrag(projekt, uhr, capsys):
    uhr.stellen("2026-10-12T10:00:00")
    assert session.main(["start", "--person", "auftraggeber-a", "--art", "testsession", "--ohne-git"]) == 0
    assert "Testsession von auftraggeber-a gestartet" in capsys.readouterr().out
    assert lock(projekt)["art"] == "testsession"
    assert session.main(["status"]) == 0
    assert "(Testsession)" in capsys.readouterr().out
    assert session.main(["ende", "--ohne-git"]) == 0
    assert "WARNUNG" not in capsys.readouterr().out


def test_nachbuchung_ist_eine_session_art_ohne_session_eintrag(projekt, uhr, capsys):
    uhr.stellen("2026-10-12T00:30:00")
    assert session.main(["start", "--person", "auftraggeber-a", "--art", "nachbuchung", "--ohne-git"]) == 0
    assert "Nachbuchung von auftraggeber-a gestartet" in capsys.readouterr().out
    assert lock(projekt)["art"] == "nachbuchung"
    assert session.main(["status"]) == 0
    assert "(automatische Nachbuchung)" in capsys.readouterr().out
    assert session.main(["ende", "--ohne-git"]) == 0
    assert "WARNUNG" not in capsys.readouterr().out and not (projekt / "session.lock").exists()


def test_trading_session_warnt_weiter_ohne_session_eintrag(projekt, uhr, capsys):
    uhr.stellen("2026-10-12T10:00:00")
    assert session.main(["start", "--person", "auftraggeber-a", "--ohne-git"]) == 0
    assert lock(projekt)["art"] == "trading"
    capsys.readouterr()
    assert session.main(["ende", "--ohne-git"]) == 0
    assert "kein Session-Eintrag" in capsys.readouterr().out


def test_unbekannte_art_abgelehnt(projekt, uhr):
    import pytest

    with pytest.raises(SystemExit):
        session.main(["start", "--person", "auftraggeber-a", "--art", "frei", "--ohne-git"])


def test_richtlinien_session_ohne_warnung(projekt, uhr, capsys):
    uhr.stellen("2026-10-12T10:00:00")
    assert session.main(["start", "--person", "auftraggeber-a", "--art", "richtlinien", "--ohne-git"]) == 0
    assert "Richtlinien-Session von auftraggeber-a gestartet" in capsys.readouterr().out
    assert session.main(["ende", "--ohne-git"]) == 0
    assert "WARNUNG" not in capsys.readouterr().out
