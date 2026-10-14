"""Strukturierte Prognosen: Block lesen, auswerten, Brier und Kalibrierung, Prüfhinweise (ohne Netzwerk)."""

import json
from datetime import date
from decimal import Decimal

import pytest

import gemeinsam as g
import kurse
import prognosen

BLOCK = "ticker=SAP.DE; horizont=5; bull=0.30@112; base=0.50@104; bear=0.20@93; start=100"


def kerzen_schreiben(ticker, schluesse):
    zeilen = [{"datum": d, "open": k, "high": k, "low": k, "close": k, "dividende": "0", "split": "0"}
              for d, k in sorted(schluesse.items())]
    g.csv_schreiben(kurse.historie_pfad(ticker), kurse.HISTORIE_FELDER, zeilen)


def journal_schreiben(projekt, eintraege, datum="2026-09-01", person="auftraggeber-a"):
    zeilen = [f"# Journal {datum} ({person})", ""]
    for nummer, profil, aktion, prognose in eintraege:
        zeilen += [f"### J-{datum.replace('-', '')}-{nummer} | {profil} | SAP.DE", f"- Zeit: {datum} 10:00",
                   f"- Aktion: {aktion}", "- These: Test"]
        if prognose:
            zeilen.append(f"- Prognose: {prognose}")
        zeilen.append("")
    (projekt / "journal" / f"{datum}_{person}.md").write_text("\n".join(zeilen), encoding="utf-8")


# 2026-09-01 ist ein Dienstag; Horizont 5 Handelstage endet am 2026-09-08.
TAGE = {"2026-09-02": "101", "2026-09-03": "102", "2026-09-04": "103", "2026-09-07": "104", "2026-09-08": "105"}


def test_block_gueltig_mit_komma_und_grossschreibung():
    p, fehler = prognosen.block_lesen("Ticker=SAP.DE; Horizont=20; bull=0,3@112,5; base=0,5@104; bear=0,2@93")
    assert fehler == [] and p["ticker"] == "SAP.DE" and p["ziel"]["bull"] == 112.5 and p["start"] is None


@pytest.mark.parametrize("text, stichwort", [
    ("ticker=SAP.DE; horizont=5; bull=0.4@112; base=0.5@104; bear=0.2@93", "summieren"),
    ("ticker=SAP.DE; horizont=5; bull=0.3@112; base=0.5@104", "bear fehlt"),
    ("ticker=SAP.DE; horizont=0; bull=0.3@112; base=0.5@104; bear=0.2@93", "horizont"),
    ("horizont=5; bull=0.3@112; base=0.5@104; bear=0.2@93", "ticker fehlt"),
    ("ticker=SAP.DE; horizont=5; bull=0.3@93; base=0.5@104; bear=0.2@112", "unplausibel"),
    ("ticker=SAP.DE; horizont=5; bull=0.3@900; base=0.5@104; bear=0.2@93; start=100", "Fünffache"),
    ("ticker=SAP.DE; horizont=5; bull=0.3@112; base=0.5@104; bear=0.2@93; x=1", "unbekannte"),
    ("ticker=SAP.DE; horizont=5; bull=abc; base=0.5@104; bear=0.2@93", "nicht lesbar"),
    ("ticker=SAP.PA; horizont=5; bull=0.3@112; base=0.5@104; bear=0.2@93", "Universum"),
])
def test_block_ungueltig(text, stichwort):
    p, fehler = prognosen.block_lesen(text)
    assert p is None and any(stichwort in f for f in fehler), fehler


def test_szenario_naechstes_ziel():
    p, _ = prognosen.block_lesen(BLOCK)
    assert prognosen.tatsaechliches_szenario(p, 111) == "bull"
    assert prognosen.tatsaechliches_szenario(p, 95) == "bear"
    assert prognosen.tatsaechliches_szenario(p, 103) == "base"


def test_faellige_prognose_wird_ausgewertet(projekt, uhr):
    uhr.stellen("2026-10-12T10:00")
    kerzen_schreiben("SAP.DE", TAGE)
    journal_schreiben(projekt, [("01", "ausgewogen", "Kauf", BLOCK)])
    e = prognosen.auswerten(date(2026, 10, 12))
    p = e["prognosen"][0]
    assert p["status"] == "ausgewertet" and p["ende"] == "2026-09-08"
    assert p["kurs_ende"] == 105 and p["szenario"] == "base" and p["kurs_quelle"] == "kerze"
    # Brier: (0.3-0)^2 + (0.5-1)^2 + (0.2-0)^2 = 0.09 + 0.25 + 0.04
    assert p["brier"] == pytest.approx(0.38)
    assert p["richtung_treffer"] is True
    # erwartet 0.3*112+0.5*104+0.2*93 = 104.2; Fehler gegen 105 bei Start 100: -0.8 %
    assert p["erwartet"] == pytest.approx(104.2)
    assert p["fehler_erwartung"] == pytest.approx(-0.008)
    assert e["gesamt"]["brier"] == pytest.approx(0.38)
    assert e["profile"]["ausgewogen"]["ausgewertet"] == 1
    assert e["gesamt"]["belastbar"] is False
    assert json.loads(prognosen.ergebnis_pfad().read_text(encoding="utf-8"))["gesamt"]["ausgewertet"] == 1


def test_nicht_faellige_prognose_bleibt_offen(projekt, uhr):
    kerzen_schreiben("SAP.DE", TAGE)
    journal_schreiben(projekt, [("01", "ausgewogen", "Kauf", BLOCK)])
    e = prognosen.auswerten(date(2026, 9, 8))
    assert e["prognosen"][0]["status"] == "offen"
    assert e["gesamt"]["ausgewertet"] == 0 and e["gesamt"]["brier"] is None and e["gesamt"]["offen"] == 1


def test_kursluecke_ungünstigere_annahme(projekt, uhr):
    """Fehlt die Kerze am Horizontende, gilt der Nachbar, der weiter vom erwarteten Kurs (104,2) liegt."""
    tage = dict(TAGE)
    del tage["2026-09-08"]
    tage["2026-09-07"] = "104"
    tage["2026-09-09"] = "110"
    kerzen_schreiben("SAP.DE", tage)
    journal_schreiben(projekt, [("01", "ausgewogen", "Kauf", BLOCK)])
    p = prognosen.auswerten(date(2026, 10, 12))["prognosen"][0]
    assert p["kurs_quelle"] == "luecke" and p["kurs_ende"] == 110 and p["szenario"] == "bull"


def test_ohne_kerzen_ist_luecke_nicht_ausgewertet(projekt, uhr):
    journal_schreiben(projekt, [("01", "ausgewogen", "Kauf", BLOCK)])
    e = prognosen.auswerten(date(2026, 10, 12))
    assert e["prognosen"][0]["status"] == "luecke" and e["gesamt"]["luecke"] == 1


def test_startkurs_aus_protokoll_vor_schluss(projekt, uhr):
    kerzen_schreiben("SAP.DE", {**TAGE, "2026-08-31": "99"})
    g.csv_anhaengen(kurse.kurs_protokoll_pfad(date(2026, 9, 1)), kurse.KURS_FELDER, [{
        "zeit": "2026-09-01T10:05:00+02:00", "ticker": "SAP.DE", "kurs": "100.50", "waehrung": "EUR",
        "quelle": "test", "markt_offen": "ja"}])
    journal_schreiben(projekt, [("01", "ausgewogen", "Kauf", BLOCK.replace("; start=100", ""))])
    p = prognosen.auswerten(date(2026, 10, 12))["prognosen"][0]
    assert p["start"] == 100.5 and p["start_quelle"] == "protokoll"


def test_startkurs_ersatz_letzter_schluss(projekt, uhr):
    kerzen_schreiben("SAP.DE", {**TAGE, "2026-08-31": "99"})
    journal_schreiben(projekt, [("01", "ausgewogen", "Kauf", BLOCK.replace("; start=100", ""))])
    p = prognosen.auswerten(date(2026, 10, 12))["prognosen"][0]
    assert p["start"] == 99 and p["start_quelle"] == "schluss"


def test_kalibrierung_und_brier_ueber_mehrere(projekt, uhr):
    kerzen_schreiben("SAP.DE", TAGE)
    journal_schreiben(projekt, [("01", "ausgewogen", "Kauf", BLOCK),
                                ("02", "aggressiv", "Kauf", BLOCK.replace("0.30@112; base=0.50", "0.60@112; base=0.20"))])
    e = prognosen.auswerten(date(2026, 10, 12))
    assert e["gesamt"]["ausgewertet"] == 2
    # zweite: 0.6^2 + (0.2-1)^2 + 0.2^2 = 0.36 + 0.64 + 0.04 = 1.04; Mittel (0.38 + 1.04) / 2
    assert e["gesamt"]["brier"] == pytest.approx(0.71)
    assert set(e["profile"]) == {"ausgewogen", "aggressiv"}
    kal = {k["klasse"]: k for k in e["gesamt"]["kalibrierung"]}
    assert sum(k["n"] for k in kal.values()) == 6
    assert kal["0.5-0.6"]["n"] == 1 and kal["0.5-0.6"]["trefferquote"] == 1.0  # base 0.50 trifft
    assert kal["0.6-0.7"]["n"] == 1 and kal["0.6-0.7"]["trefferquote"] == 0.0  # bull 0.60 trifft nicht


def test_altes_journal_ohne_block_ist_unauffaellig(projekt, uhr):
    journal_schreiben(projekt, [("01", "ausgewogen", "Kauf", None)])
    e = prognosen.auswerten(date(2026, 10, 12))
    assert e["gesamt"]["anzahl"] == 0 and e["ungueltig"] == []
    assert prognosen.pruef_hinweise() == []  # vor dem Stichtag


def test_hinweise_ab_stichtag(projekt, uhr):
    journal_schreiben(projekt, [("01", "ausgewogen", "Kauf", None), ("02", "defensiv", "Verkauf", None),
                                ("03", "aggressiv", "Kauf", BLOCK), ("04", "overnight", "Kauf", None)], datum="2026-11-03")
    hinweise = prognosen.pruef_hinweise()
    assert len(hinweise) == 1 and "J-20261103-01" in hinweise[0] and "fehlt" in hinweise[0]


def test_hinweis_ungueltiger_block_auch_vor_stichtag(projekt, uhr):
    journal_schreiben(projekt, [("01", "ausgewogen", "Kauf", "ticker=SAP.DE; horizont=5")])
    hinweise = prognosen.pruef_hinweise()
    assert len(hinweise) == 1 and "ungültige Prognose" in hinweise[0]
    assert prognosen.auswerten(date(2026, 10, 12))["ungueltig"][0]["id"] == "J-20260901-01"


def test_ranking_abschnitt_leer_und_gefuellt(projekt, uhr):
    assert "Noch keine Prognosen" in "\n".join(prognosen.ranking_abschnitt(None))
    kerzen_schreiben("SAP.DE", TAGE)
    journal_schreiben(projekt, [("01", "ausgewogen", "Kauf", BLOCK)])
    text = "\n".join(prognosen.ranking_abschnitt(prognosen.auswerten(date(2026, 10, 12))))
    assert "| Gesamt | 1 | 1 | 0,380 |" in text and "kaum belastbar" in text


def test_cli_auswerten(projekt, uhr, capsys):
    kerzen_schreiben("SAP.DE", TAGE)
    journal_schreiben(projekt, [("01", "ausgewogen", "Kauf", BLOCK)])
    uhr.stellen("2026-10-12T10:00")
    assert prognosen.main(["auswerten"]) == 0
    assert "gesamt: 1 Prognosen, 1 ausgewertet" in capsys.readouterr().out
    assert prognosen.main(["liste"]) == 0


def test_pruefe_meldet_nur_warnungen(projekt, uhr):
    import pruefe
    journal_schreiben(projekt, [("01", "ausgewogen", "Kauf", "ticker=SAP.DE; horizont=5")], datum="2026-11-03")
    befunde = pruefe.pruefe_prognosen()
    assert befunde and all(b.stufe == "WARNUNG" for b in befunde)
