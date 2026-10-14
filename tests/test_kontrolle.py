"""Mechanische Kontrollportfolios (Strategie-Labor L5): passiv, Zufall, Labor; Aktivierung nur über die Konfiguration."""

import json
from datetime import date, datetime, timedelta

import pytest

import bewertung
import buchen
import gemeinsam as g
import kontrolle
import pruefe
from helfer import laden, portfolio

LIMITS = {"max_anteil_zertifikate": "0.00", "max_hebel": "1", "max_exposure": "1.0", "max_einzelposition": "1.0",
          "min_cashquote": "0.01", "max_risiko_trade": "1.0", "drawdown_stufe1": "-0.30", "drawdown_stufe2": "-0.50",
          "benchmark_etf_anteil": "1.00"}


def zeit(text):
    return datetime.fromisoformat(text).replace(tzinfo=g.TZ)


@pytest.fixture
def spiel(projekt, quelle, uhr, framework):
    """Spiel mit den drei Kontrollportfolios aktiviert (config/profile.json im Framework-Testverzeichnis)."""
    datei = framework / "config" / "profile.json"
    profile = json.loads(datei.read_text(encoding="utf-8"))
    for name in ("passiv", "zufall", "labor"):
        profile["profile"][name] = dict(LIMITS)
    profile["kontrolle"] = {"passiv": "passiv", "zufall": "zufall", "labor": "labor"}
    datei.write_text(json.dumps(profile), encoding="utf-8")
    g.json_schreiben(g.spiel_pfad(), {"startdatum": "2026-10-12"})
    quelle.konstant("EUNL.DE", "2026-09-20", "2027-01-31", "100")
    quelle.konstant("EURUSD=X", "2026-09-20", "2027-01-31", "1.10")
    for ticker in ("SAP.DE", "ALV.DE", "SXR8.DE"):
        quelle.konstant(ticker, "2026-09-20", "2027-01-31", "50")
    uhr.stellen("2026-10-13T10:30")
    for name in ("passiv", "zufall", "labor"):
        portfolio(name, startdatum="2026-10-12", verarbeitet_bis="2026-10-12")
    return projekt


def live(quelle, uhr, kurs="100", ticker="EUNL.DE"):
    quelle.kurs(ticker, kurs, uhr())


def konfig_aendern(framework, **standard):
    datei = framework / "config" / "kontrolle.json"
    k = json.loads(datei.read_text(encoding="utf-8"))
    for typ, werte in standard.items():
        k["standard"][typ].update(werte)
    datei.write_text(json.dumps(k), encoding="utf-8")


def bericht_ohne(profil, bericht):
    return [z for z in bericht["ausgefuehrt"] if z["profil"] == profil]


# ----------------------------------------------------------------------------- Aktivierung


def test_ohne_eintrag_in_der_konfiguration_geschieht_nichts(projekt, quelle, uhr):
    g.json_schreiben(g.spiel_pfad(), {"startdatum": "2026-10-12"})
    portfolio("ausgewogen", startdatum="2026-10-12", verarbeitet_bis="2026-10-12")
    assert g.kontrolle_profile() == {} and kontrolle.aktive_profile() == {}
    assert kontrolle.tick()["hinweis"] == "Keine aktiven Kontrollportfolios."
    assert "Keine Kontrollportfolios" in kontrolle.status()[0]


def test_kontrollprofile_sind_keine_claude_profile(spiel):
    assert set(g.claude_profile()) == {"defensiv", "ausgewogen", "aggressiv", "overnight"}
    assert {"passiv", "zufall", "labor"} <= set(g.profile())
    assert not ({"passiv", "zufall", "labor"} & set(pruefe.profile_am("2026-10-13")))
    assert not ({"passiv", "zufall", "labor"} & set(g.richtlinien_offen()))
    with pytest.raises(g.Fehler, match="mechanisches Kontrollportfolio"):
        buchen.portfolio_pruefen("passiv")


# ----------------------------------------------------------------------------- passiv


def test_passiv_kauft_einmal_die_benchmark_unter_echten_kosten(spiel, quelle, uhr):
    live(quelle, uhr)
    bericht = kontrolle.tick()
    gebucht = [z for z in bericht["ausgefuehrt"] if z["profil"] == "passiv"]
    assert len(gebucht) == 1 and gebucht[0]["aktion"] == "kauf" and gebucht[0]["ticker"] == "EUNL.DE"
    p = laden("passiv")
    assert len(p["positionen"]) == 1
    zeile = g.trades_lesen("passiv")[0]
    assert zeile["bemerkung"].startswith("automatisch (Auslöser: Kontrollportfolio)") and zeile["gebuehr_eur"] == "1.00"
    assert float(zeile["spread_eur"]) > 0 and zeile["kursquelle"] == "kurse"
    # Journal-Eintrag mechanisch, vor der Order, gleiche Portfolio-Zuordnung
    eintrag = g.journal_eintraege()[zeile["journal_id"]]
    assert "mechanisch" in eintrag["felder"] and eintrag["person"] == "mechanisch" and eintrag["portfolio"] == "passiv"
    assert [b for b in pruefe.pruefe_kontrolle("passiv") + pruefe.pruefe_journal("passiv")] == []
    # idempotent am selben Tag und an den Folgetagen: es bleibt bei einem Kauf
    assert kontrolle.tick()["ausgefuehrt"] == [z for z in kontrolle.tick()["ausgefuehrt"] if z["profil"] != "passiv"]
    uhr.stellen("2026-10-14T10:30")
    p = laden("passiv")
    p["verarbeitet_bis"] = "2026-10-13"
    g.portfolio_speichern(p)
    live(quelle, uhr, "101")
    assert bericht_ohne("passiv", kontrolle.tick()) == [] and len(laden("passiv")["positionen"]) == 1


def test_kein_kauf_bei_geschlossener_boerse_aber_spaeter(spiel, quelle, uhr):
    uhr.stellen("2026-10-13T20:00")  # Xetra zu
    live(quelle, uhr)
    assert bericht_ohne("passiv", kontrolle.tick()) == []
    assert laden("passiv")["positionen"] == []
    uhr.stellen("2026-10-14T09:30")
    p = laden("passiv")
    p["verarbeitet_bis"] = "2026-10-13"
    g.portfolio_speichern(p)
    live(quelle, uhr)
    assert len(bericht_ohne("passiv", kontrolle.tick())) == 1


def test_nachbuchung_steht_aus_dann_wartet_die_regel(spiel, quelle, uhr):
    p = laden("passiv")
    p["verarbeitet_bis"] = "2026-10-09"
    g.portfolio_speichern(p)
    live(quelle, uhr)
    bericht = kontrolle.tick()
    assert bericht_ohne("passiv", bericht) == [] and any("Nachbuchung" in u["text"] for u in bericht["uebersprungen"])


# ----------------------------------------------------------------------------- Zufall


def test_zufall_ist_reproduzierbar_und_seed_steht_im_protokoll(spiel):
    kandidaten = kontrolle.kandidatenliste(["etf_xetra", "dax40"])
    cfg = kontrolle.parameter("zufall", "zufall")
    a = kontrolle.zufall_entscheidung("zufall", cfg, date(2026, 10, 13), kandidaten)
    b = kontrolle.zufall_entscheidung("zufall", cfg, date(2026, 10, 13), kandidaten)
    assert a == b and a["seed"] == "3000|zufall|2026-10-13"
    anderer_seed = kontrolle.zufall_entscheidung("zufall", {**cfg, "seed": 4}, date(2026, 10, 13), kandidaten)
    assert anderer_seed["seed"] != a["seed"]
    # Kaufhäufigkeit entspricht der Vorgabe (ohne Vorbild-Daten 20 %)
    tage = [date(2026, 11, 2) + timedelta(days=i) for i in range(400)]
    kaeufe = sum(kontrolle.zufall_entscheidung("zufall", cfg, t, kandidaten)["kaufen"] for t in tage)
    assert 0.12 < kaeufe / 400 < 0.28
    assert all(t in ("aktie", "etf") for _, t in kandidaten) and ("SAP.DE", "aktie") in kandidaten


def test_vorbild_statistik_aus_trades(spiel, monkeypatch):
    portfolio("ausgewogen", startdatum="2026-10-12", verarbeitet_bis="2026-10-12")
    zeilen = [
        {"aktion": "kauf", "grund": "order", "position_id": "P1", "zeit": "2026-10-12T10:00:00+02:00", "betrag_eur": "-101.00"},
        {"aktion": "verkauf", "grund": "order", "position_id": "P1", "zeit": "2026-10-16T10:00:00+02:00", "betrag_eur": "104.00"},
        {"aktion": "kauf", "grund": "order", "position_id": "P2", "zeit": "2026-10-13T10:00:00+02:00", "betrag_eur": "-201.00"},
        {"aktion": "verkauf", "grund": "order", "position_id": "P2", "zeit": "2026-10-23T10:00:00+02:00", "betrag_eur": "190.00"},
    ]
    monkeypatch.setattr(g, "trades_lesen", lambda profil: zeilen)
    monkeypatch.setattr(bewertung, "nav_lesen", lambda profil: [
        {"datum": "2026-10-12", "portfoliowert": "1000"}, {"datum": "2026-10-13", "portfoliowert": "1000"}])
    s = kontrolle.vorbild_statistik("ausgewogen")
    assert s["kaeufe"] == 2 and s["tage"] == 2 and sorted(s["dauern"]) == [4, 10]
    assert sorted(round(a, 3) for a in s["anteile"]) == [0.101, 0.201]


def test_zufall_kauft_und_verkauft_nach_der_gezogenen_haltedauer(spiel, quelle, uhr, framework):
    konfig_aendern(framework, zufall={"kaufwahrscheinlichkeit": "1.0", "haltedauer_tage": 1, "listen": ["etf_xetra"],
                                      "einsatz_anteil": "0.10"})
    for ticker, _ in kontrolle.kandidatenliste(["etf_xetra"]):
        quelle.konstant(ticker, "2026-09-20", "2027-01-31", "50")
        quelle.kurs(ticker, "50", uhr())
    bericht = kontrolle.tick()
    kauf = [z for z in bericht_ohne("zufall", bericht) if z["aktion"] == "kauf"]
    assert len(kauf) == 1
    eintrag = next(e for e in kontrolle.protokoll_lesen("zufall") if e["ereignis"] == "entscheidung")
    assert eintrag["seed"] == "3000|zufall|2026-10-13" and eintrag["kaufen"] and eintrag["ticker"] == kauf[0]["ticker"]
    position = laden("zufall")["positionen"][0]
    assert position["kontrolle"]["verkauf_ab"] == "2026-10-14"
    # nächster Handelstag: erst verkaufen, dann (Wahrscheinlichkeit 1) neu ziehen und kaufen
    uhr.stellen("2026-10-14T10:30")
    p = laden("zufall")
    p["verarbeitet_bis"] = "2026-10-13"
    g.portfolio_speichern(p)
    for ticker, _ in kontrolle.kandidatenliste(["etf_xetra"]):
        quelle.kurs(ticker, "51", uhr())
    aktionen = [z["aktion"] for z in bericht_ohne("zufall", kontrolle.tick())]
    assert aktionen[0] == "verkauf"
    assert pruefe.pruefe_kontrolle("zufall") == [] and pruefe.pruefe_journal("zufall") == []


# ----------------------------------------------------------------------------- Labor


def labor_daten(ticker="EUNL.DE", bis=date(2026, 10, 12), n=40):
    from labor import daten
    from kurse import Kerze
    from decimal import Decimal

    tage, t = [], bis
    while len(tage) < n:
        if t.weekday() < 5:
            tage.append(t)
        t -= timedelta(days=1)
    tage.reverse()
    zeilen = [{"datum": d.isoformat(), "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100 + i, "dividende": 0, "split": 0}
              for i, d in enumerate(tage)]
    g.csv_schreiben(daten.cache_datei(ticker), daten.FELDER, zeilen)


def test_labor_strategie_kauft_bei_aufwaertstrend(spiel, quelle, uhr, framework):
    konfig_aendern(framework, labor={"strategie": "trend", "parameter": {"ticker": "EUNL.DE", "tage": 10, "pruefung": "taeglich"}})
    labor_daten()
    live(quelle, uhr)
    gebucht = bericht_ohne("labor", kontrolle.tick())
    assert len(gebucht) == 1 and gebucht[0]["ticker"] == "EUNL.DE"
    assert "Labor-Strategie trend" in g.trades_lesen("labor")[0]["bemerkung"]


def test_labor_daten_veraltet_wartet(spiel, quelle, uhr, framework):
    konfig_aendern(framework, labor={"strategie": "buyhold", "parameter": {"ticker": "EUNL.DE"}})
    labor_daten(bis=date(2026, 9, 25))
    live(quelle, uhr)
    bericht = kontrolle.tick()
    assert bericht_ohne("labor", bericht) == [] and any("veraltet" in u["text"] for u in bericht["uebersprungen"])


# ----------------------------------------------------------------------------- Prüfung


def test_pruefung_erkennt_claude_order_im_kontrollportfolio(spiel, quelle, uhr):
    live(quelle, uhr)
    kontrolle.tick()
    p = laden("passiv")
    lauf = g.Buchungslauf(p)
    lauf.trade(zeit=uhr(), aktion="kauf", typ="etf", richtung="long", ticker="EUNL.DE", basiswert="EUNL.DE", stueck="1",
               betrag_eur="-100", journal_id="J-20261013-09", grund="order", kursquelle="kurse", bemerkung="")
    lauf.speichern()
    meldungen = [str(b) for b in pruefe.pruefe_kontrolle("passiv")]
    assert any("nicht mechanisch entstanden" in m for m in meldungen)


def test_prognose_zeile_gilt_nicht_fuer_mechanische_eintraege(spiel, quelle, uhr):
    import prognosen

    live(quelle, uhr)
    kontrolle.tick()
    assert prognosen.pruef_hinweise() == []
