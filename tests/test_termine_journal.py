"""Fällige Reviews, Session-Einträge und Journal-Vorlage."""

from datetime import date

import gemeinsam as g
import pruefe
import session
import termine
from helfer import portfolio, sperre

J_VOLL = """### J-20261012-01 | ausgewogen | SAP.DE
- Zeit: 2026-10-12 10:00
- Aktion: Kauf, Aktie, long
- These: Cloud-Wachstum
  über Erwartung
- Szenarien: Bull 30 % / Base 50 % / Bear 20 %
- Katalysator und Zeithorizont: Quartalszahlen, 3 Monate
- Einstieg, Stop, Kursziel: 200 / 190 / 230
- Positionsgröße und Risikorechnung: 200 EUR, Verlust bis Stop 10 EUR
- Quellen: https://example.org/sap, 2026-10-12
- Unsicherheiten: Zinsumfeld
"""

S_VOLL = """### S-20261012-01 | Session | auftraggeber-a
- Zeit: 2026-10-12 11:00
- Marktlage: ruhig (https://example.org, 2026-10-12)
- Defensiv: keine Order; Alternative Anleihe-ETF verworfen
- Ausgewogen: Order J-20261012-01
- Aggressiv: keine Order
- Overnight: keine Daueranweisung, Ausnahme (a) mit Zahlen
- Offene Punkte und Termine für die nächste Session: Zahlen SAP
"""


def schreiben(projekt, text, datei="2026-10-12_auftraggeber-a.md"):
    (projekt / "journal" / datei).write_text(text, encoding="utf-8")


def test_parser_liest_j_und_s_mit_feldern(projekt):
    schreiben(projekt, "# Journal\n\n" + J_VOLL + "\n" + S_VOLL)
    bloecke = g.journal_bloecke()
    assert [b["id"] for b in bloecke] == ["J-20261012-01", "S-20261012-01"]
    j, s = bloecke
    assert j["felder"]["these"] == "Cloud-Wachstum über Erwartung"
    assert j["portfolio"] == "ausgewogen" and j["person"] == "auftraggeber-a"
    assert s["art"] == "S" and s["auftraggeber"] == "auftraggeber-a"
    assert s["zeit"].hour == 11
    assert list(g.journal_eintraege()) == ["J-20261012-01"]
    assert pruefe.pruefe_journal_vollstaendigkeit() == []
    assert pruefe.pruefe_session_eintraege() == []


def test_unvollstaendige_eintraege_erzeugen_warnungen(projekt):
    schreiben(projekt, "### J-20261012-01 | ausgewogen | SAP.DE\n- Zeit: 2026-10-12 10:00\n- These: x\n"
                       "- Quellen: Handelsblatt\n- Szenarien: eher positiv\n")
    befunde = [str(b) for b in pruefe.pruefe_journal_vollstaendigkeit()]
    assert any("es fehlt Aktion" in b for b in befunde)
    assert any("Quellen ohne URL" in b for b in befunde)
    assert any("Szenarien ohne Wahrscheinlichkeiten" in b for b in befunde)
    assert all(b.startswith("WARNUNG") for b in befunde)
    session_befunde = pruefe.pruefe_session_eintraege()
    assert len(session_befunde) == 1 and "kein Session-Eintrag" in session_befunde[0].text


def test_laufende_session_noch_ohne_s_eintrag_keine_warnung(projekt, uhr):
    uhr.stellen("2026-10-12T12:00:00")
    sperre(projekt, "auftraggeber-a", "2026-10-12T09:30:00+02:00")
    schreiben(projekt, J_VOLL)
    assert pruefe.pruefe_session_eintraege() == []


def test_session_ende_warnt_ohne_s_eintrag(projekt, uhr, capsys):
    uhr.stellen("2026-10-12T12:00:00")
    sperre(projekt, "auftraggeber-a", "2026-10-12T09:30:00+02:00")
    schreiben(projekt, J_VOLL)
    assert session.main(["ende", "--ohne-git"]) == 0
    assert "kein Session-Eintrag" in capsys.readouterr().out
    sperre(projekt, "auftraggeber-a", "2026-10-12T09:30:00+02:00")
    schreiben(projekt, J_VOLL + "\n" + S_VOLL)
    assert session.main(["ende", "--ohne-git"]) == 0
    assert "kein Session-Eintrag" not in capsys.readouterr().out


def test_faellige_reviews(projekt):
    assert termine.faellige_reviews(date(2026, 10, 20)) == []  # nicht initialisiert
    portfolio(startdatum="2026-09-28")  # Starttag: Reviews zählen ab hier in Spieltagen, nicht nach Kalender
    assert termine.faellige_reviews(date(2026, 10, 4)) == []  # erster Zeitraum endet am 2026-10-04 (noch nicht vorbei)
    faellig = termine.faellige_reviews(date(2026, 10, 14))
    assert [(f["art"], f["datei"]) for f in faellig] == [("woche", "reviews/2026-10-04_woche.md"),
                                                         ("woche", "reviews/2026-10-11_woche.md")]
    assert faellig[0]["zeitraum"] == "2026-09-28 bis 2026-10-04"
    (projekt / "reviews" / "2026-10-04_woche.md").write_text("# Review\n")
    (projekt / "reviews" / "2026-10-11_woche.md").write_text("# Review\n")
    assert termine.faellige_reviews(date(2026, 10, 14)) == []
    assert termine.faellige_reviews(date(2026, 10, 19))[0]["datei"] == "reviews/2026-10-18_woche.md"
    # Monat nach 28 Tagen, Quartal nach 91 Tagen, unabhängig von Kalendermonaten.
    arten = {(f["art"], f["datei"]) for f in termine.faellige_reviews(date(2026, 10, 26))}
    assert ("monat", "reviews/2026-10-25_monat.md") in arten
    assert not any(a == "quartal" for a, _ in arten)
    assert ("quartal", "reviews/2026-12-27_quartal.md") in {(f["art"], f["datei"]) for f in
                                                          termine.faellige_reviews(date(2026, 12, 28))}


def test_review_zeitraeume_beginnen_am_starttag_mitten_in_der_woche(projekt):
    portfolio(startdatum="2026-10-14")  # Mittwoch: keine halbe Kalenderwoche, erster Zeitraum hat 7 volle Tage
    assert termine.faellige_reviews(date(2026, 10, 20)) == []
    assert [f["datei"] for f in termine.faellige_reviews(date(2026, 10, 21))] == ["reviews/2026-10-20_woche.md"]


def test_pflicht_review_stufe_2(projekt):
    p = portfolio(startdatum="2026-10-12", stufe=2)
    p["stufe2_seit"] = "2026-10-13"
    g.portfolio_speichern(p)
    faellig = termine.faellige_reviews(date(2026, 10, 14))
    assert faellig[-1]["art"] == "stufe2" and "bewertung.py review --profil ausgewogen" in faellig[-1]["text"]
    p["stufe2_review"] = {"datei": "reviews/x.md", "zeit": "2026-10-14T10:00:00+02:00"}
    g.portfolio_speichern(p)
    assert all(f["art"] != "stufe2" for f in termine.faellige_reviews(date(2026, 10, 14)))


def test_atomar_geschriebene_dateien_beachten_umask(projekt):
    import os
    alt = os.umask(0o022)
    try:
        ziel = projekt / "data" / "probe.csv"
        g.atomar_schreiben(ziel, "x\n")
        assert ziel.stat().st_mode & 0o777 == 0o644
    finally:
        os.umask(alt)
