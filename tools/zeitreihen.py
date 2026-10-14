"""Gemeinsame Hilfen für Auswertungen auf Kursdaten (Prognosen, Schattenbuch, Statistik, Labor).

Nur Lesen: Kurse kommen aus dem Kursprotokoll (data/kurse/) und den gespeicherten Tageskerzen (data/historie/), auf
Wunsch (`netz=True`) ergänzt über tools/kurse.py. Nichts davon bucht oder ändert den Spielstand.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import gemeinsam as g
import kurse
from gemeinsam import D

LUECKE_TAGE = 5  # so viele Kalendertage um einen Stichtag werden bei fehlender Kerze nach Ersatz abgesucht


def handelstag_nach(ticker: str, start: date, anzahl: int) -> date:
    """Der `anzahl`-te Handelstag der Börse des Tickers nach `start` (Kalender aus config/universum.json)."""
    tag = start
    for _ in range(max(0, anzahl)):
        tag = kurse.naechster_handelstag(ticker, tag)
    return tag


def kerzen(ticker: str, von: date, bis: date, netz: bool = False) -> dict[date, kurse.Kerze]:
    """Tageskerzen im Zeitraum; ohne Netz nur aus dem Speicher, mit Netz zusätzlich über kurse.historie."""
    if netz:
        try:
            kurse.historie(ticker, von, bis)
        except g.Fehler:
            pass  # Lücken meldet der Aufrufer; vorhandene Kerzen bleiben nutzbar
    return {d: k for d, k in kurse.gespeicherte_historie(ticker).items() if von <= d <= bis}


def kurs_am(ticker: str, tag: date, erwartet: Decimal | None = None, netz: bool = False) -> tuple[Decimal, str] | None:
    """Schlusskurs des Tages. Fehlt die Kerze (Lücke), gilt die ungünstigere Annahme.

    Ungünstiger heißt: Von der letzten Kerze davor und der ersten danach (je höchstens `LUECKE_TAGE` Tage entfernt) wird
    der Kurs genommen, der weiter vom `erwarteten` Kurs der Prognose entfernt liegt (ohne Erwartung: der niedrigere).
    Gibt (Kurs, Quelle) zurück, Quelle "kerze" oder "luecke"; None, wenn kein Ersatz vorhanden ist.
    """
    karte = kerzen(ticker, tag - timedelta(days=LUECKE_TAGE), tag + timedelta(days=LUECKE_TAGE), netz)
    if tag in karte:
        return karte[tag].close, "kerze"
    davor = [d for d in karte if d < tag]
    danach = [d for d in karte if d > tag]
    kandidaten = []
    if davor:
        kandidaten.append(karte[max(davor)].close)
    if danach:
        kandidaten.append(karte[min(danach)].close)
    if not kandidaten:
        return None
    if erwartet is not None:
        return max(kandidaten, key=lambda k: abs(k - erwartet)), "luecke"
    return min(kandidaten), "luecke"


def protokollkurs(ticker: str, ab: datetime, max_minuten: int = 120) -> tuple[Decimal, datetime] | None:
    """Erster protokollierter Kurs des Tickers ab `ab` (gleicher Tag, höchstens `max_minuten` später).

    Das ist der Kurs, den ein Werkzeug (kurse.py aktuell, Kauf, Ausführung) wirklich protokolliert hat; kein
    nachträglich abgeleiteter Wert und keiner vor `ab` (kein Backdating).
    """
    ab = ab.astimezone(g.TZ)
    zeilen = g.csv_lesen(kurse.kurs_protokoll_pfad(ab.date()))
    grenze = ab + timedelta(minutes=max_minuten)
    treffer = []
    for z in zeilen:
        if z["ticker"] != ticker:
            continue
        zeit = g.zeit_lesen(z["zeit"])
        if ab <= zeit <= grenze:
            treffer.append((zeit, D(z["kurs"])))
    if not treffer:
        return None
    zeit, kurs = min(treffer)
    return kurs, zeit


def letzter_schluss_vor(ticker: str, tag: date, netz: bool = False) -> Decimal | None:
    """Schlusskurs der letzten Kerze vor `tag` (höchstens 10 Kalendertage zurück)."""
    karte = kerzen(ticker, tag - timedelta(days=10), tag - timedelta(days=1), netz)
    return karte[max(karte)].close if karte else None
