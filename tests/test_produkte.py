"""AP3: Synthetische Zertifikate nach regeln.md Abschnitt 4."""

from datetime import date
from decimal import Decimal

import pytest

import produkte as p
from gemeinsam import Fehler


def test_basispreis_long_und_short(projekt):
    assert p.ko_basispreis("long", "20000", "5") == Decimal("16000")
    assert p.ko_basispreis("short", "20000", "5") == Decimal("24000")
    assert p.ko_basispreis("long", "100", "10") == Decimal("90")
    with pytest.raises(Fehler):
        p.ko_basispreis("long", "100", "1")


def test_ausgabe_wert_und_hebel(projekt):
    wert, parameter = p.ausgabe("ko", "long", "20000", hebel="5")
    assert wert == Decimal("4000")
    assert parameter["barriere"] == parameter["basispreis"] == Decimal("16000")
    assert p.ko_hebel("long", "20000", parameter["basispreis"]) == Decimal("5")
    wert, parameter = p.ausgabe("ko", "short", "20000", hebel="4")
    assert wert == Decimal("5000")
    assert p.ko_hebel("short", "20000", parameter["basispreis"]) == Decimal("4")


def test_hebelberechnung_nach_kursbewegung(projekt):
    # Long K=16000: S=18000 -> 18000/2000 = 9; S=24000 -> 3
    assert p.ko_hebel("long", "18000", "16000") == Decimal("9")
    assert p.ko_hebel("long", "24000", "16000") == Decimal("3")
    assert p.ko_hebel("short", "22000", "24000") == Decimal("11")
    assert p.ko_hebel("long", "15000", "16000") is None


def test_aufzinsung_ueber_wochenende(projekt):
    k = Decimal("16000")
    taeglich = k
    for _ in range(3):  # Freitag, Samstag, Sonntag
        taeglich = p.ko_aufzinsen("long", taeglich, 1)
    am_stueck = p.ko_aufzinsen("long", k, 3)
    erwartet = k * (1 + Decimal("0.04") / 365) ** 3
    assert abs(taeglich - erwartet) < Decimal("0.0000001")
    assert abs(am_stueck - erwartet) < Decimal("0.0000001")
    assert am_stueck > k
    # Short: konstant
    assert p.ko_aufzinsen("short", Decimal("24000"), 3) == Decimal("24000")


def test_knockout_long_durch_tagestief(projekt):
    assert p.ko_ausgeknockt("long", "16000", tief="16000", hoch="17000") is True
    assert p.ko_ausgeknockt("long", "16000", tief="15999", hoch="17000") is True
    assert p.ko_ausgeknockt("long", "16000", tief="16000.01", hoch="17000") is False


def test_knockout_short_durch_tageshoch(projekt):
    assert p.ko_ausgeknockt("short", "24000", tief="20000", hoch="24000") is True
    assert p.ko_ausgeknockt("short", "24000", tief="20000", hoch="23999.99") is False


def test_ko_wert_nie_negativ(projekt):
    assert p.ko_wert("long", "15000", "16000") == 0
    assert p.ko_wert("short", "25000", "24000") == 0


def test_faktor_nie_negativ(projekt):
    # Faktor 10 long, Basiswert -15 %: 1 + 10*(-0,15) < 0 -> 0
    assert p.faktor_fortschreiben("long", 10, "100", "100", "85") == 0
    assert p.faktor_fortschreiben("short", 10, "100", "100", "115") == 0


def test_faktor_tagesformel(projekt):
    # 3x long, +2 %: 100 * (1 + 0,06 - 0,02/365)
    wert = p.faktor_fortschreiben("long", 3, "100", "100", "102")
    assert wert == (Decimal("100") * (1 + Decimal("0.06") - Decimal("0.02") / 365)).quantize(Decimal("1e-8"))
    # Short: -F
    wert = p.faktor_fortschreiben("short", 2, "100", "100", "101")
    assert wert == (Decimal("100") * (1 - Decimal("0.02") - Decimal("0.02") / 365)).quantize(Decimal("1e-8"))
    # Kosten je Kalendertag (Wochenende: 3)
    wert = p.faktor_fortschreiben("long", 2, "100", "100", "100", kostentage=3)
    assert wert == (Decimal("100") * (1 - 3 * Decimal("0.02") / 365)).quantize(Decimal("1e-8"))


def test_faktor_verkauf_innerhalb_des_tages(projekt):
    _, parameter = p.ausgabe("faktor", "long", "200", faktor=2, kauftag=date(2026, 10, 12))
    position = {"typ": "faktor", "richtung": "long", "parameter": parameter}
    # Verkauf am Kauftag: R vom Ausführungskurs bis Verkaufskurs, keine Kosten
    assert p.wert_je_stueck(position, "210", date(2026, 10, 12)) == Decimal("110")


def test_aktien_nur_long(projekt):
    with pytest.raises(Fehler):
        p.ausgabe("aktie", "short", "100")
