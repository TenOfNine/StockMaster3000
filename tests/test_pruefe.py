"""AP7: Je Prüfung ein Test, der einen manipulierten Zustand erkennt."""

import json
from decimal import Decimal

import pytest

import bewertung
import buchen
import gemeinsam as g
import pruefe
from helfer import git_commit, git_init, journal, laden, portfolio, sperre


@pytest.fixture
def spielstand(projekt, quelle, uhr):
    """Gültiger Spielstand: Sofortkauf, Abendorder, Nachbuchung mit Stop-Verkauf."""
    quelle.konstant("EUNL.DE", "2026-09-20", "2026-10-31", "100")
    quelle.konstant("EURUSD=X", "2026-09-20", "2026-10-31", "1.10")
    portfolio()
    journal(projekt, eintraege=(("01", "10:00", "ausgewogen", "SAP.DE"), ("02", "22:50", "ausgewogen", "AAPL")))
    uhr.stellen("2026-10-12T10:05:00")
    sperre(projekt, start=g.iso(uhr()))
    quelle.kurs("SAP.DE", "200")
    quelle.kerze("SAP.DE", "2026-10-12", 200, 202, 198, 201)
    quelle.kerze("SAP.DE", "2026-10-13", 200, 201, 189, 195)
    assert buchen.main(["kaufen", "--profil", "ausgewogen", "--typ", "aktie", "--ticker", "SAP.DE",
                        "--einsatz", "200", "--stop", "190", "--kursziel", "230", "--journal-id", "J-20261012-01"]) == 0
    uhr.stellen("2026-10-12T23:00:00")
    sperre(projekt, start=g.iso(uhr()))
    quelle.kurs("AAPL", "220", zeit=uhr())
    quelle.kurs("EURUSD=X", "1.10", zeit=uhr())
    quelle.kerze("AAPL", "2026-10-13", 221, 222, 219, 220)
    assert buchen.main(["kaufen", "--profil", "ausgewogen", "--typ", "aktie", "--ticker", "AAPL",
                        "--einsatz", "150", "--stop", "200", "--kursziel", "260", "--journal-id", "J-20261012-02"]) == 0
    uhr.stellen("2026-10-14T10:00:00")
    sperre(projekt, start=g.iso(uhr()))
    assert bewertung.main(["nachbuchen"]) == 0
    aktionen = [z["aktion"] for z in g.trades_lesen("ausgewogen") if z["aktion"] != "zins"]
    assert aktionen == ["kauf", "vormerkung", "kauf", "verkauf"]
    return projekt


def befunde(funktion, *args):
    return [str(b) for b in funktion(*args) if b.stufe == "FEHLER"]


def test_gueltiger_stand_besteht(spielstand):
    git_init(spielstand)
    assert pruefe.main([]) == 0
    assert pruefe.main(["--historie"]) == 0


def test_nachrechnung_erkennt_manipuliertes_cash(spielstand):
    assert befunde(pruefe.pruefe_nachrechnung, "ausgewogen") == []
    p = laden()
    p["cash"] = str(Decimal(p["cash"]) + 100)
    g.portfolio_speichern(p)
    assert any("Cash im Portfolio" in b for b in befunde(pruefe.pruefe_nachrechnung, "ausgewogen"))


def test_nachrechnung_erkennt_manipulierte_stueckzahl(spielstand):
    p = laden()
    p["positionen"][0]["stueck"] = "5.000000"
    g.portfolio_speichern(p)
    assert any("Positionen im Portfolio" in b for b in befunde(pruefe.pruefe_nachrechnung, "ausgewogen"))


def test_nachrechnung_erkennt_falschen_betrag(spielstand):
    datei = spielstand / "trades" / "ausgewogen.csv"
    zeilen = g.csv_lesen(datei)
    zeilen[0]["kurs"] = "150"
    g.csv_schreiben(datei, g.TRADE_FELDER, zeilen)
    assert any("Stück x Kurs" in b for b in befunde(pruefe.pruefe_nachrechnung, "ausgewogen"))


def test_journal_fehlt_oder_zu_spaet(spielstand):
    assert befunde(pruefe.pruefe_journal, "ausgewogen") == []
    datei = spielstand / "journal" / "2026-10-12_auftraggeber-a.md"
    datei.write_text(datei.read_text().replace("2026-10-12 22:50", "2026-10-12 23:30"))
    assert any("nach der Order" in b for b in befunde(pruefe.pruefe_journal, "ausgewogen"))
    datei.write_text(datei.read_text().replace("J-20261012-01", "J-20261012-09"))
    assert any("J-20261012-01 fehlt" in b for b in befunde(pruefe.pruefe_journal, "ausgewogen"))


def test_kurs_nicht_belegt(spielstand):
    assert befunde(pruefe.pruefe_kurse, "ausgewogen") == []
    protokoll = spielstand / "data" / "kurse" / "2026-10-12.csv"
    protokoll.write_text(protokoll.read_text().replace("SAP.DE,200.000000", "SAP.DE,199.000000"))
    assert any("nicht in data/kurse" in b for b in befunde(pruefe.pruefe_kurse, "ausgewogen"))


def test_historienkurs_nicht_belegt(spielstand):
    historie = spielstand / "data" / "historie" / "SAP.DE.csv"
    historie.write_text(historie.read_text().replace("2026-10-13,200.000000,201.000000,189.000000",
                                                     "2026-10-13,200.000000,201.000000,191.000000"))
    assert any("passt nicht zur Tageskerze" in b for b in befunde(pruefe.pruefe_kurse, "ausgewogen"))


def test_limits_protokoll_fehlt_oder_verletzt(spielstand):
    assert befunde(pruefe.pruefe_limits, "ausgewogen") == []
    datei = spielstand / "data" / "limits" / "ausgewogen.jsonl"
    eintraege = [json.loads(z) for z in datei.read_text().splitlines()]
    eintraege[0]["kennzahlen"]["einzelposition"] = "0.40"
    datei.write_text("\n".join(json.dumps(e) for e in eintraege) + "\n")
    assert any("Einzelposition" in b for b in befunde(pruefe.pruefe_limits, "ausgewogen"))
    datei.write_text(json.dumps(eintraege[1]) + "\n")
    assert any("keine Limitprüfung" in b for b in befunde(pruefe.pruefe_limits, "ausgewogen"))


def test_config_weicht_von_regeln_ab(projekt):
    assert pruefe.pruefe_config_regeln() == []
    datei = projekt / "config" / "profile.json"
    daten = json.loads(datei.read_text())
    daten["profile"]["aggressiv"]["max_hebel"] = "12"
    datei.write_text(json.dumps(daten))
    fehler = befunde(pruefe.pruefe_config_regeln)
    assert fehler == ["FEHLER [Konfiguration] config/profile.json aggressiv.max_hebel = 12, regeln.md = 10."]


def test_regeln_geaendert_wird_erkannt(projekt):
    datei = projekt / "regeln.md"
    datei.write_text(datei.read_text().replace("| Mindest-Cashquote | 10 % |", "| Mindest-Cashquote | 5 % |"))
    assert any("defensiv.min_cashquote" in b for b in befunde(pruefe.pruefe_config_regeln))


def test_nur_anhaengen_gegenueber_letztem_commit(spielstand):
    git_init(spielstand)
    assert befunde(pruefe.pruefe_anhaengen) == []
    datei = spielstand / "journal" / "2026-10-12_auftraggeber-a.md"
    datei.write_text(datei.read_text().replace("These: Test", "These: geändert", 1))
    assert any("journal/2026-10-12_auftraggeber-a.md" in b for b in befunde(pruefe.pruefe_anhaengen))


def test_anhaengen_ist_erlaubt(spielstand):
    git_init(spielstand)
    datei = spielstand / "journal" / "2026-10-12_auftraggeber-a.md"
    datei.write_text(datei.read_text() + "\n### Nachtrag\n- Korrektur zu J-20261012-01\n")
    assert befunde(pruefe.pruefe_anhaengen) == []


def test_historie_erkennt_aenderung_in_frueherem_commit(spielstand):
    git_init(spielstand)
    datei = spielstand / "data" / "kurse" / "2026-10-12.csv"
    datei.write_text(datei.read_text().replace("200.000000", "201.000000"))
    git_commit(spielstand, "manipuliert")
    (spielstand / "lessons.md").write_text("neu")
    git_commit(spielstand, "harmlos")
    assert befunde(pruefe.pruefe_anhaengen) == []
    assert any("data/kurse/2026-10-12.csv" in b for b in befunde(pruefe.pruefe_anhaengen_historie))


def test_warnung_bei_verwaister_sperre(projekt, uhr):
    uhr.stellen("2026-10-12T20:00:00")
    sperre(projekt, start="2026-10-12T13:59:00+02:00")
    warnungen = pruefe.pruefe_sperre()
    assert len(warnungen) == 1 and warnungen[0].stufe == "WARNUNG" and "Verwaiste Sperre" in warnungen[0].text
    sperre(projekt, start="2026-10-12T14:01:00+02:00")
    assert pruefe.pruefe_sperre() == []


def test_rueckgabewert_bei_fehler(spielstand, capsys):
    git_init(spielstand)
    p = laden()
    p["cash"] = "5000.00"
    g.portfolio_speichern(p)
    assert pruefe.main([]) == 1
    assert "FEHLGESCHLAGEN" in capsys.readouterr().out
