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
    assert lock(projekt) == {"person": "auftraggeber-a", "start": "2026-10-12T10:00:00+02:00"}
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
    assert lock(projekt) == {"person": "auftraggeber-a", "start": "2026-10-12T16:00:00+02:00"}


def test_unbekannte_person(projekt, uhr):
    assert session.main(["start", "--person", "Mallory", "--ohne-git"]) == 1


def test_start_committet_und_pusht_ende_committet(projekt, uhr, tmp_path_factory):
    remote = tmp_path_factory.mktemp("remote") / "repo.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    git_init(projekt)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=projekt, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "main"], cwd=projekt, check=True)
    uhr.stellen("2026-10-12T10:00:00")
    assert session.main(["start", "--person", "auftraggeber-b"]) == 0
    log = subprocess.run(["git", "log", "--format=%s", "origin/main", "-1"], cwd=projekt, capture_output=True,
                         text=True).stdout.strip()
    assert log == "session: Start auftraggeber-b"
    assert session.main(["ende"]) == 0
    log = subprocess.run(["git", "log", "--format=%s", "-1"], cwd=projekt, capture_output=True,
                         text=True).stdout.strip()
    assert log == "session: Ende auftraggeber-b"
    assert not (projekt / "session.lock").exists()


def test_push_fehlgeschlagen_raeumt_auf(projekt, uhr):
    git_init(projekt)  # kein Remote -> Push scheitert
    vorher = subprocess.run(["git", "rev-parse", "HEAD"], cwd=projekt, capture_output=True, text=True).stdout
    assert session.main(["start", "--person", "auftraggeber-a"]) == 1
    assert not (projekt / "session.lock").exists()
    nachher = subprocess.run(["git", "rev-parse", "HEAD"], cwd=projekt, capture_output=True, text=True).stdout
    assert vorher == nachher
