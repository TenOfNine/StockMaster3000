"""Umbau v2, Punkt 5: Ausführung ohne Claude-Lauf (tools/ausfuehrung.py, Buchungssperre, Prüfungen)."""

import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import ausfuehrung
import bewertung
import buchen
import gemeinsam as g
import pruefe
from helfer import aktie, journal, laden, portfolio, sperre

WURZEL = Path(__file__).resolve().parent.parent


def zeit(text):
    return datetime.fromisoformat(text).replace(tzinfo=g.TZ)


@pytest.fixture
def spiel(projekt, quelle, uhr):
    g.json_schreiben(g.spiel_pfad(), {"startdatum": "2026-10-12"})
    quelle.konstant("EUNL.DE", "2026-09-20", "2026-10-31", "100")
    quelle.konstant("EURUSD=X", "2026-09-20", "2026-10-31", "1.10")
    return projekt


def kaufen(profil="ausgewogen", typ="aktie", basiswert="SAP.DE", einsatz=200, stop=190, kursziel="keiner",
           journal_id="J-20261011-01", **extra):
    argv = ["kaufen", "--profil", profil, "--typ", typ, "--einsatz", str(einsatz), "--stop", str(stop),
            "--kursziel", str(kursziel), "--journal-id", journal_id]
    argv += ["--ticker", basiswert] if typ in ("aktie", "etf") else ["--basiswert", basiswert]
    for schluessel, wert in extra.items():
        argv += [f"--{schluessel}", str(wert)]
    return buchen.main(argv)


def sonntagabend(spiel, quelle, uhr, profil="ausgewogen", **kaufargumente):
    """Sonntag 19:00: eine Session erfasst eine Kauforder (Markt geschlossen) und endet."""
    uhr.stellen("2026-10-11T19:00:00")
    portfolio(profil=profil)
    journal(spiel, datum="2026-10-11", eintraege=(("01", "18:55", profil, "SAP.DE"),))
    sperre(spiel, start="2026-10-11T18:50:00+02:00")
    quelle.kurs("SAP.DE", "200")
    quelle.kurs("^GDAXI", "20000")
    assert kaufen(profil=profil, **kaufargumente) == 0
    (spiel / "session.lock").unlink()
    return laden(profil)["offene_orders"][0]


def trades(profil="ausgewogen", aktion=None):
    return [z for z in g.trades_lesen(profil) if aktion is None or z["aktion"] == aktion]


def fehler_der_pruefung():
    return [b for b in pruefe.alle_pruefungen() if b.stufe == "FEHLER"]


# --------------------------------------------------------------------------
# Hauptszenario: Sonntagabend erfasst, Montag zur Eröffnung ohne Lauf ausgeführt


def test_sonntagabend_order_wird_montag_zur_eroeffnung_ohne_lauf_ausgefuehrt(spiel, quelle, uhr):
    order = sonntagabend(spiel, quelle, uhr)
    assert order["art"] == "market" and laden()["positionen"] == []
    uhr.stellen("2026-10-12T09:03:00")
    quelle.kurs("SAP.DE", "201", zeit("2026-10-12T09:01:00"))
    bericht = ausfuehrung.tick("eroeffnung")
    assert [a["aktion"] for a in bericht["ausgefuehrt"]] == ["kauf"]
    p = laden()
    assert p["offene_orders"] == [] and len(p["positionen"]) == 1
    kauf = trades(aktion="kauf")[0]
    assert kauf["bemerkung"].startswith("automatisch (Auslöser: Eröffnung)")
    assert kauf["journal_id"] == "J-20261011-01" and kauf["order_id"] == order["id"]
    assert kauf["kursquelle"] == "kurse" and kauf["kurs_basiswert"] == "201.000000"
    assert kauf["zeit"] == "2026-10-12T09:03:00+02:00"
    assert fehler_der_pruefung() == []
    # ein weiterer Tick bucht nichts mehr
    uhr.stellen("2026-10-12T09:08:00")
    assert ausfuehrung.tick()["ausgefuehrt"] == []
    assert len(trades(aktion="kauf")) == 1


def test_verpasstes_eroeffnungsfenster_ueberlaesst_die_order_der_nachbuchung(spiel, quelle, uhr):
    sonntagabend(spiel, quelle, uhr)
    uhr.stellen("2026-10-12T10:40:00")
    quelle.kurs("SAP.DE", "205")
    bericht = ausfuehrung.tick()
    assert bericht["ausgefuehrt"] == [] and any("Eröffnungsfenster" in u["text"] for u in bericht["uebersprungen"])
    assert len(laden()["offene_orders"]) == 1
    quelle.kerze("SAP.DE", "2026-10-12", 200, 206, 199, 204)
    uhr.stellen("2026-10-13T00:30:00")
    sperre(spiel, start="2026-10-13T00:29:00+02:00")
    assert bewertung.main(["nachbuchen"]) == 0
    kauf = trades(aktion="kauf")[0]
    assert kauf["kursquelle"] == "historie:open" and kauf["kurs_basiswert"] == "200.000000"
    assert len(laden()["positionen"]) == 1 and len(trades(aktion="kauf")) == 1


def test_kurs_vor_der_eroeffnung_und_ohne_kurs_wird_wiederholt(spiel, quelle, uhr):
    sonntagabend(spiel, quelle, uhr)
    uhr.stellen("2026-10-12T09:02:00")
    quelle.kurs("SAP.DE", "199", zeit("2026-10-12T08:55:00"))  # Quellzeit vor der Eröffnung
    bericht = ausfuehrung.tick("eroeffnung")
    assert bericht["ausgefuehrt"] == [] and bericht["wiederholen"]
    del quelle.live["SAP.DE"]
    uhr.stellen("2026-10-12T09:04:00")
    bericht = ausfuehrung.tick()
    assert bericht["ausgefuehrt"] == [] and bericht["wiederholen"] and bericht["fehler"]
    quelle.kurs("SAP.DE", "202", zeit("2026-10-12T09:05:00"))
    uhr.stellen("2026-10-12T09:06:00")
    assert len(ausfuehrung.tick()["ausgefuehrt"]) == 1


def test_veralteter_kurs_bei_offenem_markt_fuehrt_nicht_aus(spiel, quelle, uhr):
    sonntagabend(spiel, quelle, uhr)
    uhr.stellen("2026-10-12T09:20:00")
    quelle.kurs("SAP.DE", "200", zeit("2026-10-12T08:30:00"))  # älter als 30 Minuten
    bericht = ausfuehrung.tick()
    assert bericht["ausgefuehrt"] == [] and bericht["fehler"] and len(laden()["offene_orders"]) == 1


def test_nachbuchung_steht_aus_dann_keine_ausfuehrung(spiel, quelle, uhr):
    sonntagabend(spiel, quelle, uhr)
    p = laden()
    p["verarbeitet_bis"] = "2026-10-09"
    g.portfolio_speichern(p)
    uhr.stellen("2026-10-12T09:03:00")
    quelle.kurs("SAP.DE", "200", zeit("2026-10-12T09:01:00"))
    bericht = ausfuehrung.tick()
    assert bericht["ausgefuehrt"] == [] and bericht["rueckstand_nachbuchung"]


# --------------------------------------------------------------------------
# Limits, Stops, Kursziele, Knock-outs


def test_limit_order_wird_bei_beruehrung_ausgefuehrt(spiel, quelle, uhr):
    uhr.stellen("2026-10-12T10:00:00")
    portfolio()
    journal(spiel, datum="2026-10-12", eintraege=(("01", "09:55", "ausgewogen", "SAP.DE"),))
    sperre(spiel, start="2026-10-12T09:50:00+02:00")
    quelle.kurs("SAP.DE", "200")
    assert kaufen(journal_id="J-20261012-01", limit=195) == 0
    assert trades()[0]["aktion"] == "vormerkung"
    (spiel / "session.lock").unlink()
    uhr.stellen("2026-10-12T10:05:00")
    quelle.kurs("SAP.DE", "198")
    assert ausfuehrung.tick()["ausgefuehrt"] == []
    uhr.stellen("2026-10-12T10:10:00")
    quelle.kurs("SAP.DE", "194")
    bericht = ausfuehrung.tick()
    assert len(bericht["ausgefuehrt"]) == 1
    kauf = trades(aktion="kauf")[0]
    assert kauf["bemerkung"].startswith("automatisch (Auslöser: Limit)") and kauf["kurs_basiswert"] == "194.000000"


def position_mit_stop(stop="190", kursziel="230", **extra):
    return portfolio(positionen=[aktie("P-0001", "SAP.DE", 1, "200", stop=stop, kursziel=kursziel, **extra)],
                     cash="800.00")


def test_stop_wird_im_tick_ausgeloest(spiel, quelle, uhr):
    position_mit_stop()
    uhr.stellen("2026-10-12T11:00:00")
    quelle.kurs("SAP.DE", "195")
    assert ausfuehrung.tick()["ausgefuehrt"] == []
    uhr.stellen("2026-10-12T11:05:00")
    quelle.kurs("SAP.DE", "188")
    bericht = ausfuehrung.tick()
    assert len(bericht["ausgefuehrt"]) == 1
    verkauf = trades(aktion="verkauf")[0]
    assert verkauf["grund"] == "stop" and verkauf["kurs_basiswert"] == "188.000000"
    assert verkauf["bemerkung"].startswith("automatisch (Auslöser: Stop)")
    assert laden()["positionen"] == []


def test_kursziel_wird_im_tick_ausgeloest(spiel, quelle, uhr):
    position_mit_stop()
    uhr.stellen("2026-10-12T11:00:00")
    quelle.kurs("SAP.DE", "231")
    ausfuehrung.tick()
    verkauf = trades(aktion="verkauf")[0]
    assert verkauf["grund"] == "kursziel" and verkauf["bemerkung"].startswith("automatisch (Auslöser: Kursziel)")


def test_knockout_wird_im_tick_ausgebucht(spiel, quelle, uhr):
    ko = {"id": "P-0001", "typ": "ko", "richtung": "long", "ticker": "DAX KO Long", "basiswert": "^GDAXI",
          "stueck": "1", "einstand": "50", "eroeffnet": "2026-10-01T10:00:00+02:00",
          "parameter": {"basispreis": "19000", "barriere": "19500", "wert_je_stueck": "500", "stand": "2026-10-01"},
          "stop": None, "kursziel": None, "journal_id": "J-20261001-01", "stop_historie": []}
    portfolio(profil="aggressiv", positionen=[ko], cash="950.00")
    uhr.stellen("2026-10-12T11:00:00")
    quelle.kurs("^GDAXI", "19450")
    bericht = ausfuehrung.tick()
    assert len(bericht["ausgefuehrt"]) == 1
    z = trades("aggressiv", "knockout")[0]
    assert z["bemerkung"].startswith("automatisch (Auslöser: Knock-out)") and z["kursquelle"] == "kurse"
    assert laden("aggressiv")["positionen"] == []


def test_limits_bei_ausfuehrung_verletzt_order_verfaellt_mit_vermerk(spiel, quelle, uhr):
    sonntagabend(spiel, quelle, uhr, profil="aggressiv", typ="ko", basiswert="^GDAXI", einsatz=100, stop=19500,
                 hebel=5)
    p = laden("aggressiv")
    p["drawdown_stufe"] = 2  # Stufe 2: keine neuen Zertifikate
    g.portfolio_speichern(p)
    uhr.stellen("2026-10-12T09:03:00")
    quelle.kurs("^GDAXI", "20010", zeit("2026-10-12T09:01:00"))
    ausfuehrung.tick()
    p = laden("aggressiv")
    assert p["offene_orders"] == [] and p["positionen"] == []
    verfall = trades("aggressiv", "verfall")[0]
    assert "Limits bei Ausführung verletzt" in verfall["bemerkung"] and verfall["bemerkung"].startswith("automatisch")


# --------------------------------------------------------------------------
# Kein doppeltes Buchen


def test_order_mit_endbuchung_wird_nicht_erneut_ausgefuehrt(spiel, quelle, uhr):
    order = sonntagabend(spiel, quelle, uhr)
    p = laden()
    lauf = g.Buchungslauf(p)
    lauf.trade(zeit=zeit("2026-10-12T09:01:00"), order_id=order["id"], aktion="storno", journal_id="J-20261011-01",
               grund="order")
    lauf.speichern()  # Absturz-Nachbildung: Endbuchung steht in trades/, die Order noch im Portfolio
    uhr.stellen("2026-10-12T09:03:00")
    quelle.kurs("SAP.DE", "200", zeit("2026-10-12T09:01:00"))
    bericht = ausfuehrung.tick()
    assert bericht["ausgefuehrt"] == [] and bericht["probleme"]
    assert trades(aktion="kauf") == []


def test_gleichzeitige_ticks_buchen_eine_order_genau_einmal(spiel, quelle, uhr):
    sonntagabend(spiel, quelle, uhr)
    uhr.stellen("2026-10-12T09:03:00")
    quelle.kurs("SAP.DE", "200", zeit("2026-10-12T09:01:00"))
    ergebnisse = []

    def lauf():
        ergebnisse.append(ausfuehrung.tick())

    threads = [threading.Thread(target=lauf) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(len(b["ausgefuehrt"]) for b in ergebnisse) == 1
    assert len(trades(aktion="kauf")) == 1 and len(laden()["positionen"]) == 1
    assert fehler_der_pruefung() == []


def test_claude_session_und_ausfuehrung_buchen_gleichzeitig_ohne_doppelbuchung(spiel, quelle, uhr):
    order = sonntagabend(spiel, quelle, uhr)
    uhr.stellen("2026-10-12T09:03:00")
    quelle.kurs("SAP.DE", "200", zeit("2026-10-12T09:01:00"))
    journal(spiel, datum="2026-10-12", eintraege=(("01", "09:02", "ausgewogen", "BMW.DE"),))
    sperre(spiel, start="2026-10-12T09:00:00+02:00")
    quelle.kurs("BMW.DE", "100", zeit("2026-10-12T09:01:00"))
    ergebnisse = {}

    def session():  # Claude kauft parallel mit einem anderen Journal-Eintrag und storniert nichts
        ergebnisse["kauf"] = kaufen(basiswert="BMW.DE", journal_id="J-20261012-01", einsatz=150, stop=90)

    def automatik():
        ergebnisse["tick"] = ausfuehrung.tick()

    threads = [threading.Thread(target=session), threading.Thread(target=automatik)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert ergebnisse["kauf"] == 0
    if laden()["offene_orders"]:  # die Session buchte zuerst: der Tick hatte keinen Kurs für die neue Position
        assert ergebnisse["tick"]["wiederholen"]
        uhr.stellen("2026-10-12T09:04:00")
        quelle.kurs("SAP.DE", "200", zeit("2026-10-12T09:03:30"))
        quelle.kurs("BMW.DE", "100", zeit("2026-10-12T09:03:30"))
        ausfuehrung.tick()
    p = laden()
    assert len(p["positionen"]) == 2 and p["offene_orders"] == []
    assert len(trades(aktion="kauf")) == 2
    assert len({z["order_id"] for z in trades(aktion="kauf")}) == 2 and order["id"] in {z["order_id"] for z in trades()}
    assert fehler_der_pruefung() == []


def test_buchungssperre_gilt_prozessuebergreifend(spiel):
    code = ("import sys, time\nsys.path.insert(0, 'tools')\nimport gemeinsam as g\n"
            "with g.buchungssperre():\n    print('belegt', flush=True)\n    time.sleep(4)\n")
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=WURZEL, stdout=subprocess.PIPE, text=True,
                            env={**os.environ, "STOCKMASTER_DATA_DIR": str(spiel)})
    try:
        assert proc.stdout.readline().strip() == "belegt"
        with pytest.raises(g.BuchungssperreBelegt), g.buchungssperre(0.3):
            pass
    finally:
        proc.kill()
        proc.wait()
    with g.buchungssperre(1):  # nach dem Ende des anderen Prozesses frei
        pass


def test_tick_bei_belegter_sperre_versucht_es_spaeter_erneut(spiel, quelle, uhr, monkeypatch):
    sonntagabend(spiel, quelle, uhr)
    uhr.stellen("2026-10-12T09:03:00")
    quelle.kurs("SAP.DE", "200", zeit("2026-10-12T09:01:00"))
    einst = {**ausfuehrung.einstellungen(), "sperre_wartezeit_sekunden": 0.2}
    monkeypatch.setattr(ausfuehrung, "einstellungen", lambda: einst)
    ergebnis = {}

    def tick():
        ergebnis["bericht"] = ausfuehrung.tick()

    with g.buchungssperre():
        t = threading.Thread(target=tick)
        t.start()
        t.join()
    assert ergebnis["bericht"]["wiederholen"] and ergebnis["bericht"]["ausgefuehrt"] == []
    assert len(laden()["offene_orders"]) == 1
    assert len(ausfuehrung.tick()["ausgefuehrt"]) == 1


# --------------------------------------------------------------------------
# Uhr: Ereignisse, Zeitzonen, Sommerzeit, Feiertage, Frühschluss


def ereignis_zeiten(tag):
    beginn = zeit(f"{tag}T00:00:00")
    return [(e["zeit"].strftime("%H:%M"), e["art"], e["boerse"]) for e in
            ausfuehrung.ereignisse(beginn, beginn + timedelta(days=1))]


def test_ereignisse_beruecksichtigen_sommerzeit_unterschiede_zwischen_europa_und_usa():
    # 27.10.2026: Europa schon Winterzeit (seit 25.10.), die USA noch Sommerzeit (bis 1.11.): NYSE 14:30 deutsche Zeit
    assert ("09:01", "eroeffnung", "xetra") in ereignis_zeiten("2026-10-27")
    assert ("14:31", "eroeffnung", "nyse") in ereignis_zeiten("2026-10-27")
    assert ("21:58", "schluss", "nyse") in ereignis_zeiten("2026-10-27") or ("21:58", "schluss", "rohstoffe") in \
        ereignis_zeiten("2026-10-27")
    # 3.11.2026: beide in Winterzeit: NYSE 15:30
    assert ("15:31", "eroeffnung", "nyse") in ereignis_zeiten("2026-11-03")
    assert ("21:58", "schluss", "nyse") in ereignis_zeiten("2026-11-03")
    assert ("22:06", "schlusskurs", "nyse") in ereignis_zeiten("2026-11-03")


def test_ereignisse_fruehschluss_und_feiertag():
    assert ("18:58", "schluss", "nyse") in ereignis_zeiten("2026-11-27")  # 13:00 New York
    nyse = [e for e in ereignis_zeiten("2026-11-26") if e[2] == "nyse"]  # Thanksgiving: geschlossen
    assert nyse == []
    assert ereignis_zeiten("2026-10-17") == []  # Samstag


def test_faellig_im_takt_und_zu_oeffnung_und_schluss():
    assert ausfuehrung.faellig(zeit("2026-10-11T12:00:00"), zeit("2026-10-11T12:30:00")) is None  # Sonntag
    assert ausfuehrung.faellig(zeit("2026-10-12T08:58:00"), zeit("2026-10-12T09:00:30")) is None  # Takt 5 Min.
    assert ausfuehrung.faellig(zeit("2026-10-12T08:50:00"), zeit("2026-10-12T09:01:10")) == "eroeffnung"
    assert ausfuehrung.faellig(zeit("2026-10-12T09:01:10"), zeit("2026-10-12T09:04:00")) is None
    assert ausfuehrung.faellig(zeit("2026-10-12T09:01:10"), zeit("2026-10-12T09:06:20")) == "takt"
    assert ausfuehrung.faellig(zeit("2026-10-12T09:06:20"), zeit("2026-10-12T09:07:30"), wiederholen=True) == "takt"
    assert ausfuehrung.faellig(zeit("2026-10-12T17:00:00"), zeit("2026-10-12T17:28:30")) == "schluss"
    assert ausfuehrung.faellig(zeit("2026-10-12T17:28:30"), zeit("2026-10-12T17:36:30")) == "schlusskurs"  # Xetra
    assert ausfuehrung.faellig(zeit("2026-10-12T22:10:00"), zeit("2026-10-12T22:30:00")) is None  # alles geschlossen
    assert ausfuehrung.faellig(zeit("2026-10-12T22:10:00"), zeit("2026-10-12T22:12:00"), wiederholen=True) == "takt"


# --------------------------------------------------------------------------
# Prüfungen (pruefe.py)


def test_pruefung_meldet_doppelte_endbuchung_vorzeitige_ausfuehrung_und_buchung_ausserhalb_der_zeit(spiel):
    portfolio()
    p = laden()
    lauf = g.Buchungslauf(p)
    lauf.trade(zeit=zeit("2026-10-12T10:00:00"), order_id="O-0001", aktion="vormerkung", journal_id="J-20261012-01",
               grund="order")
    lauf.trade(zeit=zeit("2026-10-12T09:00:00"), order_id="O-0001", aktion="kauf", journal_id="J-20261012-01",
               grund="order")  # vor der Vormerkung
    lauf.trade(zeit=zeit("2026-10-12T10:05:00"), order_id="O-0001", aktion="verfall", journal_id="J-20261012-01",
               grund="verfall")  # zweite Endbuchung
    lauf.trade(zeit=zeit("2026-10-12T20:00:00"), position_id="P-0009", aktion="verkauf", basiswert="SAP.DE",
               kursquelle="kurse", grund="stop", journal_id="J-20261001-01",
               bemerkung=g.automatisch_text("Stop"))  # außerhalb der Xetra-Handelszeit
    lauf.trade(zeit=zeit("2026-10-12T10:10:00"), position_id="P-0009", aktion="verkauf", basiswert="SAP.DE",
               kursquelle="historie:open", grund="stop", journal_id="J-20261001-01",
               bemerkung="automatisch (Auslöser: Zauberei)")
    lauf.speichern()
    texte = [b.text for b in pruefe.pruefe_ausfuehrung("ausgewogen")]
    assert any("vor der Vormerkung" in t for t in texte)
    assert any("2 Endbuchungen" in t for t in texte)
    assert any("außerhalb der Handelszeit" in t for t in texte)
    assert any("unbekannter Auslöser" in t for t in texte)
    assert any("nur zu protokollierten Kursen" in t for t in texte)


# --------------------------------------------------------------------------
# Nachbuchung als Abgleich


@pytest.mark.parametrize("tief, erwartet", [("187", False), ("195", True)])
def test_nachbuchung_gleicht_automatische_ausfuehrungen_mit_der_tageskerze_ab(spiel, quelle, uhr, tief, erwartet):
    position_mit_stop()
    uhr.stellen("2026-10-12T11:05:00")
    quelle.kurs("SAP.DE", "188")
    ausfuehrung.tick()
    quelle.kerze("SAP.DE", "2026-10-12", 200, 201, tief, 199)
    uhr.stellen("2026-10-13T00:30:00")
    sperre(spiel, start="2026-10-13T00:29:00+02:00")
    meldungen = bewertung.nachbuchen_profil("ausgewogen")
    assert any("Abgleich prüfen" in m for m in meldungen) is erwartet


def test_vorgemerkter_verkauf_wird_zur_eroeffnung_ausgefuehrt(spiel, quelle, uhr):
    portfolio(positionen=[aktie("P-0001", "SAP.DE", 1, "200", stop="150", kursziel="400")], cash="800.00")
    uhr.stellen("2026-10-11T19:00:00")
    journal(spiel, datum="2026-10-11", eintraege=(("01", "18:55", "ausgewogen", "SAP.DE Verkauf"),))
    sperre(spiel, start="2026-10-11T18:50:00+02:00")
    quelle.kurs("SAP.DE", "210")
    assert buchen.main(["verkaufen", "--profil", "ausgewogen", "--position-id", "P-0001",
                        "--journal-id", "J-20261011-01"]) == 0
    (spiel / "session.lock").unlink()
    assert len(laden()["offene_orders"]) == 1
    uhr.stellen("2026-10-12T09:02:00")
    quelle.kurs("SAP.DE", "212", zeit("2026-10-12T09:01:00"))
    bericht = ausfuehrung.tick("eroeffnung")
    assert len(bericht["ausgefuehrt"]) == 1
    verkauf = trades(aktion="verkauf")[0]
    assert verkauf["grund"] == "order" and verkauf["journal_id"] == "J-20261011-01"
    assert verkauf["bemerkung"].startswith("automatisch (Auslöser: Eröffnung)")
    assert laden()["positionen"] == [] and laden()["offene_orders"] == []
