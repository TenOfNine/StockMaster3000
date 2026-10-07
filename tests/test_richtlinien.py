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
