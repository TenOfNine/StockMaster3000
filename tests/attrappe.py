"""Kursquelle für Tests: liefert vorgegebene Kurse, nie Netzwerk."""

from datetime import date, timedelta
from decimal import Decimal

from gemeinsam import D, KursFehler
from kurse import Kerze


class AttrappenQuelle:
    name = "attrappe"

    def __init__(self, uhr):
        self.uhr = uhr
        self.live = {}
        self.kerzen = {}
        self.marktkap = {}
        self.aufrufe = []

    # Vorgaben -------------------------------------------------------------
    def kurs(self, ticker, wert, zeit=None):
        self.live[ticker] = (D(wert), zeit)

    def kerze(self, ticker, datum, o, h=None, l=None, c=None, dividende=0, split=0):
        o = D(o)
        h = D(h) if h is not None else o
        l = D(l) if l is not None else o
        c = D(c) if c is not None else o
        tag = date.fromisoformat(datum) if isinstance(datum, str) else datum
        self.kerzen.setdefault(ticker, {})[tag] = Kerze(tag, o, h, l, c, D(dividende), D(split))

    def konstant(self, ticker, von, bis, wert, nur_werktage=True, ausser=()):
        tag = date.fromisoformat(von)
        ende = date.fromisoformat(bis)
        while tag <= ende:
            if (not nur_werktage or tag.weekday() < 5) and tag.isoformat() not in ausser:
                self.kerze(ticker, tag, wert)
            tag += timedelta(days=1)

    # Schnittstelle --------------------------------------------------------
    def aktuell(self, ticker):
        self.aufrufe.append(("aktuell", ticker))
        if ticker not in self.live:
            raise KursFehler(f"Keine Daten für {ticker} (Attrappe).")
        wert, zeit = self.live[ticker]
        return wert, zeit or self.uhr()

    def historie(self, ticker, von, bis):
        self.aufrufe.append(("historie", ticker, von, bis))
        return [k for d, k in sorted(self.kerzen.get(ticker, {}).items()) if von <= d <= bis]

    def marktkapitalisierung(self, ticker):
        return self.marktkap.get(ticker)
