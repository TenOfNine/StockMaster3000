"""AP11: Initialisierung."""

import re

import gemeinsam as g
import init
import pruefe


def aps_abhaken(framework, bis=10):
    datei = framework / "STATUS.md"
    text = datei.read_text()
    for n in range(1, bis + 1):
        text = re.sub(rf"^- \[ \] AP{n} ", f"- [x] AP{n} ", text, flags=re.M)
    datei.write_text(text)


FREIGABE = ["--freigabe", "auftraggeber-a"]


def test_datum_in_der_vergangenheit_abgelehnt(projekt, framework, uhr, capsys):
    aps_abhaken(framework)
    uhr.stellen("2026-10-12T10:00:00")
    assert init.main(["--startdatum", "2026-10-09", *FREIGABE]) == 1
    assert "liegt in der Vergangenheit" in capsys.readouterr().err
    assert g.vorhandene_profile() == []


def test_ohne_abgeschlossene_arbeitspakete_abgelehnt(projekt, framework, uhr, capsys):
    aps_abhaken(framework, bis=9)
    datei = framework / "STATUS.md"
    datei.write_text(datei.read_text().replace("- [x] AP10 ", "- [ ] AP10 "))
    assert init.main(["--startdatum", "2026-10-13", *FREIGABE]) == 1
    assert "offen: AP10" in capsys.readouterr().err


def test_wochenende_abgelehnt(projekt, framework, uhr):
    aps_abhaken(framework)
    assert init.main(["--startdatum", "2026-10-17", *FREIGABE]) == 1


def test_freigabe_nur_durch_auftraggeber(projekt, framework, uhr, capsys):
    aps_abhaken(framework)
    assert init.main(["--startdatum", "2026-10-12", "--freigabe", "jemand"]) == 1
    assert "Freigabe nach AP12" in capsys.readouterr().err
    assert g.vorhandene_profile() == []


def test_initialisierung(projekt, framework, uhr):
    aps_abhaken(framework)
    status_vorher = (framework / "STATUS.md").read_text()
    uhr.stellen("2026-10-12T10:00:00")
    (projekt / "strategie" / "aggressiv.md").write_text("# schon ausformuliert\n")
    assert init.main(["--startdatum", "2026-10-12", *FREIGABE]) == 0
    assert g.vorhandene_profile() == list(g.PROFILE)
    for profil in g.PROFILE:
        p = g.portfolio_laden(profil)
        assert p["cash"] == "1000.00" and p["startdatum"] == "2026-10-12" and p["verarbeitet_bis"] == "2026-10-11"
        assert (projekt / "trades" / f"{profil}.csv").read_text().startswith("trade_id,zeit,")
        assert (projekt / "data" / "nav" / f"{profil}.csv").exists()
    assert (projekt / "strategie" / "aggressiv.md").read_text() == "# schon ausformuliert\n"
    assert "Max. Hebel je Zertifikat beim Kauf: 3x" in (projekt / "strategie" / "defensiv.md").read_text()
    # Startdatum und Freigabe stehen im Datenverzeichnis, das Framework bleibt unverändert.
    assert g.spiel_lesen()["startdatum"] == "2026-10-12"
    assert g.spiel_lesen()["freigabe_ap12"] == "auftraggeber-a"
    assert (framework / "STATUS.md").read_text() == status_vorher
    assert not (projekt / "STATUS.md").exists()
    assert [str(b) for b in pruefe.alle_pruefungen() if b.stufe == "FEHLER"] == []
    # zweite Initialisierung abgelehnt
    assert init.main(["--startdatum", "2026-10-13", *FREIGABE]) == 1
