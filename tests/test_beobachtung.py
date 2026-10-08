"""Beobachtungsliste und Screener: Kennzahlen, Abruf-Hilfen, Aktualisierung und Ausgabe, ohne Netzwerk."""

import json
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

import beobachtung
import gemeinsam as g
import kurse
from gemeinsam import Fehler


def kerzen_reihe(schluesse, ende=date(2026, 10, 9), volumen=1000, offen=None):
    """Tageskerzen (nur Handelstage Mo–Fr) mit den gegebenen Schlusskursen, das letzte am `ende`."""
    tage, tag = [], ende
    while len(tage) < len(schluesse):
        if tag.weekday() < 5:
            tage.append(tag)
        tag -= timedelta(days=1)
    tage.reverse()
    kerzen = []
    for i, (tag, kurs) in enumerate(zip(tage, schluesse)):
        kerzen.append({"datum": tag, "open": kurs if offen is None else offen, "high": kurs * 1.01,
                       "low": kurs * 0.99, "close": kurs,
                       "volume": volumen if callable(volumen) is False else volumen(i)})
    return kerzen


def steigend(n, start=100.0, schritt=1.0):
    return [start + i * schritt for i in range(n)]


# --------------------------------------------------------------------------
# Kennzahlen


def test_kennzahlen_renditen_und_abstaende():
    schluesse = steigend(70)  # 100 ... 169
    z = beobachtung.kennzahlen(kerzen_reihe(schluesse))
    assert z["kurs"] == 169.0 and z["datum"] == "2026-10-09" and z["tage"] == 70
    assert z["rendite_1t"] == pytest.approx(169 / 168 - 1, abs=1e-6)
    assert z["rendite_5t"] == pytest.approx(169 / 164 - 1, abs=1e-6)
    assert z["rendite_20t"] == pytest.approx(169 / 149 - 1, abs=1e-6)
    assert z["rendite_60t"] == pytest.approx(169 / 109 - 1, abs=1e-6)
    assert z["abstand_hoch"] == pytest.approx(169 / (169 * 1.01) - 1, abs=1e-6)
    assert z["abstand_tief"] == pytest.approx(169 / (100 * 0.99) - 1, abs=1e-6)
    assert z["sma20_abstand"] == pytest.approx(169 / (sum(schluesse[-20:]) / 20) - 1, abs=1e-6)
    assert z["sma50_abstand"] == pytest.approx(169 / (sum(schluesse[-50:]) / 50) - 1, abs=1e-6)
    assert z["volatilitaet_20t"] is not None and z["volatilitaet_20t"] > 0


def test_kennzahlen_ohne_ausreichende_historie_sind_none():
    z = beobachtung.kennzahlen(kerzen_reihe(steigend(10)))
    assert z["rendite_1t"] is not None and z["rendite_5t"] is not None
    assert z["rendite_20t"] is None and z["rendite_60t"] is None
    assert z["sma20_abstand"] is None and z["sma50_abstand"] is None
    assert z["volatilitaet_20t"] is None and z["volumen_relativ_1t"] is None


def test_kennzahlen_zu_wenig_oder_kein_kurs():
    assert beobachtung.kennzahlen([]) is None
    assert beobachtung.kennzahlen(kerzen_reihe([100.0])) is None
    assert beobachtung.kennzahlen(kerzen_reihe([100.0, 0.0])) is None


def test_kennzahlen_sortiert_unsortierte_kerzen():
    kerzen = kerzen_reihe(steigend(30))
    assert beobachtung.kennzahlen(list(reversed(kerzen))) == beobachtung.kennzahlen(kerzen)


def test_kennzahlen_luecke_und_volumen():
    schluesse = [100.0] * 29 + [110.0]
    kerzen = kerzen_reihe(schluesse, volumen=lambda i: 3000 if i == 29 else 1000)
    kerzen[-1]["open"] = 105.0  # Eröffnung 5 % über dem Vortagesschluss
    z = beobachtung.kennzahlen(kerzen)
    assert z["gap_1t"] == pytest.approx(0.05)
    assert z["volumen_relativ_1t"] == pytest.approx(3.0)  # gegen den Schnitt der 20 Tage davor, ohne den letzten Tag
    assert z["rendite_1t"] == pytest.approx(0.1)


def test_kennzahlen_volumen_null_gibt_kein_verhaeltnis():
    z = beobachtung.kennzahlen(kerzen_reihe(steigend(30), volumen=0))
    assert z["volumen_relativ_1t"] is None


# --------------------------------------------------------------------------
# Abruf-Hilfen (yfinance-Antworten als synthetische DataFrames)


def _frame(tickers, ebene_ticker_oben=True, tage=3, mit_volumen=True):
    index = pd.bdate_range("2026-10-05", periods=tage)
    felder = ["Open", "High", "Low", "Close"] + (["Volume"] if mit_volumen else [])
    spalten = pd.MultiIndex.from_product([tickers, felder] if ebene_ticker_oben else [felder, tickers])
    daten = {}
    for spalte in spalten:
        ticker = spalte[0] if ebene_ticker_oben else spalte[1]
        feld = spalte[1] if ebene_ticker_oben else spalte[0]
        grundwert = 100.0 + 10 * tickers.index(ticker)
        daten[spalte] = [grundwert + i + (0 if feld != "Volume" else 1000) for i in range(tage)]
    return pd.DataFrame(daten, index=index)


@pytest.mark.parametrize("ticker_oben", [True, False])
def test_teilframe_beide_spaltenebenen(ticker_oben):
    frame = _frame(["SAP.DE", "SIE.DE"], ticker_oben)
    teil = beobachtung._teilframe(frame, "SIE.DE", einzeln=False)
    assert set(teil.columns) >= {"Open", "High", "Low", "Close"}
    assert beobachtung._kerzen_aus_frame(teil)[0]["close"] == 110.0
    assert beobachtung._teilframe(frame, "FEHLT.DE", einzeln=False) is None


def test_teilframe_einzelner_wert_ohne_zweite_ebene():
    frame = pd.DataFrame({"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [10]},
                         index=pd.bdate_range("2026-10-05", periods=1))
    assert beobachtung._teilframe(frame, "SAP.DE", einzeln=True) is frame
    assert beobachtung._teilframe(frame, "SAP.DE", einzeln=False) is None


def test_kerzen_aus_frame_ueberspringt_luecken_und_nan_volumen():
    frame = _frame(["SAP.DE"], tage=3)
    teil = beobachtung._teilframe(frame, "SAP.DE", einzeln=True)
    teil.loc[teil.index[0], "Close"] = float("nan")  # Lückentag ohne Schluss
    teil.loc[teil.index[2], "Volume"] = float("nan")
    kerzen = beobachtung._kerzen_aus_frame(teil)
    assert [k["datum"] for k in kerzen] == [date(2026, 10, 6), date(2026, 10, 7)]
    assert kerzen[-1]["volume"] == 0.0


def test_kerzen_aus_frame_ohne_kursspalten():
    assert beobachtung._kerzen_aus_frame(pd.DataFrame({"Close": [1.0]})) == []


def test_yfinance_holen_bloeckeweise_und_fehler_nur_im_block(monkeypatch):
    import types

    aufrufe = []

    def download(teil, **kwargs):
        aufrufe.append(list(teil))
        if "B.DE" in teil:
            raise OSError("Netzwerk")
        return _frame(list(teil))

    monkeypatch.setitem(__import__("sys").modules, "yfinance", types.SimpleNamespace(download=download))
    monkeypatch.setattr(beobachtung.time, "sleep", lambda s: None)
    ergebnis = beobachtung._yfinance_holen(["A.DE", "B.DE", "C.DE"], block=2)
    assert aufrufe == [["A.DE", "B.DE"], ["C.DE"]]
    assert list(ergebnis) == ["C.DE"]  # der fehlgeschlagene Block fehlt, der andere läuft weiter
    assert ergebnis["C.DE"][0]["datum"] == date(2026, 10, 5)


def test_yfinance_holen_einzelwert_und_leere_antwort(monkeypatch):
    import types

    antworten = iter([pd.DataFrame({"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [10]},
                                   index=pd.bdate_range("2026-10-05", periods=1)), pd.DataFrame()])
    monkeypatch.setitem(__import__("sys").modules, "yfinance",
                        types.SimpleNamespace(download=lambda teil, **kw: next(antworten)))
    monkeypatch.setattr(beobachtung.time, "sleep", lambda s: None)
    assert list(beobachtung._yfinance_holen(["A.DE"], block=1)) == ["A.DE"]
    assert beobachtung._yfinance_holen(["B.DE"], block=1) == {}


# --------------------------------------------------------------------------
# Aktualisieren


@pytest.fixture
def stand_umgebung(projekt, uhr, monkeypatch):
    """Datenverzeichnis, feste Uhr (Montag 12.10.2026 10:00), Abruf ersetzt."""
    uhr.stellen("2026-10-12T22:30")  # nach Handelsschluss in Xetra und NYSE
    monkeypatch.setattr(beobachtung, "HOLEN", lambda tickers: {})
    return projekt


def konfig(**listen):
    return {"listen": {k: {"name": k.upper(), "ticker": v} for k, v in listen.items()}}


def test_aktualisieren_schreibt_stand_mit_struktur(stand_umgebung, monkeypatch):
    daten = {t: kerzen_reihe(steigend(70), ende=date(2026, 10, 12)) for t in ("SAP.DE", "AAPL")}
    monkeypatch.setattr(beobachtung, "HOLEN", lambda tickers: {t: daten[t] for t in tickers if t in daten})
    stand = beobachtung.aktualisieren(konfig(a=["SAP.DE", "AAPL", "FEHLT.DE"], b=["AAPL"]))
    assert stand["anzahl"] == 3 and stand["mit_daten"] == 2 and stand["aktuell"] == 2
    assert stand["ohne_daten"] == ["FEHLT.DE"] and stand["veraltet"] == []
    assert stand["listen"] == {"a": {"name": "A", "anzahl": 3, "mit_daten": 2},
                               "b": {"name": "B", "anzahl": 1, "mit_daten": 1}}
    assert stand["eintraege"]["AAPL"]["listen"] == ["a", "b"]
    assert stand["eintraege"]["AAPL"]["waehrung"] == "USD" and stand["eintraege"]["SAP.DE"]["waehrung"] == "EUR"
    assert stand["eintraege"]["SAP.DE"]["handelbar"] is True
    gespeichert = json.loads(beobachtung.stand_pfad().read_text(encoding="utf-8"))
    assert gespeichert["eintraege"].keys() == stand["eintraege"].keys()
    assert beobachtung.stand_pfad().parent.name == ".cache"


def test_aktualisieren_nicht_handelbare_werte_gekennzeichnet(stand_umgebung, monkeypatch):
    daten = {"BILLIG.DE": kerzen_reihe(steigend(30, start=0.2, schritt=0.01), ende=date(2026, 10, 12)),
             "SAP.PA": kerzen_reihe(steigend(30), ende=date(2026, 10, 12))}
    monkeypatch.setattr(beobachtung, "HOLEN", lambda tickers: daten)
    stand = beobachtung.aktualisieren(konfig(a=["BILLIG.DE", "SAP.PA"]))
    billig, paris = stand["eintraege"]["BILLIG.DE"], stand["eintraege"]["SAP.PA"]
    assert billig["handelbar"] is False and "Kurs unter 1" in billig["grund"] and billig["waehrung"] == "EUR"
    assert paris["handelbar"] is False and "nicht erlaubt" in paris["grund"] and paris["waehrung"] is None


def test_aktualisieren_verwirft_laufenden_handelstag(projekt, uhr, monkeypatch):
    uhr.stellen("2026-10-12T11:00")  # Xetra offen
    kerzen = kerzen_reihe(steigend(30), ende=date(2026, 10, 12))
    monkeypatch.setattr(beobachtung, "HOLEN", lambda tickers: {"SAP.DE": kerzen})
    stand = beobachtung.aktualisieren(konfig(a=["SAP.DE"]))
    assert stand["eintraege"]["SAP.DE"]["datum"] == "2026-10-09"  # ohne den noch laufenden Montag
    uhr.stellen("2026-10-12T18:00")  # Xetra geschlossen: die Kerze des Tages ist fertig
    assert beobachtung.aktualisieren(konfig(a=["SAP.DE"]))["eintraege"]["SAP.DE"]["datum"] == "2026-10-12"


def test_aktualisieren_ohne_daten_wirft_fehler_und_behaelt_alten_stand(stand_umgebung, monkeypatch):
    kerzen = kerzen_reihe(steigend(30), ende=date(2026, 10, 12))
    monkeypatch.setattr(beobachtung, "HOLEN", lambda tickers: {"SAP.DE": kerzen})
    beobachtung.aktualisieren(konfig(a=["SAP.DE"]))
    vorher = beobachtung.stand_pfad().read_text(encoding="utf-8")
    monkeypatch.setattr(beobachtung, "HOLEN", lambda tickers: {})
    with pytest.raises(Fehler, match="Keine Kursdaten"):
        beobachtung.aktualisieren(konfig(a=["SAP.DE"]))
    assert beobachtung.stand_pfad().read_text(encoding="utf-8") == vorher


def test_aktualisieren_uebernimmt_alten_stand_als_veraltet(stand_umgebung, monkeypatch):
    kerzen = kerzen_reihe(steigend(30), ende=date(2026, 10, 12))
    monkeypatch.setattr(beobachtung, "HOLEN", lambda tickers: {"SAP.DE": kerzen, "SIE.DE": kerzen})
    beobachtung.aktualisieren(konfig(a=["SAP.DE", "SIE.DE"]))
    monkeypatch.setattr(beobachtung, "HOLEN", lambda tickers: {"SAP.DE": kerzen})  # SIE.DE fehlt jetzt
    stand = beobachtung.aktualisieren(konfig(a=["SAP.DE", "SIE.DE", "NEU.DE"]))
    assert stand["veraltet"] == ["SIE.DE"] and stand["ohne_daten"] == ["NEU.DE"]
    assert stand["eintraege"]["SIE.DE"]["veraltet"] is True and stand["eintraege"]["SIE.DE"]["kurs"] == 129.0
    assert stand["mit_daten"] == 2 and stand["aktuell"] == 1
    assert "veraltet" not in stand["eintraege"]["SAP.DE"]


def test_aktualisieren_einzelne_liste_und_unbekannte_liste(stand_umgebung, monkeypatch):
    abgefragt = []

    def holen(tickers):
        abgefragt.extend(tickers)
        return {t: kerzen_reihe(steigend(30), ende=date(2026, 10, 12)) for t in tickers}

    monkeypatch.setattr(beobachtung, "HOLEN", holen)
    stand = beobachtung.aktualisieren(konfig(a=["SAP.DE"], b=["AAPL"]), nur="b")
    assert abgefragt == ["AAPL"] and list(stand["listen"]) == ["b"]
    with pytest.raises(Fehler, match="Unbekannte Liste"):
        beobachtung.aktualisieren(konfig(a=["SAP.DE"]), nur="x")


def test_stand_lesen_ohne_daten(stand_umgebung):
    with pytest.raises(Fehler, match="Noch keine Daten"):
        beobachtung.stand_lesen()


# --------------------------------------------------------------------------
# Auswahl, Sortierung, Ausgabe


def eintrag(kurs=100.0, **kennzahlen):
    basis = {"name": None, "listen": ["a"], "waehrung": "EUR", "handelbar": True, "grund": None, "datum": "2026-10-09",
             "kurs": kurs, "tage": 252, "rendite_1t": 0.01, "rendite_5t": 0.02, "rendite_20t": 0.03, "rendite_60t": 0.04,
             "abstand_hoch": -0.05, "abstand_tief": 0.3, "sma20_abstand": 0.01, "sma50_abstand": 0.02, "gap_1t": 0.0,
             "volumen_relativ_1t": 1.0, "volatilitaet_20t": 0.25}
    return {**basis, **kennzahlen}


def beispielstand(zeit="2026-10-12T22:30:00+02:00"):
    return {"zeit": zeit, "quelle": "yfinance", "anzahl": 5, "mit_daten": 5, "aktuell": 4,
            "listen": {"a": {"name": "A", "anzahl": 4, "mit_daten": 4}, "b": {"name": "B", "anzahl": 1, "mit_daten": 1}},
            "ohne_daten": [], "veraltet": ["ALT.DE"],
            "eintraege": {"AAA.DE": eintrag(rendite_1t=0.05, gap_1t=0.02, volumen_relativ_1t=3.0, name="Alpha AG"),
                          "BBB.DE": eintrag(rendite_1t=-0.04, rendite_5t=-0.06),
                          "CCC": eintrag(rendite_1t=0.02, listen=["b"], waehrung="USD"),
                          "DDD.DE": eintrag(0.5, handelbar=False, grund="Kurs unter 1 EUR", rendite_1t=0.5),
                          "ALT.DE": eintrag(veraltet=True, rendite_1t=0.9)}}


def test_auswahl_nur_handelbar_aktuell_und_liste():
    stand = beispielstand()
    assert [t for t, _ in beobachtung.auswahl(stand)] == ["AAA.DE", "BBB.DE", "CCC"]
    assert [t for t, _ in beobachtung.auswahl(stand, "b")] == ["CCC"]
    assert "DDD.DE" in [t for t, _ in beobachtung.auswahl(stand, nur_handelbar=False)]
    with pytest.raises(Fehler, match="Unbekannte Liste"):
        beobachtung.auswahl(stand, "x")


def test_sortieren_ueberspringt_fehlende_kennzahlen_und_ist_stabil():
    zeilen = [("B", {"x": 1.0}), ("A", {"x": 1.0}), ("C", {"x": None}), ("D", {"x": 3.0})]
    assert [t for t, _ in beobachtung.sortieren(zeilen, "x")] == ["D", "B", "A"]
    assert [t for t, _ in beobachtung.sortieren(zeilen, "x", absteigend=False)] == ["A", "B", "D"]


def test_kandidaten_bloecke():
    bloecke = {b["titel"]: [w["ticker"] for w in b["werte"]]
               for b in beobachtung.kandidaten(beispielstand(), anzahl=2)}
    assert bloecke["Stärkste Tagesbewegung nach oben"] == ["AAA.DE", "CCC"]
    assert bloecke["Stärkste Tagesbewegung nach unten"][0] == "BBB.DE"
    assert bloecke["Schwächster 5-Tage-Trend"] == ["BBB.DE", "AAA.DE"]
    assert bloecke["Auffälliges Volumen bei steigendem Kurs"] == ["AAA.DE", "CCC"]  # BBB.DE fällt, also ausgeschlossen
    assert bloecke["Eröffnungslücke nach oben"][0] == "AAA.DE"
    assert all(len(v) <= 2 for v in bloecke.values())


def test_prozent_und_zahlformat():
    assert beobachtung._prozent(0.0123) == "+1,23 %" and beobachtung._prozent(-0.5) == "-50,00 %"
    assert beobachtung._prozent(None) == "–" and beobachtung._prozent(0.25, False) == "25,00 %"
    assert beobachtung._zahl(1234.5) == "1.234,50"


def test_kopfzeile_warnt_bei_altem_stand(uhr):
    uhr.stellen("2026-10-12T10:00")
    frisch = beobachtung.kopfzeile(beispielstand(), None)
    assert len(frisch) == 1 and "5 von 5 Werten" in frisch[0] and "kurse.py aktuell" in frisch[0]
    alt = beobachtung.kopfzeile(beispielstand("2026-10-01T22:30:00+02:00"), "a")
    assert len(alt) == 2 and alt[1].startswith("WARNUNG") and "Beobachtungsliste a" in alt[0]


# --------------------------------------------------------------------------
# Kommandozeile


@pytest.fixture
def mit_stand(projekt, uhr):
    uhr.stellen("2026-10-12T22:45")
    g.json_schreiben(beobachtung.stand_pfad(), beispielstand())
    return projekt


def test_cli_kandidaten_liste_werte_pruefen(mit_stand, capsys):
    assert beobachtung.main(["kandidaten", "--anzahl", "2"]) == 0
    ausgabe = capsys.readouterr().out
    assert "== Stärkste Tagesbewegung nach oben" in ausgabe and "AAA.DE" in ausgabe and "Alpha AG" in ausgabe
    assert "DDD.DE" not in ausgabe and "ALT.DE" not in ausgabe  # nicht handelbar und veraltet fallen heraus

    assert beobachtung.main(["liste", "--sortiert", "rendite_1t", "--aufsteigend", "--anzahl", "2"]) == 0
    zeilen = [z for z in capsys.readouterr().out.splitlines() if z.startswith(("AAA", "BBB", "CCC"))]
    assert [z.split()[0] for z in zeilen] == ["BBB.DE", "CCC"]

    assert beobachtung.main(["werte", "DDD.DE", "ALT.DE", "NIX.DE"]) == 0
    ausgabe = capsys.readouterr().out
    assert "[nicht handelbar: Kurs unter 1 EUR]" in ausgabe and "[alter Stand]" in ausgabe
    assert "NIX.DE: nicht in der Beobachtungsliste" in ausgabe

    assert beobachtung.main(["pruefen"]) == 0
    ausgabe = capsys.readouterr().out
    assert "A: 4 von 4 mit Daten" in ausgabe and "Alter Stand (Abruf lückenhaft): ALT.DE" in ausgabe
    assert "Nicht handelbar: DDD.DE" in ausgabe


def test_cli_json(mit_stand, capsys):
    assert beobachtung.main(["kandidaten", "--json", "--liste", "b"]) == 0
    bloecke = json.loads(capsys.readouterr().out)
    assert bloecke[0]["werte"][0]["ticker"] == "CCC"
    assert beobachtung.main(["liste", "--json", "--anzahl", "1"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1


def test_cli_fehler_geben_exit_code_1(projekt, uhr, capsys):
    assert beobachtung.main(["kandidaten"]) == 1
    assert "Noch keine Daten" in capsys.readouterr().err
    g.json_schreiben(beobachtung.stand_pfad(), beispielstand())
    assert beobachtung.main(["liste", "--liste", "x"]) == 1
    assert "Unbekannte Liste" in capsys.readouterr().err


def test_cli_aktualisieren(stand_umgebung, monkeypatch, capsys):
    monkeypatch.setattr(beobachtung, "standard_konfig", lambda: konfig(a=["SAP.DE", "FEHLT.DE"]))
    monkeypatch.setattr(beobachtung, "HOLEN",
                        lambda tickers: {"SAP.DE": kerzen_reihe(steigend(30), ende=date(2026, 10, 12))})
    assert beobachtung.main(["aktualisieren"]) == 0
    ausgabe = capsys.readouterr().out
    assert "1 von 2 Werten aktualisiert" in ausgabe and "FEHLT.DE" in ausgabe
    monkeypatch.setattr(beobachtung, "HOLEN", lambda tickers: {})
    assert beobachtung.main(["aktualisieren"]) == 1


# --------------------------------------------------------------------------
# Konfiguration config/beobachtung.json


def test_konfiguration_ist_gueltig(framework):
    konf = beobachtung.standard_konfig()
    assert set(konf["listen"]) == {"dax40", "sp500", "nasdaq100", "etf_xetra", "etf_us"}
    gesehen = set()
    for kennung, liste in konf["listen"].items():
        assert liste["name"] and liste["ticker"], kennung
        assert len(liste["ticker"]) == len(set(liste["ticker"])), f"Doppelte Ticker in {kennung}"
        assert set(liste.get("namen", {})) <= set(liste["ticker"]), f"Namen ohne Ticker in {kennung}"
        gesehen |= set(liste["ticker"])
    assert len(gesehen) >= 600
    xetra = konf["listen"]["dax40"]["ticker"] + konf["listen"]["etf_xetra"]["ticker"]
    assert all(t.endswith(".DE") for t in xetra)
    for ticker in gesehen:
        assert ticker == ticker.strip().upper() and " " not in ticker and not any(z in ticker for z in "^=/")
        kurse.boerse_von(ticker)  # nur Xetra (.DE), NYSE und NASDAQ erlaubt; sonst Fehler
    assert beobachtung.werte_der_listen(konf)["EUNL.DE"]["listen"] == ["etf_xetra"]
