"""AP1: Konfiguration vollständig und gleich regeln.md."""

import json
from decimal import Decimal
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

ERWARTET = {
    "defensiv": {"max_anteil_zertifikate": "0.10", "max_hebel": "3", "max_exposure": "1.2",
                 "max_einzelposition": "0.20", "min_cashquote": "0.10", "max_risiko_trade": "0.01",
                 "drawdown_stufe1": "-0.08", "drawdown_stufe2": "-0.15", "benchmark_etf_anteil": "0.30"},
    "ausgewogen": {"max_anteil_zertifikate": "0.30", "max_hebel": "5", "max_exposure": "2.0",
                   "max_einzelposition": "0.25", "min_cashquote": "0.05", "max_risiko_trade": "0.02",
                   "drawdown_stufe1": "-0.12", "drawdown_stufe2": "-0.20", "benchmark_etf_anteil": "0.60"},
    "aggressiv": {"max_anteil_zertifikate": "0.70", "max_hebel": "10", "max_exposure": "4.0",
                  "max_einzelposition": "0.35", "min_cashquote": "0.00", "max_risiko_trade": "0.05",
                  "drawdown_stufe1": "-0.20", "drawdown_stufe2": "-0.35", "benchmark_etf_anteil": "1.00"},
}


def lade(name):
    return json.loads((WURZEL / "config" / f"{name}.json").read_text(encoding="utf-8"))


def test_alle_config_dateien_lesbar():
    for name in ("profile", "universum", "kosten", "projekt"):
        assert isinstance(lade(name), dict)


def test_profile_vollstaendig_und_gleich_regeln():
    profile = lade("profile")["profile"]
    assert set(profile) == set(ERWARTET)
    for profil, werte in ERWARTET.items():
        assert set(profile[profil]) == set(werte), profil
        for schluessel, wert in werte.items():
            assert Decimal(profile[profil][schluessel]) == Decimal(wert), (profil, schluessel)


def test_kosten_gleich_regeln():
    kosten = lade("kosten")
    assert Decimal(kosten["spread"]["aktie"]) == Decimal("0.001")
    assert Decimal(kosten["spread"]["etf"]) == Decimal("0.001")
    assert Decimal(kosten["spread"]["ko"]) == Decimal("0.002")
    assert Decimal(kosten["spread"]["faktor"]) == Decimal("0.002")
    assert Decimal(kosten["gebuehr_je_order"]) == Decimal("1")
    assert Decimal(kosten["mindestorder"]) == Decimal("100")
    assert Decimal(kosten["cash_zins_pa"]) == Decimal("0.02")
    assert Decimal(kosten["ko_long_aufzinsung_pa"]) == Decimal("0.04")
    assert Decimal(kosten["ko_short_aufzinsung_pa"]) == Decimal("0")
    assert Decimal(kosten["faktor_kosten_pa"]) == Decimal("0.02")
    assert kosten["tage_je_jahr"] == 365
    assert Decimal(kosten["verlust_ohne_stop"]["aktie"]) == Decimal("0.2")
    assert Decimal(kosten["verlust_ohne_stop"]["ko"]) == Decimal("1")


def test_projekt_gleich_regeln():
    projekt = lade("projekt")
    assert Decimal(projekt["startkapital"]) == Decimal("1000")
    assert Decimal(projekt["portfolio_stopp"]) == Decimal("200")
    assert projekt["sperre_stunden"] == 6
    assert projekt["benchmark_ticker"] == "EUNL.DE"
    assert projekt["devisen_ticker"] == "EURUSD=X"
    assert set(projekt["auftraggeber"]) == {"auftraggeber-a", "auftraggeber-b"}
    assert projekt["sharpe_min_handelstage"] == 60


def test_universum_gleich_regeln():
    universum = lade("universum")
    assert set(universum["basiswerte"]) == {"^GDAXI", "^STOXX50E", "^GSPC", "^NDX", "GC=F", "BZ=F"}
    boersen = universum["boersen"]
    assert (boersen["xetra"]["oeffnung"], boersen["xetra"]["schluss"]) == ("09:00", "17:30")
    assert boersen["xetra"]["zeitzone"] == "Europe/Berlin"
    assert (boersen["nyse"]["oeffnung"], boersen["nyse"]["schluss"]) == ("09:30", "16:00")
    assert boersen["nyse"]["zeitzone"] == "America/New_York"
    assert (boersen["rohstoffe"]["oeffnung"], boersen["rohstoffe"]["schluss"]) == ("08:00", "22:00")
    for name, boerse in boersen.items():
        for feld in ("zeitzone", "oeffnung", "schluss", "handelstage", "waehrung", "feiertage"):
            assert feld in boerse, (name, feld)
    assert universum["basiswerte"]["^GDAXI"]["boerse"] == "xetra"
    assert universum["basiswerte"]["^STOXX50E"]["boerse"] == "xetra"
    assert universum["basiswerte"]["^GSPC"]["boerse"] == "nyse"
    assert universum["basiswerte"]["^NDX"]["boerse"] == "nyse"
    assert universum["basiswerte"]["GC=F"]["boerse"] == "rohstoffe"
    assert universum["basiswerte"]["BZ=F"]["boerse"] == "rohstoffe"
    assert Decimal(universum["aktien_als_basiswert"]["min_marktkapitalisierung"]) == Decimal("1e10")
    assert Decimal(universum["aktien"]["mindestkurs"]) == Decimal("1")
    assert universum["aktien"]["suffix_boerse"] == {".DE": "xetra"}
