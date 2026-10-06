"""AP9: Szenario-Tests mit gemockten Tagesdaten (regeln.md Abschnitte 2, 4, 6, 7, 8)."""

from decimal import Decimal

import pytest

import bewertung
import buchen
import gemeinsam as g
import pruefe
from helfer import aktie, git_commit, git_init, journal, laden, portfolio, sperre

C = Decimal("0.02") / 365


@pytest.fixture
def spiel(projekt, quelle, uhr):
    quelle.konstant("EUNL.DE", "2026-09-20", "2026-10-31", "100")
    quelle.konstant("EURUSD=X", "2026-09-20", "2026-10-31", "1.10")
    return projekt


def session(projekt, uhr, zeit, person="auftraggeber-a"):
    uhr.stellen(zeit)
    sperre(projekt, person=person, start=g.iso(uhr()))


def kaufen(profil, typ, basiswert, einsatz, stop, kursziel="keiner", journal_id="J-20261012-01", **extra):
    argv = ["kaufen", "--profil", profil, "--typ", typ, "--einsatz", str(einsatz), "--stop", str(stop),
            "--kursziel", str(kursziel), "--journal-id", journal_id]
    argv += ["--ticker", basiswert] if typ in ("aktie", "etf") else ["--basiswert", basiswert]
    for schluessel, wert in extra.items():
        argv += [f"--{schluessel}", str(wert)]
    return buchen.main(argv)


def aktionen(profil):
    return [(z["aktion"], z["grund"]) for z in g.trades_lesen(profil) if z["aktion"] != "zins"]


def test_1_knockout_long_durch_kursluecke_bei_eroeffnung(spiel, quelle, uhr):
    portfolio(profil="aggressiv")
    journal(spiel, eintraege=(("01", "10:00", "aggressiv", "DAX KO Long"),))
    session(spiel, uhr, "2026-10-12T10:05:00")
    quelle.kurs("^GDAXI", "20000")
    quelle.kerze("^GDAXI", "2026-10-12", 20000, 20100, 19900, 20000)
    quelle.kerze("^GDAXI", "2026-10-13", 15500, 15800, 15400, 15600)  # Lücke unter die Barriere
    assert kaufen("aggressiv", "ko", "^GDAXI", 100, 19500, hebel=5) == 0
    cash_nach_kauf = Decimal(laden("aggressiv")["cash"])
    session(spiel, uhr, "2026-10-14T10:00:00")
    assert bewertung.main(["nachbuchen"]) == 0
    p = laden("aggressiv")
    assert p["positionen"] == []
    ko = [z for z in g.trades_lesen("aggressiv") if z["aktion"] == "knockout"][0]
    assert ko["grund"] == "knockout" and ko["kursquelle"] == "historie:open"
    assert ko["kurs_basiswert"] == "15500.000000" and ko["betrag_eur"] == "0.00"
    zinsen = sum(Decimal(z["betrag_eur"]) for z in g.trades_lesen("aggressiv") if z["aktion"] == "zins")
    assert Decimal(p["cash"]) == cash_nach_kauf + zinsen


def test_2_stop_und_kursziel_am_selben_tag_stop_gilt(spiel, quelle, uhr):
    portfolio()
    journal(spiel)
    session(spiel, uhr, "2026-10-12T10:05:00")
    quelle.kurs("SAP.DE", "200")
    quelle.kerze("SAP.DE", "2026-10-12", 200)
    quelle.kerze("SAP.DE", "2026-10-13", 200, 215, 185, 205)  # Kursziel 210 und Stop 190 berührt
    assert kaufen("ausgewogen", "aktie", "SAP.DE", 200, 190, 210) == 0
    session(spiel, uhr, "2026-10-14T10:00:00")
    assert bewertung.main(["nachbuchen"]) == 0
    verkauf = [z for z in g.trades_lesen("ausgewogen") if z["aktion"] == "verkauf"][0]
    assert verkauf["grund"] == "stop" and Decimal(verkauf["kurs_basiswert"]) == 190
    assert verkauf["kursquelle"] == "historie:intraday"
    assert Decimal(verkauf["kurs"]) == Decimal("190") * Decimal("0.9995")


def test_3_market_order_am_abend_zum_naechsten_eroeffnungskurs(spiel, quelle, uhr):
    portfolio()
    journal(spiel, eintraege=(("01", "18:55", "ausgewogen", "SAP.DE"),))
    session(spiel, uhr, "2026-10-12T19:00:00")
    quelle.kurs("SAP.DE", "200", zeit=uhr())
    quelle.kerze("SAP.DE", "2026-10-12", 198, 201, 197, 200)
    quelle.kerze("SAP.DE", "2026-10-13", 205, 207, 204, 206)
    assert kaufen("ausgewogen", "aktie", "SAP.DE", 200, 195) == 0
    assert laden()["positionen"] == []
    session(spiel, uhr, "2026-10-14T10:00:00")
    assert bewertung.main(["nachbuchen"]) == 0
    position = laden()["positionen"][0]
    assert position["eroeffnet"] == "2026-10-13T09:00:00+02:00"
    assert Decimal(position["einstand"]) == Decimal("205") * Decimal("1.0005")
    kauf = [z for z in g.trades_lesen("ausgewogen") if z["aktion"] == "kauf"][0]
    assert kauf["kursquelle"] == "historie:open" and kauf["kurs_zeit"] == "2026-10-13"
    assert aktionen("ausgewogen") == [("vormerkung", "order"), ("kauf", "order")]


def test_4_cash_zins_ueber_ein_wochenende(spiel, uhr):
    portfolio(verarbeitet_bis="2026-10-08", startdatum="2026-10-09", cash="10000.00")
    session(spiel, uhr, "2026-10-13T10:00:00")
    assert bewertung.main(["nachbuchen"]) == 0
    zinsen = [z for z in g.trades_lesen("ausgewogen") if z["aktion"] == "zins"]
    assert [z["bemerkung"][-10:] for z in zinsen] == ["2026-10-09", "2026-10-10", "2026-10-11", "2026-10-12"]
    # 10000 * 0,02/365 = 0,548 -> 0,55; danach jeweils auf dem neuen Endbestand
    erwartet, cash = [], Decimal("10000.00")
    for _ in range(4):
        z = (cash * C).quantize(Decimal("0.01"))
        erwartet.append(z)
        cash += z
    assert [Decimal(z["betrag_eur"]) for z in zinsen] == erwartet
    nav = bewertung.nav_lesen("ausgewogen")
    assert [z["datum"] for z in nav] == ["2026-10-09", "2026-10-12"]
    # Montag enthält Zins für Freitag bis Montag; Sa und So (drei Kalendertage Fr-So) sind enthalten
    assert Decimal(nav[1]["portfoliowert"]) - Decimal(nav[0]["portfoliowert"]) == sum(erwartet[1:])


def test_5_order_verletzt_exposure_limit(spiel, quelle, uhr, capsys):
    portfolio(profil="defensiv", cash="100.00", positionen=[aktie("P-0001", "SAP.DE", "9", stop="80")])
    journal(spiel, eintraege=(("01", "10:00", "defensiv", "DAX Faktor"),))
    session(spiel, uhr, "2026-10-12T10:05:00")
    quelle.kurs("SAP.DE", "100")
    quelle.kurs("^GDAXI", "20000")
    assert kaufen("defensiv", "faktor", "^GDAXI", 100, 19990, faktor=3) == 1
    fehler = capsys.readouterr().err
    assert "Gesamt-Exposure: Grenzwert 1.20x, Istwert 1.21x" in fehler
    assert laden("defensiv")["positionen"][0]["id"] == "P-0001" and len(laden("defensiv")["positionen"]) == 1
    assert g.trades_lesen("defensiv") == []


def test_5b_vorgemerkte_order_verfaellt_bei_limitverstoss(spiel, quelle, uhr):
    portfolio(profil="defensiv")
    journal(spiel, eintraege=(("01", "18:00", "defensiv", "SAP.DE"),))
    session(spiel, uhr, "2026-10-12T19:00:00")
    quelle.kurs("SAP.DE", "100", zeit=uhr())
    quelle.kerze("SAP.DE", "2026-10-12", 100)
    quelle.kerze("SAP.DE", "2026-10-13", 96, 97, 95.5, 96)  # Eröffnung nahe am Stop -> Risiko passt noch
    assert kaufen("defensiv", "aktie", "SAP.DE", 150, 95) == 0
    session(spiel, uhr, "2026-10-14T10:00:00")
    assert bewertung.main(["nachbuchen"]) == 0
    assert aktionen("defensiv")[-1] == ("kauf", "order")
    # Gegenprobe: Lücke unter den Stop -> Stop über Kurs -> Order verfällt mit Vermerk
    portfolio(profil="aggressiv")
    journal(spiel, datum="2026-10-14", eintraege=(("01", "18:00", "aggressiv", "ALV.DE"),))
    session(spiel, uhr, "2026-10-14T19:00:00")
    quelle.kurs("ALV.DE", "300", zeit=uhr())
    quelle.kerze("ALV.DE", "2026-10-15", 280, 285, 279, 281)
    p = laden("aggressiv")
    p["verarbeitet_bis"] = "2026-10-13"
    g.portfolio_speichern(p)
    assert kaufen("aggressiv", "aktie", "ALV.DE", 150, 290, journal_id="J-20261014-01") == 0
    session(spiel, uhr, "2026-10-16T10:00:00")
    assert bewertung.main(["nachbuchen"]) == 0
    verfall = [z for z in g.trades_lesen("aggressiv") if z["aktion"] == "verfall"][0]
    assert "Stop" in verfall["bemerkung"] and laden("aggressiv")["offene_orders"] == []


def test_6_nachtraeglich_geaenderte_zeile_in_trades_wird_erkannt(spiel, quelle, uhr, capsys):
    portfolio()
    journal(spiel)
    session(spiel, uhr, "2026-10-12T10:05:00")
    quelle.kurs("SAP.DE", "200")
    assert kaufen("ausgewogen", "aktie", "SAP.DE", 200, 190, 230) == 0
    git_init(spiel)
    assert pruefe.main([]) == 0
    datei = spiel / "trades" / "ausgewogen.csv"
    zeilen = datei.read_text().splitlines()
    zeilen[1] = zeilen[1].replace("J-20261012-01", "J-20261012-02")  # nachträglich umgeschrieben
    datei.write_text("\n".join(zeilen) + "\n")
    capsys.readouterr()
    assert pruefe.main([]) == 1
    ausgabe = capsys.readouterr().out
    assert "FEHLER [Nur anhängen] trades/ausgewogen.csv" in ausgabe
    # auch wenn die Änderung bereits committet wurde (GitHub Action prüft die Historie)
    git_commit(spiel, "manipuliert")
    assert pruefe.main([]) == 1  # Journal-Bezug fehlt jetzt ebenfalls
    assert pruefe.main(["--historie"]) == 1
    assert "trades/ausgewogen.csv: in Commit" in capsys.readouterr().out


def test_7_drawdown_stufe_2_zertifikate_abgelehnt_aktien_erlaubt(spiel, quelle, uhr, capsys):
    portfolio(cash="780.00", hoechststand="1000.00")
    journal(spiel, datum="2026-10-13", eintraege=(("01", "10:00", "ausgewogen", "DAX KO"),
                                                  ("02", "10:01", "ausgewogen", "SAP.DE")))
    session(spiel, uhr, "2026-10-13T10:05:00")
    assert bewertung.main(["nachbuchen"]) == 0
    assert "Pflicht-Review" in capsys.readouterr().out
    p = laden()
    assert p["drawdown_stufe"] == 2 and p["stufe2_seit"] == "2026-10-12"
    quelle.kurs("^GDAXI", "20000")
    quelle.kurs("SAP.DE", "200")
    assert kaufen("ausgewogen", "ko", "^GDAXI", 100, 19900, hebel=2, journal_id="J-20261013-01") == 1
    assert "Drawdown-Stufe 2: Grenzwert keine neuen Zertifikate, Istwert Stufe 2" in capsys.readouterr().err
    # Aktie mit kleinem Risiko (Stufe >= 1: Risiko halbiert auf 1 %)
    assert kaufen("ausgewogen", "aktie", "SAP.DE", 100, 196, journal_id="J-20261013-02") == 0
    assert len(laden()["positionen"]) == 1


def test_8_dividende_und_split_auf_aktienposition(spiel, quelle, uhr):
    position = aktie("P-0001", "AAPL", "2", einstand="180", stop="150", kursziel="300")
    portfolio(cash="600.00", positionen=[position])
    quelle.kerze("AAPL", "2026-10-12", 220, 222, 219, 221)
    quelle.kerze("AAPL", "2026-10-13", 221, 223, 220, 222, dividende="0.26")
    quelle.kerze("AAPL", "2026-10-14", 56, 57, 55, 56, split=4)
    session(spiel, uhr, "2026-10-15T10:00:00")
    assert bewertung.main(["nachbuchen"]) == 0
    zeilen = g.trades_lesen("ausgewogen")
    dividende = [z for z in zeilen if z["aktion"] == "dividende"][0]
    assert Decimal(dividende["betrag_eur"]) == (2 * Decimal("0.26") / Decimal("1.10")).quantize(Decimal("0.01"))
    assert Decimal(dividende["devisenkurs"]) == Decimal("1.1") and dividende["kurs_zeit"] == "2026-10-13"
    split = [z for z in zeilen if z["aktion"] == "split"][0]
    assert split["stueck"] == "8.000000" and split["kurs_zeit"] == "2026-10-14"
    p = laden()["positionen"][0]
    assert p["stueck"] == "8.000000"
    assert Decimal(p["stop"]) == Decimal("37.5") and Decimal(p["kursziel"]) == Decimal("75")
    assert Decimal(p["einstand"]) == Decimal("45")
    # Kein Stop ausgelöst, obwohl der Kurs nominal unter den alten Stop fällt
    assert not any(z["aktion"] == "verkauf" for z in zeilen)
    nav = bewertung.nav_lesen("ausgewogen")
    assert Decimal(nav[-1]["positionswert"]) == (8 * Decimal("56") / Decimal("1.10")).quantize(Decimal("0.01"))


def test_9_faktor_zertifikat_in_seitwaertsphase(spiel, quelle, uhr):
    portfolio(profil="aggressiv", verarbeitet_bis="2026-10-11")
    journal(spiel, datum="2026-10-11", eintraege=(("01", "18:00", "aggressiv", "DAX Faktor 3"),))
    session(spiel, uhr, "2026-10-11T19:00:00")
    quelle.kurs("^GDAXI", "20000", zeit=uhr())
    kurse_tage = {"2026-10-12": 20000, "2026-10-13": 21000, "2026-10-14": 20000, "2026-10-15": 21000,
                  "2026-10-16": 20000, "2026-10-19": 21000, "2026-10-20": 20000}
    for tag, wert in kurse_tage.items():
        quelle.kerze("^GDAXI", tag, wert)
    p = laden("aggressiv")
    p["startdatum"] = "2026-10-11"
    g.portfolio_speichern(p)
    assert kaufen("aggressiv", "faktor", "^GDAXI", 150, 18000, faktor=3, journal_id="J-20261011-01") == 0
    session(spiel, uhr, "2026-10-21T10:00:00")
    assert bewertung.main(["nachbuchen"]) == 0
    position = laden("aggressiv")["positionen"][0]
    wert = Decimal(position["parameter"]["wert_je_stueck"])
    # Erwartung exakt nach Formel: Kosten je Kalendertag, Rendite Schluss zu Schluss
    erwartet, vorher, stand = Decimal("100"), Decimal("20000"), 11
    for tag, kurs in kurse_tage.items():
        heute = int(tag[-2:])
        r = Decimal(kurs) / vorher - 1
        erwartet = (erwartet * max(Decimal(0), 1 + 3 * r - C * (heute - stand))).quantize(Decimal("1e-8"))
        vorher, stand = Decimal(kurs), heute
    assert wert == erwartet
    # Basiswert unverändert, Faktor-Effekt (Volatilitätsverlust) deutlich größer als die Kosten
    assert kurse_tage["2026-10-20"] == 20000
    assert wert < Decimal("100") * (1 - 9 * C) - Decimal("1")


def test_10_portfolio_faellt_unter_200_eur(spiel, quelle, uhr):
    portfolio(profil="aggressiv", cash="50.00", positionen=[aktie("P-0001", "XYZ.DE", "9.5")])
    quelle.kerze("XYZ.DE", "2026-10-12", 100, 100, 14, 15)
    quelle.kerze("XYZ.DE", "2026-10-13", 15)
    session(spiel, uhr, "2026-10-14T10:00:00")
    assert bewertung.main(["nachbuchen"]) == 0
    p = laden("aggressiv")
    assert p["status"] == "geschlossen" and p["positionen"] == []
    verkauf = [z for z in g.trades_lesen("aggressiv") if z["aktion"] == "verkauf"][0]
    assert verkauf["grund"] == "portfoliostopp" and Decimal(verkauf["kurs_basiswert"]) == 15
    erloes = (Decimal("9.5") * Decimal("15") * Decimal("0.9995")).quantize(Decimal("0.01"))
    assert Decimal(p["cash"]) == Decimal("50.00") + Decimal("0.00") + erloes - 1  # Zins vor Bewertung: 0,00
    nav = bewertung.nav_lesen("aggressiv")
    assert nav[-1]["status"] == "geschlossen"
    # Weitere Nachbuchungen ändern nichts mehr
    session(spiel, uhr, "2026-10-16T10:00:00")
    assert bewertung.main(["nachbuchen"]) == 0
    assert laden("aggressiv")["cash"] == p["cash"]
