"""AP6: Nachbuchung und Bewertung (Grundfälle; Szenarien in test_szenarien.py)."""

import json
from decimal import Decimal

import pytest

import bewertung
import gemeinsam as g
from helfer import laden, portfolio, sperre


@pytest.fixture
def lauf(projekt, quelle, uhr):
    uhr.stellen("2026-10-15T10:00:00")
    sperre(projekt, start="2026-10-15T09:30:00+02:00")
    quelle.konstant("EUNL.DE", "2026-09-20", "2026-10-31", "100")
    quelle.konstant("EURUSD=X", "2026-09-20", "2026-10-31", "1.10")
    return projekt


def dateien(projekt):
    return {p: p.read_bytes() for p in sorted(projekt.rglob("*")) if p.is_file() and "historie" not in str(p)}


def test_cash_zins_je_kalendertag_und_tageswerte(lauf):
    portfolio(verarbeitet_bis="2026-10-11")
    assert bewertung.main(["nachbuchen"]) == 0
    p = laden()
    # 1000 * 0,02 / 365 = 0,0548 -> 0,05 je Tag; 12., 13., 14.10.
    assert p["cash"] == "1000.15"
    assert p["verarbeitet_bis"] == "2026-10-14"
    zins = [z for z in g.trades_lesen("ausgewogen") if z["aktion"] == "zins"]
    assert [z["betrag_eur"] for z in zins] == ["0.05", "0.05", "0.05"]
    nav = bewertung.nav_lesen("ausgewogen")
    assert [z["datum"] for z in nav] == ["2026-10-12", "2026-10-13", "2026-10-14"]
    assert nav[-1]["portfoliowert"] == "1000.15"


def test_zweimal_ausfuehren_ist_idempotent(lauf, quelle):
    portfolio(verarbeitet_bis="2026-10-08")
    p = laden()
    p["offene_orders"].append({"id": "O-0001", "art": "market", "aktion": "kauf", "typ": "aktie",
                               "richtung": "long", "ticker": "SAP.DE", "basiswert": "SAP.DE", "einsatz": "200",
                               "stop": "190", "kursziel": "250", "erfasst": "2026-10-08T20:00:00+02:00",
                               "journal_id": "J-20261008-01"})
    g.portfolio_speichern(p)
    quelle.konstant("SAP.DE", "2026-10-01", "2026-10-31", "200")
    assert bewertung.main(["nachbuchen"]) == 0
    assert len(laden()["positionen"]) == 1
    vorher = dateien(lauf)
    assert bewertung.main(["nachbuchen"]) == 0
    assert dateien(lauf) == vorher
    assert bewertung.main(["bericht"]) == 0
    bericht1 = (lauf / "ranking.md").read_text()
    assert bewertung.main(["bericht"]) == 0
    assert (lauf / "ranking.md").read_text() == bericht1


def test_ko_aufzinsung_ueber_wochenende(lauf, quelle, uhr):
    uhr.stellen("2026-10-13T10:00:00")
    sperre(lauf, start="2026-10-13T09:30:00+02:00")
    portfolio(profil="aggressiv", verarbeitet_bis="2026-10-08")
    p = laden("aggressiv")
    p["offene_orders"].append({"id": "O-0001", "art": "market", "aktion": "kauf", "typ": "ko",
                               "richtung": "long", "ticker": "KO-LONG-^GDAXI", "basiswert": "^GDAXI",
                               "einsatz": "100", "hebel": "5", "stop": "19000", "kursziel": None,
                               "erfasst": "2026-10-08T20:00:00+02:00", "journal_id": "J-20261008-01"})
    g.portfolio_speichern(p)
    quelle.konstant("^GDAXI", "2026-10-01", "2026-10-31", "20000")
    assert bewertung.main(["nachbuchen"]) == 0
    position = laden("aggressiv")["positionen"][0]
    k = Decimal("16000")
    for _ in range(4):  # Abschluss Fr, Sa, So, Mo
        k = (k * (1 + Decimal("0.04") / 365)).quantize(Decimal("1e-8"))
    assert Decimal(position["parameter"]["basispreis"]) == k
    assert position["parameter"]["barriere"] == position["parameter"]["basispreis"]


def test_ohne_portfolios_nichts_zu_tun(lauf, capsys):
    assert bewertung.main(["nachbuchen"]) == 0
    assert "nichts nachzubuchen" in capsys.readouterr().out
    assert bewertung.main(["bericht"]) == 0
    assert "noch nicht initialisiert" in (lauf / "ranking.md").read_text()


def test_ohne_sperre_abgelehnt(lauf):
    (lauf / "session.lock").unlink()
    portfolio()
    assert bewertung.main(["nachbuchen"]) == 2


def test_bericht_kennzahlen(lauf, quelle):
    portfolio(verarbeitet_bis="2026-10-11", startdatum="2026-10-12")
    quelle.kerze("EUNL.DE", "2026-10-13", 101, 101, 101, 101)
    quelle.kerze("EUNL.DE", "2026-10-14", 102, 102, 102, 102)
    assert bewertung.main(["nachbuchen"]) == 0
    assert bewertung.main(["bericht"]) == 0
    benchmark = g.csv_lesen(lauf / "data" / "benchmark.csv")
    assert [z["datum"] for z in benchmark] == ["2026-10-12", "2026-10-13", "2026-10-14"]
    # ausgewogen: 600 EUR ETF zu 100 -> 6 Anteile; 400 EUR Cash mit Zins (0,02 je Tag)
    assert benchmark[-1]["ausgewogen"] == str((6 * Decimal("102") + Decimal("400.06")).quantize(Decimal("0.01")))
    assert benchmark[-1]["aggressiv"] == "1020.00"
    text = (lauf / "ranking.md").read_text()
    assert "zu wenig Daten (3/60 Handelstage)" in text
    assert "| Portfoliowert | 1000,15 EUR |" in text
    assert "." not in text.split("| Portfoliowert")[1].split("\n")[0]  # Dezimalkomma statt Punkt
