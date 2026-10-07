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
    assert g.richtlinien_offen() == ["ausgewogen", "aggressiv"]
    daten = richtlinien.status()
    assert daten["profile"]["defensiv"] == {"vorhanden": True, "ausformuliert": True}
    assert richtlinien.main(["status"]) == 0


def test_pruefe_warnt_erst_nach_spielstart(projekt, uhr):
    assert pruefe.pruefe_richtlinien() == []
    _starten(projekt)
    for profil in g.PROFILE:
        (projekt / "strategie" / f"{profil}.md").write_text(init.vorlage(profil, g.heute()))
    befunde = pruefe.pruefe_richtlinien()
    assert [b.stufe for b in befunde] == ["WARNUNG"] * 3 and "noch die Vorlage" in befunde[0].text
    for profil in g.PROFILE:
        (projekt / "strategie" / f"{profil}.md").write_text(f"# {profil}\n")
    assert pruefe.pruefe_richtlinien() == []


def test_standard_richtlinien_sind_ausformuliert_mit_limits(projekt, uhr):
    for profil, hebel in (("defensiv", "3x"), ("ausgewogen", "5x"), ("aggressiv", "10x")):
        text = init.standard_text(profil, g.heute())
        assert f"Max. Hebel je Zertifikat beim Kauf: {hebel}" in text and g.RICHTLINIE_VORLAGE_MARKE not in text
        assert "{" not in text and "## Ausgangsstrategie" in text and "## Änderungshistorie" in text


def test_standard_uebernehmen_ueberschreibt_nichts(projekt, uhr, capsys):
    (projekt / "strategie" / "defensiv.md").write_text("# Anlagerichtlinie Defensiv\n\nStand: 2026-10-07 eigene.\n")
    (projekt / "strategie" / "ausgewogen.md").write_text(init.vorlage("ausgewogen", g.heute()))
    assert g.richtlinien_offen() == ["ausgewogen", "aggressiv"]
    assert richtlinien.main(["standard"]) == 0
    assert g.richtlinien_offen() == []
    assert "eigene" in (projekt / "strategie" / "defensiv.md").read_text()
    assert "Standard-Richtlinie" in (projekt / "strategie" / "aggressiv.md").read_text()
    assert richtlinien.standard_uebernehmen() == ["Alle Anlagerichtlinien sind bereits ausformuliert; nichts geändert."]
