"""Schattenbuch: Verworfen-Zeile lesen, Bewertung nach Kosten, Vergleich mit Käufen, bucht nie (ohne Netzwerk)."""

from datetime import date
from decimal import Decimal

import pytest

import gemeinsam as g
import kurse
import schattenbuch
from test_prognosen import kerzen_schreiben

# Dienstag 2026-11-03; 5 Handelstage später ist der 10.11.
TAGE = {"2026-11-04": "101", "2026-11-05": "102", "2026-11-06": "103", "2026-11-09": "104", "2026-11-10": "110"}


def kurs_protokollieren(ticker, zeit, kurs):
    g.csv_anhaengen(kurse.kurs_protokoll_pfad(date.fromisoformat(zeit[:10])), kurse.KURS_FELDER, [{
        "zeit": f"{zeit}:00+01:00", "ticker": ticker, "kurs": kurs, "waehrung": "EUR", "quelle": "test", "markt_offen": "ja"}])


def eintraege(projekt, session_zeilen, j_zeilen=(), datum="2026-11-03"):
    zeilen = [f"# Journal {datum} (auftraggeber-a)", ""]
    zeilen += list(j_zeilen)
    zeilen += [f"### S-{datum.replace('-', '')}-01 | Session | auftraggeber-a", f"- Zeit: {datum} 11:00", *session_zeilen, ""]
    (projekt / "journal" / f"{datum}_auftraggeber-a.md").write_text("\n".join(zeilen), encoding="utf-8")


def erwartete_rendite(kauf, verkauf):
    halb = Decimal("0.0005")
    stueck = Decimal("99") / (Decimal(kauf) * (1 + halb))
    return float((stueck * Decimal(verkauf) * (1 - halb) - Decimal("1")) / Decimal("100") - 1)


def test_verworfen_lesen():
    k, f = schattenbuch.verworfen_lesen("ausgewogen:SAP.DE=zu teuer; NVDA=Spread; keine=")
    assert [(x["profil"], x["ticker"], x["grund"]) for x in k] == [("ausgewogen", "SAP.DE", "zu teuer"), (None, "NVDA", "Spread")]
    assert len(f) == 1
    assert schattenbuch.verworfen_lesen("keine") == ([], [])
    _, f = schattenbuch.verworfen_lesen("unbekannt:SAP.DE=x; ^FOO=Index; SAP.DE=")
    assert len(f) == 3


def test_nettorendite_handgerechnet(projekt):
    # 99 EUR / (100 * 1,0005) Stück, Verkauf zu 110 * 0,9995, abzüglich 1 EUR
    assert schattenbuch.nettorendite(Decimal("100"), Decimal("110")) == pytest.approx(0.0779, abs=1e-4)
    assert schattenbuch.nettorendite(Decimal("100"), Decimal("100")) == pytest.approx(-0.0210, abs=1e-4)
    assert schattenbuch.nettorendite(Decimal("100"), Decimal("110")) == pytest.approx(erwartete_rendite("100", "110"))


def test_bewertung_und_vergleich_mit_kauf(projekt, uhr):
    kerzen_schreiben("SAP.DE", TAGE)
    kerzen_schreiben("NVDA", {k: str(Decimal(v) * 2) for k, v in TAGE.items()})
    kurs_protokollieren("SAP.DE", "2026-11-03T11:05", "100")
    kurs_protokollieren("NVDA", "2026-11-03T11:05", "200")
    kurs_protokollieren("SAP.DE", "2026-11-03T10:05", "100")
    eintraege(projekt, ["- Verworfen: ausgewogen:SAP.DE=zu teuer"],
              ["### J-20261103-01 | aggressiv | NVDA", "- Zeit: 2026-11-03 10:00", "- Aktion: Kauf", "- These: x", ""])
    kurs_protokollieren("NVDA", "2026-11-03T10:05", "200")
    e = schattenbuch.auswerten(date(2026, 11, 20))
    v = e["verworfen"][0]
    assert v["ticker"] == "SAP.DE" and v["einstieg"]["kurs"] == 100
    assert v["horizonte"]["5"]["status"] == "bewertet" and v["horizonte"]["5"]["kurs"] == 110
    assert v["horizonte"]["5"]["rendite"] == pytest.approx(erwartete_rendite("100", "110"))
    assert v["horizonte"]["20"]["status"] == "offen"
    k = e["gekauft"][0]
    assert k["ticker"] == "NVDA" and k["horizonte"]["5"]["rendite"] == pytest.approx(erwartete_rendite("200", "220"))
    assert e["vergleich"]["verworfen"]["5"]["n"] == 1 and e["vergleich"]["gekauft"]["5"]["n"] == 1
    assert e["vergleich"]["je_profil"]["ausgewogen"]["verworfen"]["5"]["n"] == 1
    assert schattenbuch.ergebnis_pfad().exists()


def test_ohne_protokollkurs_keine_bewertung_kein_backdating(projekt, uhr):
    kerzen_schreiben("SAP.DE", {**TAGE, "2026-11-02": "90"})
    eintraege(projekt, ["- Verworfen: SAP.DE=zu teuer"])
    e = schattenbuch.auswerten(date(2026, 11, 20))
    assert e["verworfen"][0]["status"] == "kein_kurs" and e["ohne_kurs"] == 1
    assert e["vergleich"]["verworfen"]["5"]["n"] == 0


def test_kurs_vor_dem_eintrag_zaehlt_nicht(projekt, uhr):
    kerzen_schreiben("SAP.DE", TAGE)
    kurs_protokollieren("SAP.DE", "2026-11-03T09:00", "50")
    eintraege(projekt, ["- Verworfen: SAP.DE=zu teuer"])
    assert schattenbuch.auswerten(date(2026, 11, 20))["verworfen"][0]["status"] == "kein_kurs"


def test_kurslücke_ungünstigerer_kurs(projekt, uhr):
    tage = dict(TAGE)
    del tage["2026-11-10"]
    tage["2026-11-11"] = "120"  # Nachbar höher; ungünstig für Long ist der niedrigere (104)
    kerzen_schreiben("SAP.DE", tage)
    kurs_protokollieren("SAP.DE", "2026-11-03T11:05", "100")
    eintraege(projekt, ["- Verworfen: SAP.DE=zu teuer"])
    h = schattenbuch.auswerten(date(2026, 11, 20))["verworfen"][0]["horizonte"]["5"]
    assert h["quelle"] == "luecke" and h["kurs"] == 104


def test_vor_beginn_nichts_und_hinweise(projekt, uhr):
    eintraege(projekt, ["- Verworfen: SAP.DE=x"], datum="2026-10-20")
    e = schattenbuch.auswerten(date(2026, 11, 20))
    assert e["verworfen"] == [] and schattenbuch.pruef_hinweise() == []
    eintraege(projekt, ["- Offene Punkte: x"], datum="2026-11-03")
    assert len(schattenbuch.pruef_hinweise()) == 1


def test_bucht_nie(projekt, uhr):
    import hashlib
    kerzen_schreiben("SAP.DE", TAGE)
    kurs_protokollieren("SAP.DE", "2026-11-03T11:05", "100")
    eintraege(projekt, ["- Verworfen: SAP.DE=x"])

    def stand():
        return {str(p): hashlib.sha1(p.read_bytes()).hexdigest() for d in ("portfolios", "trades", "journal")
                for p in (projekt / d).rglob("*") if p.is_file()}

    vorher = stand()
    schattenbuch.auswerten(date(2026, 11, 20))
    assert stand() == vorher


def test_ranking_abschnitt_und_cli(projekt, uhr, capsys):
    assert "Noch keine verworfenen" in "\n".join(schattenbuch.ranking_abschnitt(None))
    kerzen_schreiben("SAP.DE", TAGE)
    kurs_protokollieren("SAP.DE", "2026-11-03T11:05", "100")
    eintraege(projekt, ["- Verworfen: SAP.DE=x"])
    uhr.stellen("2026-11-20T10:00")
    assert schattenbuch.main(["auswerten"]) == 0
    assert "| 5 Handelstage | 1 | 7,8 % |" in capsys.readouterr().out
    assert schattenbuch.main(["liste"]) == 0
