"""Vorbereitung getrennter Claude-Läufe je Portfolio: Session-Einträge dürfen sich auf einzelne Portfolios beziehen."""

import pytest

import gemeinsam as g
import pruefe
from helfer import portfolio

SESSION = """# Journal 2026-10-13 (auftraggeber-a)

### S-20261013-01 | Session | auftraggeber-a
- Zeit: 2026-10-13 10:00
- Marktlage: ruhig
{portfolios}- Defensiv: Order J-20261013-01
- Ausgewogen: Ausnahme (a) mit Zahlen 1,2 %
- Handlung oder Ausnahme: {handlung}
- Offene Punkte: keine
"""


@pytest.fixture
def spiel(projekt):
    g.json_schreiben(g.spiel_pfad(), {"startdatum": "2026-10-12"})
    for p in ("defensiv", "ausgewogen", "aggressiv", "overnight"):
        portfolio(p, startdatum="2026-10-12", verarbeitet_bis="2026-10-12")


def schreiben(projekt, portfolios, handlung):
    zeile = f"- Portfolios: {portfolios}\n" if portfolios else ""
    (projekt / "journal" / "2026-10-13_auftraggeber-a.md").write_text(
        SESSION.format(portfolios=zeile, handlung=handlung), encoding="utf-8")


def test_ohne_portfolio_zeile_gilt_der_eintrag_fuer_alle(spiel, projekt):
    schreiben(projekt, None, "Defensiv: Order J-20261013-01")
    hinweise = [h["text"] for h in pruefe.handeln_hinweise() if h["art"] == "session"]
    assert any("Ausgewogen" in h or "ausgewogen" in h for h in hinweise)  # wie bisher: jedes Portfolio verlangt
    assert any("aggressiv" in h for h in hinweise)


def test_portfolio_zeile_begrenzt_die_pflicht(spiel, projekt):
    schreiben(projekt, "defensiv", "Defensiv: Order J-20261013-01")
    hinweise = [h["text"] for h in pruefe.handeln_hinweise() if h["art"] == "session"]
    assert hinweise == []
    # die fehlenden Zeilen anderer Portfolios werden für diesen Eintrag nicht mehr gemeldet
    bloecke = g.journal_bloecke()
    assert pruefe.sitzung_profile(bloecke[0]) == ["defensiv"]
    fehlend = [b.text for b in pruefe.pruefe_journal_vollstaendigkeit(bloecke) if "Aggressiv" in b.text]
    assert fehlend == []


def test_genanntes_portfolio_ohne_order_wird_weiter_gemeldet(spiel, projekt):
    schreiben(projekt, "aggressiv", "Defensiv: Order J-20261013-01")
    hinweise = [h["text"] for h in pruefe.handeln_hinweise() if h["art"] == "session"]
    assert any("aggressiv" in h for h in hinweise)
