"""Umbau v2, Punkt 4: Daueranweisung und Overnight-Zyklus (Kauf zum Schlusskurs, Verkauf zur Eröffnung)."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

import ausfuehrung
import bewertung
import daueranweisung
import gemeinsam as g
import pruefe
from helfer import journal, laden, portfolio, sperre

P = "overnight"


def zeit(text):
    return datetime.fromisoformat(text).replace(tzinfo=g.TZ)


@pytest.fixture
def spiel(projekt, quelle, uhr):
    g.json_schreiben(g.spiel_pfad(), {"startdatum": "2026-10-12"})
    quelle.konstant("EUNL.DE", "2026-09-20", "2027-01-31", "100")
    quelle.konstant("EURUSD=X", "2026-09-20", "2027-01-31", "1.10")
    return projekt


def anlegen(tag, **felder):
    """Overnight-Portfolio, in dem alle Tage bis gestern verbucht sind."""
    from datetime import date, timedelta

    gestern = (date.fromisoformat(tag) - timedelta(days=1)).isoformat()
    return portfolio(profil=P, startdatum="2026-10-12", verarbeitet_bis=gestern, **felder)


def verarbeitet(tag):
    """Die nächtliche Nachbuchung hat alle Tage bis gestern verbucht (hier nur der Stand im Portfolio)."""
    from datetime import date, timedelta

    p = laden(P)
    p["verarbeitet_bis"] = (date.fromisoformat(tag) - timedelta(days=1)).isoformat()
    g.portfolio_speichern(p)


def setzen(spiel, uhr, tag, *extra, journal_id=None, gueltig_bis="2026-12-31", instrument="etf:EUNL.DE:1.0", stunde="10:00"):
    """Eine Session setzt die Daueranweisung (mit Journal-Eintrag und Sperre) und endet."""
    datum = tag.replace("-", "")
    journal_id = journal_id or f"J-{datum}-01"
    uhr.stellen(f"{tag}T{stunde}")
    journal(spiel, datum=tag, eintraege=(("01", "09:55", P, "EUNL.DE Daueranweisung"),))
    sperre(spiel, start=g.iso(uhr() - timedelta(minutes=10)))
    code = daueranweisung.main(["setzen", "--profil", P, "--journal-id", journal_id, "--gueltig-bis", gueltig_bis,
                                "--instrument", instrument, *extra])
    (spiel / "session.lock").unlink(missing_ok=True)
    return code


def trades(aktion=None):
    return [z for z in g.trades_lesen(P) if aktion is None or z["aktion"] == aktion]


def kurs_nach_schluss(quelle, uhr, tag, wert, uhrzeit="17:36", quellzeit="17:35"):
    uhr.stellen(f"{tag}T{uhrzeit}:00")
    quelle.kurs("EUNL.DE", wert, zeit(f"{tag}T{quellzeit}:00"))


def kurs_nach_oeffnung(quelle, uhr, tag, wert, uhrzeit="09:03", quellzeit="09:01"):
    uhr.stellen(f"{tag}T{uhrzeit}:00")
    quelle.kurs("EUNL.DE", wert, zeit(f"{tag}T{quellzeit}:00"))


def fehler():
    return [b for b in pruefe.alle_pruefungen() if b.stufe == "FEHLER"]


# --------------------------------------------------------------------------


def test_setzen_prueft_limits_schreibt_protokoll_und_trade(spiel, quelle, uhr, capsys):
    anlegen("2026-10-16")
    quelle.kurs("EUNL.DE", "100")
    assert setzen(spiel, uhr, "2026-10-16", "--nur-pruefen") == 0
    assert laden(P).get("daueranweisung") is None  # Trockenlauf ändert nichts
    assert setzen(spiel, uhr, "2026-10-16") == 0
    plan = laden(P)["daueranweisung"]
    assert plan["id"] == "D-0001" and plan["status"] == "aktiv" and plan["gueltig_bis"] == "2026-12-31"
    assert plan["instrumente"][0]["ticker"] == "EUNL.DE" and plan["aussetzen"]["ab_drawdown_stufe"] == 1
    z = trades("aenderung")[0]
    assert z["journal_id"] == "J-20261016-01" and z["bemerkung"].startswith("Daueranweisung D-0001 gesetzt")
    protokoll = daueranweisung.protokoll_lesen(P)
    assert protokoll[0]["ereignis"] == "gesetzt" and protokoll[0]["journal_id"] == "J-20261016-01"
    assert fehler() == []


def test_setzen_lehnt_ab_was_die_limits_verletzt_oder_nicht_zum_profil_passt(spiel, quelle, uhr, capsys):
    anlegen("2026-10-16")
    quelle.kurs("EUNL.DE", "100")
    # Risiko je Trade: 97 % Einsatz mit 20 % Stop-Abstand
    assert setzen(spiel, uhr, "2026-10-16", "--stop-abstand", "0.2") == 1
    assert "Risiko je Trade" in capsys.readouterr().err
    assert laden(P).get("daueranweisung") is None
    # Gültigkeit über das Maximum, Profil ohne Zyklus
    assert setzen(spiel, uhr, "2026-10-16", gueltig_bis="2027-12-31") == 2
    portfolio(profil="defensiv", verarbeitet_bis="2026-10-15")
    uhr.stellen("2026-10-16T10:00:00")
    sperre(spiel, start="2026-10-16T09:50:00+02:00")
    with pytest.raises(SystemExit):  # nur Profile mit Zyklus sind wählbar
        daueranweisung.main(["beenden", "--profil", "defensiv", "--journal-id", "J-20261016-01"])
    # ohne Session-Sperre keine Anweisung
    (spiel / "session.lock").unlink(missing_ok=True)
    assert daueranweisung.main(["setzen", "--profil", P, "--journal-id", "J-20261016-01", "--gueltig-bis", "2026-12-31",
                                "--instrument", "etf:EUNL.DE:1.0"]) == 2


def test_wochenendzyklus_kauf_freitag_zum_schluss_verkauf_montag_zur_eroeffnung(spiel, quelle, uhr):
    anlegen("2026-10-16")
    quelle.kurs("EUNL.DE", "100")
    assert setzen(spiel, uhr, "2026-10-16") == 0
    # vor dem Schlusskurs: nichts
    uhr.stellen("2026-10-16T17:32:00")
    quelle.kurs("EUNL.DE", "100.5", zeit("2026-10-16T17:31:00"))
    assert ausfuehrung.tick("schluss")["ausgefuehrt"] == []
    # Quelle liefert den Schlusskurs noch nicht (Kurs vor dem Schluss), dann kommt er
    uhr.stellen("2026-10-16T17:36:00")
    quelle.kurs("EUNL.DE", "100.5", zeit("2026-10-16T17:20:00"))
    bericht = ausfuehrung.tick("schlusskurs")
    assert bericht["ausgefuehrt"] == [] and bericht["wiederholen"]
    # Minutenkerze: Beginn der letzten Minute 17:29 (Kurs zum Schluss 17:30) zählt als Schlusskurs
    kurs_nach_schluss(quelle, uhr, "2026-10-16", "101", quellzeit="17:29")
    bericht = ausfuehrung.tick("schlusskurs")
    assert [a["aktion"] for a in bericht["ausgefuehrt"]] == ["kauf"]
    kauf = trades("kauf")[0]
    assert kauf["bemerkung"].startswith("automatisch (Auslöser: Daueranweisung): D-0001 Kauf zum Schlusskurs 101")
    assert kauf["kursquelle"] == "kurse" and kauf["journal_id"] == "J-20261016-01" and kauf["kurs_basiswert"] == "101.000000"
    p = laden(P)
    position = p["positionen"][0]
    assert position["daueranweisung"] == "D-0001" and position["zyklus"] == "2026-10-16"
    assert Decimal(p["cash"]) < Decimal("40") and p["offene_orders"] == []  # rund 97 % investiert, Cash-Quote >= 2 %
    # kein zweiter Kauf am selben Tag
    uhr.stellen("2026-10-16T17:45:00")
    assert ausfuehrung.tick()["ausgefuehrt"] == []
    assert len(trades("kauf")) == 1
    # Wochenende: nichts; Samstag/Sonntag verbucht die Nachbuchung nur Tage
    uhr.stellen("2026-10-17T12:00:00")
    assert ausfuehrung.tick()["ausgefuehrt"] == []
    verarbeitet("2026-10-19")
    # Montag zur Eröffnung: Quelle noch vor der Eröffnung, dann der erste Kurs danach
    uhr.stellen("2026-10-19T09:01:00")
    quelle.kurs("EUNL.DE", "100.7", zeit("2026-10-19T08:46:00"))
    assert ausfuehrung.tick("eroeffnung")["ausgefuehrt"] == []
    kurs_nach_oeffnung(quelle, uhr, "2026-10-19", "99.5", "09:17", "09:02")
    bericht = ausfuehrung.tick()
    assert [a["aktion"] for a in bericht["ausgefuehrt"]] == ["verkauf"]
    verkauf = trades("verkauf")[0]
    assert verkauf["grund"] == "order" and verkauf["bemerkung"].startswith(
        "automatisch (Auslöser: Daueranweisung): D-0001 Verkauf zur Eröffnung") and verkauf["journal_id"] == "J-20261016-01"
    p = laden(P)
    assert p["positionen"] == []
    plan = p["daueranweisung"]
    assert plan["naechte"] == 1 and plan["verlustnaechte_in_folge"] == 1 and Decimal(plan["ergebnis_eur"]) < 0
    assert plan["zyklen"][0]["abgerechnet"] and plan["status"] == "aktiv"
    # Montag zum Schluss geht es weiter (Dienstag ist ein Handelstag: kurze Nacht, kein Filter)
    kurs_nach_schluss(quelle, uhr, "2026-10-19", "99.9")
    assert [a["aktion"] for a in ausfuehrung.tick("schlusskurs")["ausgefuehrt"]] == ["kauf"]
    assert fehler() == []


def test_feiertagszyklus_weihnachten_ueber_vier_naechte(spiel, quelle, uhr):
    anlegen("2026-12-23")
    quelle.kurs("EUNL.DE", "100")
    assert setzen(spiel, uhr, "2026-12-23", gueltig_bis="2027-01-15") == 0
    kurs_nach_schluss(quelle, uhr, "2026-12-23", "100.2")
    assert len(ausfuehrung.tick("schlusskurs")["ausgefuehrt"]) == 1
    for tag in ("2026-12-24", "2026-12-25", "2026-12-26", "2026-12-27"):  # Feiertage und Wochenende
        uhr.stellen(f"{tag}T10:00:00")
        quelle.kurs("EUNL.DE", "100.9", zeit(f"{tag}T10:00:00"))
        assert ausfuehrung.tick()["ausgefuehrt"] == []
    assert len(laden(P)["positionen"]) == 1
    verarbeitet("2026-12-28")
    kurs_nach_oeffnung(quelle, uhr, "2026-12-28", "101.1", "09:05", "09:01")
    assert [a["aktion"] for a in ausfuehrung.tick("eroeffnung")["ausgefuehrt"]] == ["verkauf"]
    assert laden(P)["positionen"] == []
    # am 24.12. und 25.12. kein Kauf (Xetra geschlossen), der 28.12. ist wieder Handelstag
    uhr.stellen("2026-12-24T17:40:00")
    quelle.kurs("EUNL.DE", "101", zeit("2026-12-24T17:36:00"))
    assert ausfuehrung.tick("schlusskurs")["ausgefuehrt"] == []


def test_nur_lange_naechte_kauft_nicht_vor_einem_normalen_handelstag(spiel, quelle, uhr):
    anlegen("2026-10-14")
    quelle.kurs("EUNL.DE", "100")
    assert setzen(spiel, uhr, "2026-10-14", "--nur-lange-naechte") == 0
    kurs_nach_schluss(quelle, uhr, "2026-10-14", "100")  # Mittwoch: Donnerstag ist Handelstag
    assert ausfuehrung.tick("schlusskurs")["ausgefuehrt"] == []
    verarbeitet("2026-10-16")
    kurs_nach_schluss(quelle, uhr, "2026-10-16", "100")  # Freitag: bis Montag
    assert len(ausfuehrung.tick("schlusskurs")["ausgefuehrt"]) == 1


def test_ohne_gueltige_anweisung_geschieht_nichts(spiel, quelle, uhr):
    anlegen("2026-10-16")
    uhr.stellen("2026-10-16T17:40:00")
    quelle.kurs("EUNL.DE", "100", zeit("2026-10-16T17:36:00"))
    bericht = ausfuehrung.tick("schlusskurs")
    assert bericht["ausgefuehrt"] == [] and trades() == []
    # abgelaufen
    quelle.kurs("EUNL.DE", "100")
    assert setzen(spiel, uhr, "2026-10-16", gueltig_bis="2026-10-16") == 0
    kurs_nach_schluss(quelle, uhr, "2026-10-16", "100")
    assert len(ausfuehrung.tick("schlusskurs")["ausgefuehrt"]) == 1  # der letzte gültige Tag zählt
    verarbeitet("2026-10-19")
    kurs_nach_oeffnung(quelle, uhr, "2026-10-19", "100")
    ausfuehrung.tick()
    kurs_nach_schluss(quelle, uhr, "2026-10-19", "100")
    assert ausfuehrung.tick("schlusskurs")["ausgefuehrt"] == []
    assert laden(P)["daueranweisung"]["status"] == "abgelaufen"
    # beendete Anweisung: ebenfalls kein Kauf
    anlegen("2026-10-20")


def test_beenden_stoppt_den_kauf_aber_die_position_wird_zur_eroeffnung_verkauft(spiel, quelle, uhr):
    anlegen("2026-10-16")
    quelle.kurs("EUNL.DE", "100")
    assert setzen(spiel, uhr, "2026-10-16") == 0
    kurs_nach_schluss(quelle, uhr, "2026-10-16", "100")
    ausfuehrung.tick("schlusskurs")
    verarbeitet("2026-10-19")
    uhr.stellen("2026-10-19T08:30:00")
    journal(spiel, datum="2026-10-19", eintraege=(("01", "08:25", P, "EUNL.DE beenden"),))
    sperre(spiel, start="2026-10-19T08:20:00+02:00")
    assert daueranweisung.main(["beenden", "--profil", P, "--journal-id", "J-20261019-01"]) == 0
    (spiel / "session.lock").unlink()
    assert laden(P)["daueranweisung"]["status"] == "beendet"
    kurs_nach_oeffnung(quelle, uhr, "2026-10-19", "100.4")
    assert [a["aktion"] for a in ausfuehrung.tick()["ausgefuehrt"]] == ["verkauf"]
    kurs_nach_schluss(quelle, uhr, "2026-10-19", "100.4")
    assert ausfuehrung.tick("schlusskurs")["ausgefuehrt"] == []


def test_aussetzen_nach_verlustserie_und_bei_drawdown_stufe(spiel, quelle, uhr):
    anlegen("2026-10-16")
    quelle.kurs("EUNL.DE", "100")
    assert setzen(spiel, uhr, "2026-10-16", "--aussetzen-verluste", "1") == 0
    kurs_nach_schluss(quelle, uhr, "2026-10-16", "100")
    ausfuehrung.tick("schlusskurs")
    verarbeitet("2026-10-19")
    kurs_nach_oeffnung(quelle, uhr, "2026-10-19", "99")
    ausfuehrung.tick()
    assert laden(P)["daueranweisung"]["verlustnaechte_in_folge"] == 1
    kurs_nach_schluss(quelle, uhr, "2026-10-19", "99")
    bericht = ausfuehrung.tick("schlusskurs")
    assert bericht["ausgefuehrt"] == []
    plan = laden(P)["daueranweisung"]
    assert plan["status"] == "ausgesetzt" and "Verlustnächte" in plan["status_grund"]
    assert any(z["ereignis"] == "ausgesetzt" for z in daueranweisung.protokoll_lesen(P))
    # Drawdown-Stufe
    anlegen("2026-10-22", stufe=1)
    quelle.kurs("EUNL.DE", "100")
    # ohne Anweisung ist Stufe 1 egal; mit Anweisung (Stufe 1 ist das Standardkriterium) wird ausgesetzt
    p = laden(P)
    p["drawdown_stufe"] = 0
    g.portfolio_speichern(p)
    assert setzen(spiel, uhr, "2026-10-22") == 0
    p = laden(P)
    p["drawdown_stufe"] = 1
    g.portfolio_speichern(p)
    kurs_nach_schluss(quelle, uhr, "2026-10-22", "100")
    assert ausfuehrung.tick("schlusskurs")["ausgefuehrt"] == []
    assert "Drawdown-Stufe 1" in laden(P)["daueranweisung"]["status_grund"]


def test_fortsetzen_nur_wenn_das_kriterium_nicht_mehr_gilt(spiel, quelle, uhr, capsys):
    anlegen("2026-10-16")
    quelle.kurs("EUNL.DE", "100")
    assert setzen(spiel, uhr, "2026-10-16") == 0
    p = laden(P)
    p["daueranweisung"]["status"], p["daueranweisung"]["status_grund"] = "ausgesetzt", "Test"
    p["drawdown_stufe"] = 1
    g.portfolio_speichern(p)
    uhr.stellen("2026-10-16T12:00:00")
    journal(spiel, datum="2026-10-16", eintraege=(("01", "09:55", P, "x"), ("02", "11:55", P, "y")))
    sperre(spiel, start="2026-10-16T11:50:00+02:00")
    assert daueranweisung.main(["fortsetzen", "--profil", P, "--journal-id", "J-20261016-02"]) == 2
    assert "Drawdown-Stufe" in capsys.readouterr().err
    p = laden(P)
    p["drawdown_stufe"] = 0
    g.portfolio_speichern(p)
    assert daueranweisung.main(["fortsetzen", "--profil", P, "--journal-id", "J-20261016-02"]) == 0
    assert laden(P)["daueranweisung"]["status"] == "aktiv"


def test_nachbuchung_verkauft_zum_eroeffnungskurs_wenn_kein_durchlauf_lief(spiel, quelle, uhr):
    anlegen("2026-10-16")
    quelle.kurs("EUNL.DE", "100")
    assert setzen(spiel, uhr, "2026-10-16") == 0
    kurs_nach_schluss(quelle, uhr, "2026-10-16", "100")
    ausfuehrung.tick("schlusskurs")
    # Freitagskerze mit tiefem Tief (vor dem Kauf): löst den Stop der nach Schluss gekauften Position nicht aus
    quelle.kerze("EUNL.DE", "2026-10-16", 100, 101, 80, 100)
    quelle.kerze("EUNL.DE", "2026-10-19", 99, 100, 98, 99.5)
    uhr.stellen("2026-10-20T00:30:00")
    sperre(spiel, start="2026-10-20T00:29:00+02:00")
    assert bewertung.main(["nachbuchen"]) == 0
    p = laden(P)
    assert p["positionen"] == []
    verkauf = trades("verkauf")[0]
    assert verkauf["kursquelle"] == "historie:open" and verkauf["kurs_basiswert"] == "99.000000"
    assert verkauf["grund"] == "order" and "Daueranweisung D-0001" in verkauf["bemerkung"]
    assert [z for z in trades() if z["grund"] == "stop"] == []
    # der nächste Durchlauf rechnet die Nacht ab
    (spiel / "session.lock").unlink()
    kurs_nach_oeffnung(quelle, uhr, "2026-10-20", "99.5")
    ausfuehrung.tick()
    assert laden(P)["daueranweisung"]["naechte"] == 1
    assert fehler() == []


def test_pruefung_meldet_kaeufe_ohne_oder_nach_ablauf_der_anweisung(spiel, quelle, uhr):
    anlegen("2026-10-16")
    quelle.kurs("EUNL.DE", "100")
    assert setzen(spiel, uhr, "2026-10-16", gueltig_bis="2026-10-16") == 0
    p = laden(P)
    lauf = g.Buchungslauf(p)
    lauf.trade(zeit=zeit("2026-10-19T17:40:00"), position_id="P-0099", aktion="kauf", basiswert="EUNL.DE", ticker="EUNL.DE",
               kursquelle="kurse", kurs_zeit="2026-10-19T17:40:00+02:00", journal_id="J-20261016-01", grund="order",
               bemerkung=g.automatisch_text("Daueranweisung", "D-0001 Kauf zum Schlusskurs"))
    lauf.trade(zeit=zeit("2026-10-19T17:41:00"), position_id="P-0098", aktion="kauf", basiswert="EUNL.DE", ticker="EUNL.DE",
               kursquelle="kurse", kurs_zeit="2026-10-19T17:41:00+02:00", journal_id="J-20261016-01", grund="order",
               bemerkung=g.automatisch_text("Daueranweisung", "D-0007 Kauf zum Schlusskurs"))
    lauf.speichern()
    texte = [b.text for b in pruefe.pruefe_daueranweisung(P)]
    assert any("nach Ablauf der Daueranweisung D-0001" in t for t in texte)
    assert any("D-0007" in t and "keine Daueranweisung" in t for t in texte)


def test_anweisung_nach_dem_schlusskurs_kauft_erst_am_naechsten_tag(spiel, quelle, uhr):
    anlegen("2026-10-16")
    quelle.kurs("EUNL.DE", "100")
    assert setzen(spiel, uhr, "2026-10-16", stunde="17:50") == 0  # erfasst nach dem Schluss von Freitag
    kurs_nach_schluss(quelle, uhr, "2026-10-16", "100", uhrzeit="17:52", quellzeit="17:35")
    assert ausfuehrung.tick("schlusskurs")["ausgefuehrt"] == []  # der Schlusskurs lag vor der Erfassung
    verarbeitet("2026-10-19")
    kurs_nach_schluss(quelle, uhr, "2026-10-19", "100")
    assert len(ausfuehrung.tick("schlusskurs")["ausgefuehrt"]) == 1


def test_gleichzeitige_durchlaeufe_kaufen_je_nacht_nur_einmal(spiel, quelle, uhr):
    import threading

    anlegen("2026-10-16")
    quelle.kurs("EUNL.DE", "100")
    assert setzen(spiel, uhr, "2026-10-16") == 0
    kurs_nach_schluss(quelle, uhr, "2026-10-16", "100")
    ergebnisse = []
    threads = [threading.Thread(target=lambda: ergebnisse.append(ausfuehrung.tick("schlusskurs"))) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(len(b["ausgefuehrt"]) for b in ergebnisse) == 1 and len(trades("kauf")) == 1
    assert fehler() == []
