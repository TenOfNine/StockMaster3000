"""Hilfsfunktionen für Tests: Portfolios, Journal, Sperre."""

import json
from decimal import Decimal

import gemeinsam as g


def portfolio(profil="ausgewogen", cash="1000.00", startdatum="2026-10-12", verarbeitet_bis="2026-10-11",
              positionen=None, stufe=0, status="aktiv", hoechststand="1000.00"):
    daten = {
        "profil": profil, "startdatum": startdatum, "cash": cash, "verarbeitet_bis": verarbeitet_bis,
        "hoechststand": hoechststand, "drawdown_stufe": stufe, "status": status,
        "positionen": positionen or [], "offene_orders": [],
        "zaehler": {"order": 0, "position": len(positionen or []), "trade": 0},
        "stufe2_seit": None, "stufe2_review": None,
    }
    g.portfolio_speichern(daten)
    return daten


def aktie(id_, ticker, stueck, einstand="100", stop=None, kursziel=None, eroeffnet="2026-10-01T10:00:00+02:00"):
    return {"id": id_, "typ": "aktie", "richtung": "long", "ticker": ticker, "basiswert": ticker,
            "stueck": str(stueck), "einstand": str(einstand), "eroeffnet": eroeffnet, "parameter": {},
            "stop": stop, "kursziel": kursziel, "journal_id": "J-20261001-01",
            "stop_historie": [{"ab": eroeffnet, "stop": stop, "kursziel": kursziel}]}


def journal(projekt, person="patrick", datum="2026-10-12", eintraege=(("01", "10:00", "ausgewogen", "SAP.DE"),)):
    zeilen = [f"# Journal {datum} ({person})", ""]
    for nummer, zeit, profil, instrument in eintraege:
        zeilen += [f"### J-{datum.replace('-', '')}-{nummer} | {profil} | {instrument}",
                   f"- Zeit: {datum} {zeit}", "- Aktion: Kauf", "- These: Test", ""]
    datei = projekt / "journal" / f"{datum}_{person}.md"
    datei.write_text("\n".join(zeilen), encoding="utf-8")
    return datei


def sperre(projekt, person="patrick", start="2026-10-12T09:30:00+02:00"):
    (projekt / "session.lock").write_text(json.dumps({"person": person, "start": start}), encoding="utf-8")


def laden(profil="ausgewogen"):
    return g.portfolio_laden(profil)


def D(x):
    return Decimal(str(x))
