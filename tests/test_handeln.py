"""Umbau v2, Punkt 3: Handeln ist der Normalfall; Hinweise bei hoher Cashquote und bei Sessions ohne Order/Ausnahme."""

import gemeinsam as g
import pruefe
from helfer import portfolio


def session(projekt, handlung, datum="2026-10-12", nummer="01"):
    zeilen = [f"### S-{datum.replace('-', '')}-{nummer} | Session | auftraggeber-a", f"- Zeit: {datum} 11:00",
              "- Marktlage: ruhig (https://example.org, 2026-10-12)", "- Defensiv: x", "- Ausgewogen: x",
              "- Aggressiv: x", "- Overnight: x"]
    if handlung is not None:
        zeilen.append(f"- Handlung oder Ausnahme: {handlung}")
    zeilen.append("- Offene Punkte und Termine für die nächste Session: keine")
    (projekt / "journal" / f"{datum}_auftraggeber-a.md").write_text("\n".join(zeilen) + "\n", encoding="utf-8")


def texte():
    return [h["text"] for h in pruefe.handeln_hinweise()]


def test_session_mit_order_oder_belegter_ausnahme_ist_in_ordnung(projekt):
    session(projekt, "Defensiv: Order J-20261012-01 (Verlust bis Stop 0,8 % gegen Limit 1 %); "
                     "Ausgewogen: Ausnahme (a): kleinste Order hätte 2,4 % Verlust bis Stop gegen Limit 2 %, "
                     "Erwartungswert nach Kosten -1,20 EUR, geprüft SAP.DE, NVDA; "
                     "Aggressiv: Order J-20261012-02; Overnight: Order J-20261012-03")
    assert texte() == []


def test_fehlende_zeile_und_fehlende_portfolios_werden_gemeldet(projekt):
    session(projekt, None)
    assert any("'Handlung oder Ausnahme' fehlt" in t for t in texte())
    session(projekt, "Defensiv: Order J-20261012-01; Ausgewogen: Order J-20261012-02; Overnight: Order J-20261012-04")
    hinweise = texte()
    assert len(hinweise) == 1 and "aggressiv ohne Order und ohne belegte Ausnahme" in hinweise[0]


def test_ausnahme_ohne_zahlen_zaehlt_nicht(projekt):
    session(projekt, "Defensiv: Ausnahme (c): kein Kurs; Ausgewogen: Order J-20261012-02; Aggressiv: Order J-20261012-03; Overnight: Order J-20261012-04")
    hinweise = texte()
    assert len(hinweise) == 1 and "defensiv ohne Order; die Ausnahme braucht Zahlen" in hinweise[0]
    session(projekt, "Defensiv: nichts passt; Ausgewogen: Order J-20261012-02; Aggressiv: Order J-20261012-03; Overnight: Order J-20261012-04")
    assert len(texte()) == 1  # ohne das Wort Ausnahme gilt auch das nicht


def test_sessions_vor_dem_stichtag_werden_nicht_beanstandet(projekt):
    session(projekt, None, datum="2026-10-08")
    assert texte() == []


def test_warnungen_sind_nie_fehler(projekt):
    session(projekt, None)
    befunde = pruefe.pruefe_handeln()
    assert befunde and all(b.stufe == "WARNUNG" for b in befunde)


def nav(projekt, profil, quoten):
    zeilen = [{"datum": f"2026-10-{12 + i:02d}", "cash": "0", "positionswert": "0", "portfoliowert": "1000.00",
               "hoechststand": "1000.00", "drawdown": "0", "drawdown_stufe": 0, "exposure": "0",
               "cashquote": q, "zertifikate_anteil": "0", "status": "aktiv"} for i, q in enumerate(quoten)]
    g.csv_schreiben(projekt / "data" / "nav" / f"{profil}.csv", g.NAV_FELDER, zeilen)


def test_hohe_cashquote_ueber_mehrere_tage_wird_gemeldet(projekt):
    portfolio("ausgewogen")  # Mindest-Cashquote 5 %
    nav(projekt, "ausgewogen", ["0.60"] * 5)
    hinweise = texte()
    assert len(hinweise) == 1 and "ausgewogen: Cashquote im Schnitt 60 %" in hinweise[0] and "Mindestquote 5 %" in hinweise[0]


def test_cashquote_nahe_dem_mindestwert_oder_zu_wenige_tage_ohne_hinweis(projekt):
    portfolio("ausgewogen")
    nav(projekt, "ausgewogen", ["0.08"] * 5)  # 8 % bei 5 % Mindestquote: nahe genug
    assert texte() == []
    nav(projekt, "ausgewogen", ["0.90"] * 4)  # nur vier Handelstage: noch kein Urteil
    assert texte() == []
    nav(projekt, "ausgewogen", ["0.90", "0.90", "0.90", "0.90", "0.04"])  # Durchschnitt zählt, 5 Tage: 72 %
    assert len(texte()) == 1
