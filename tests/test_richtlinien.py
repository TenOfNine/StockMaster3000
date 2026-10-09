"""Anlagerichtlinien (AP12 Punkt 2): Vorlage, Stand und Prüfwarnung."""

import json

import gemeinsam as g
import init
import pruefe
import richtlinien
from helfer import portfolio


def _starten(projekt):
    (projekt / "spiel.json").write_text(json.dumps({"startdatum": "2026-10-12"}))
    for profil in g.PROFILE:
        portfolio(profil)


def test_vorlage_enthaelt_verbindliche_limits(projekt, uhr):
    text = richtlinien.vorlage_text("defensiv")
    assert "Max. Hebel je Zertifikat beim Kauf: 3x" in text and g.RICHTLINIE_VORLAGE_MARKE in text


def test_status_vorlage_und_ausformuliert(projekt, uhr):
    assert g.richtlinien_offen() == list(g.PROFILE)  # nichts vorhanden
    (projekt / "strategie" / "defensiv.md").write_text(init.vorlage("defensiv", g.heute()))
    assert g.richtlinien_offen() == list(g.PROFILE)  # Vorlage zählt nicht
    (projekt / "strategie" / "defensiv.md").write_text("# Anlagerichtlinie Defensiv\n\nStand: 2026-10-07.\n")
    assert g.richtlinien_offen() == ["ausgewogen", "aggressiv", "overnight"]
    daten = richtlinien.status()
    assert daten["profile"]["defensiv"] == {"vorhanden": True, "ausformuliert": True}
    assert richtlinien.main(["status"]) == 0


def test_pruefe_warnt_erst_nach_spielstart(projekt, uhr):
    assert pruefe.pruefe_richtlinien() == []
    _starten(projekt)
    for profil in g.PROFILE:
        (projekt / "strategie" / f"{profil}.md").write_text(init.vorlage(profil, g.heute()))
    befunde = pruefe.pruefe_richtlinien()
    assert [b.stufe for b in befunde] == ["WARNUNG"] * 4 and "noch die Vorlage" in befunde[0].text
    for profil in g.PROFILE:
        (projekt / "strategie" / f"{profil}.md").write_text(f"# {profil}\n")
    assert pruefe.pruefe_richtlinien() == []


def test_standard_richtlinien_sind_ausformuliert_mit_limits(projekt, uhr):
    for profil, hebel in (("defensiv", "3x"), ("ausgewogen", "5x"), ("aggressiv", "10x"), ("overnight", "3x")):
        text = init.standard_text(profil, g.heute())
        assert f"Max. Hebel je Zertifikat beim Kauf: {hebel}" in text and g.RICHTLINIE_VORLAGE_MARKE not in text
        assert "{" not in text and "## Ausgangsstrategie" in text and "## Änderungshistorie" in text


def test_standard_uebernehmen_ueberschreibt_nichts(projekt, uhr, capsys):
    (projekt / "strategie" / "defensiv.md").write_text("# Anlagerichtlinie Defensiv\n\nStand: 2026-10-07 eigene.\n")
    (projekt / "strategie" / "ausgewogen.md").write_text(init.vorlage("ausgewogen", g.heute()))
    assert g.richtlinien_offen() == ["ausgewogen", "aggressiv", "overnight"]
    assert richtlinien.main(["standard"]) == 0
    assert g.richtlinien_offen() == []
    assert "eigene" in (projekt / "strategie" / "defensiv.md").read_text()
    assert "Standard-Richtlinie" in (projekt / "strategie" / "aggressiv.md").read_text()
    assert richtlinien.standard_uebernehmen() == ["Alle Anlagerichtlinien sind ausformuliert und aktuell; nichts geändert."]


def _alte_standard_richtlinie(projekt, profil, extra_zeile=""):
    """Standard-Richtlinie in der Fassung v1 (vor Umbau v2): ohne Versionsangabe, mit Nichtstun als Regel."""
    text = init.standard_text(profil, g.heute()).replace(f"Standard-Richtlinie v{g.RICHTLINIE_STANDARD_VERSION} aus",
                                                         "Standard-Richtlinie aus")
    text = text.replace(f"Standard-Richtlinie v{g.RICHTLINIE_STANDARD_VERSION} übernommen", "Standard-Richtlinie übernommen")
    text = text.replace("Handeln ist der Normalfall", "Nichtstun bleibt die Regel")
    (projekt / "strategie" / f"{profil}.md").write_text(text + extra_zeile, encoding="utf-8")


def test_unveraenderte_alte_standard_richtlinie_wird_aktualisiert_mit_erhalt_der_historie(projekt, uhr, capsys):
    _alte_standard_richtlinie(projekt, "defensiv")
    assert g.richtlinie_standard_version("defensiv") == 1 and g.richtlinie_unveraendert("defensiv")
    assert g.richtlinien_veraltet() == ["defensiv"]
    assert richtlinien.main(["standard"]) == 0
    ausgabe = capsys.readouterr().out
    assert "strategie/defensiv.md auf Standard-Richtlinie v2 aktualisiert" in ausgabe
    text = (projekt / "strategie" / "defensiv.md").read_text()
    assert g.richtlinie_standard_version("defensiv") == 2 and "Nichtstun bleibt die Regel" not in text
    historie = g.richtlinie_historie("defensiv")
    assert [z[1] for z in historie] == ["Spielstart", "Standard-Update"]  # die alte Zeile bleibt
    assert g.richtlinien_veraltet() == [] and g.richtlinie_unveraendert("defensiv")
    assert richtlinien.standard_uebernehmen() == ["Alle Anlagerichtlinien sind ausformuliert und aktuell; nichts geändert."]


def test_angepasste_standard_richtlinie_bleibt_unberuehrt_und_wird_gemeldet(projekt, uhr, capsys):
    zeile = "| 2026-10-10 | Marktlage | Risiko gesenkt | Review |\n"
    _alte_standard_richtlinie(projekt, "ausgewogen", extra_zeile=zeile)
    assert not g.richtlinie_unveraendert("ausgewogen") and g.richtlinien_veraltet() == []
    vorher = (projekt / "strategie" / "ausgewogen.md").read_text()
    meldungen = richtlinien.standard_uebernehmen()
    assert (projekt / "strategie" / "ausgewogen.md").read_text() == vorher
    assert any("ausgewogen.md ist angepasst und älter als Standard-Richtlinie v2" in m for m in meldungen)
