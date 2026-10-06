"""AP11: Initialisierung."""

import re

import gemeinsam as g
import init
import pruefe


def aps_abhaken(projekt, bis=10):
    datei = projekt / "STATUS.md"
    text = datei.read_text()
    for n in range(1, bis + 1):
        text = re.sub(rf"^- \[ \] AP{n} ", f"- [x] AP{n} ", text, flags=re.M)
    datei.write_text(text)


def test_datum_in_der_vergangenheit_abgelehnt(projekt, uhr, capsys):
    aps_abhaken(projekt)
    uhr.stellen("2026-10-12T10:00:00")
    assert init.main(["--startdatum", "2026-10-09"]) == 1
    assert "liegt in der Vergangenheit" in capsys.readouterr().err
    assert g.vorhandene_profile() == []


def test_ohne_abgeschlossene_arbeitspakete_abgelehnt(projekt, uhr, capsys):
    aps_abhaken(projekt, bis=9)
    datei = projekt / "STATUS.md"
    datei.write_text(datei.read_text().replace("- [x] AP10 ", "- [ ] AP10 "))
    assert init.main(["--startdatum", "2026-10-13"]) == 1
    assert "offen: AP10" in capsys.readouterr().err


def test_wochenende_abgelehnt(projekt, uhr):
    aps_abhaken(projekt)
    assert init.main(["--startdatum", "2026-10-17"]) == 1


def test_initialisierung(projekt, uhr):
    aps_abhaken(projekt)
    uhr.stellen("2026-10-12T10:00:00")
    (projekt / "strategie" / "aggressiv.md").write_text("# schon ausformuliert\n")
    assert init.main(["--startdatum", "2026-10-12"]) == 0
    assert g.vorhandene_profile() == list(g.PROFILE)
    for profil in g.PROFILE:
        p = g.portfolio_laden(profil)
        assert p["cash"] == "1000.00" and p["startdatum"] == "2026-10-12" and p["verarbeitet_bis"] == "2026-10-11"
        assert (projekt / "trades" / f"{profil}.csv").read_text().startswith("trade_id,zeit,")
        assert (projekt / "data" / "nav" / f"{profil}.csv").exists()
    assert (projekt / "strategie" / "aggressiv.md").read_text() == "# schon ausformuliert\n"
    assert "Max. Hebel je Zertifikat beim Kauf: 3x" in (projekt / "strategie" / "defensiv.md").read_text()
    assert "- Startdatum des Spiels: 2026-10-12" in (projekt / "STATUS.md").read_text()
    assert [str(b) for b in pruefe.alle_pruefungen() if b.stufe == "FEHLER"] == []
    # zweite Initialisierung abgelehnt
    assert init.main(["--startdatum", "2026-10-13"]) == 1
