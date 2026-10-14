#!/usr/bin/env python3
"""Mechanische Kontrollportfolios (Strategie-Labor L5): handeln ohne Claude, über denselben Buchungsweg.

Ein Kontrollportfolio ist ein normales Profil (config/profile.json) mit dem Eintrag `"kontrolle": {"<profil>": "<typ>"}`.
Ohne diesen Eintrag tut dieses Werkzeug nichts: Die Aktivierung entscheiden die Auftraggeber (regeln.md 7: ein
ergänztes Profil startet am Ergänzungstag mit 1.000 EUR). Typen:

- `passiv`: kauft einmal die Benchmark (ETF) unter echten Kosten und hält sie.
- `zufall`: Zufallshändler mit der Kauffrequenz, den Haltedauern und Positionsgrößen eines Claude-Portfolios
  (`vorbild`), zufällige Werte aus derselben Kandidatenliste (config/beobachtung.json). Die Zufallszahlen kommen aus
  Code (`random.Random("<seed>|<profil>|<tag>")`), Seed und Ziehung stehen im Protokoll data/kontrolle/<profil>.jsonl.
- `labor`: führt eine Strategie des Strategie-Labors (tools/labor) mit ihren Tagesdaten aus.

Jede Buchung läuft über buchen.kauf_ausfuehren/verkauf_ausfuehren und limits.pruefe_kauf wie bei Claude, unter der
Buchungssperre, zu protokollierten Kursen bei offenem Markt, mit einem mechanischen Journal-Eintrag
(journal/<datum>_mechanisch.md, Zeile "Mechanisch") und der Bemerkung "automatisch (Auslöser: Kontrollportfolio)".

    python tools/kontrolle.py status                 aktive Kontrollportfolios und Stand
    python tools/kontrolle.py tick [--json]          einmal ausführen (idempotent je Tag)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

import ausfuehrung
import bewertung
import buchen
import gemeinsam as g
import kurse
import limits
from gemeinsam import D, Fehler

TYPEN = ("passiv", "zufall", "labor")
EINSATZ_STUFEN = (1.0, 0.75, 0.5, 0.35, 0.25, 0.15, 0.1, 0.05)  # Einsatz wird verkleinert, bis alle Limits halten
EINS = Decimal("1")


def aktive_profile() -> dict[str, str]:
    """Kontrollportfolios, die konfiguriert sind und ein Portfolio haben."""
    return {p: t for p, t in g.kontrolle_profile().items() if p in g.vorhandene_profile()}


def parameter(profil: str, typ: str) -> dict:
    konfig = g.config("kontrolle")
    if typ not in TYPEN:
        raise Fehler(f"Unbekannter Typ '{typ}' für {profil} (erlaubt: {', '.join(TYPEN)}).")
    return {**konfig["standard"][typ], **konfig.get("profile", {}).get(profil, {})}


# --------------------------------------------------------------------------
# Protokoll (nur anhängen)


def protokoll_pfad(profil: str):
    return g.pfad("data", "kontrolle", f"{profil}.jsonl")


def protokollieren(profil: str, ereignis: str, **zusatz) -> None:
    datei = protokoll_pfad(profil)
    datei.parent.mkdir(parents=True, exist_ok=True)
    with datei.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"zeit": g.iso(g.jetzt()), "ereignis": ereignis, **zusatz}, ensure_ascii=False, sort_keys=True) + "\n")


def protokoll_lesen(profil: str) -> list[dict]:
    datei = protokoll_pfad(profil)
    if not datei.exists():
        return []
    return [json.loads(z) for z in datei.read_text(encoding="utf-8").splitlines() if z.strip()]


def ereignis_am(profil: str, tag: date, ereignis: str) -> dict | None:
    return next((e for e in reversed(protokoll_lesen(profil)) if e["ereignis"] == ereignis and e.get("tag") == tag.isoformat()), None)


# --------------------------------------------------------------------------
# Journal (mechanisch)


def journal_eintrag(profil: str, ticker: str, aktion: str, typ: str, regel: str, zeit: datetime, seed: str = "") -> str:
    """Schreibt den mechanischen Journal-Eintrag zu einer Order und gibt die ID zurück (Zeit = Kurszeit der Order)."""
    zeit = zeit.astimezone(g.TZ).replace(second=0, microsecond=0)
    tag = zeit.date()
    belegt = {int(i.rsplit("-", 1)[1]) for i in g.journal_eintraege() if i.startswith(f"J-{tag:%Y%m%d}-")}
    nummer = next(n for n in range(1, 100) if n not in belegt)
    jid = f"J-{tag:%Y%m%d}-{nummer:02d}"
    datei = g.pfad("journal", f"{tag.isoformat()}_mechanisch.md")
    datei.parent.mkdir(parents=True, exist_ok=True)
    kopf = "" if datei.exists() else f"# Journal {tag.isoformat()} (mechanisch)\n\n"
    text = (f"{kopf}### {jid} | {profil} | {ticker}\n"
            f"- Zeit: {zeit:%Y-%m-%d %H:%M}\n"
            f"- Aktion: {aktion} (mechanisch)\n"
            f"- Mechanisch: ja, Kontrollportfolio vom Typ {typ}; kein Claude beteiligt{'; Seed ' + seed if seed else ''}\n"
            f"- These: Mechanische Regel statt Einschätzung: {regel}\n"
            f"- Szenarien: entfällt (mechanisch)\n"
            f"- Katalysator und Zeithorizont: entfällt (mechanisch)\n"
            f"- Einstieg, Stop, Kursziel: protokollierter Kurs bei offenem Markt, kein Stop, kein Kursziel\n"
            f"- Positionsgröße und Risikorechnung: durch die Regel und limits.pruefe_kauf bestimmt\n"
            f"- Quellen: tools/kurse.py (protokollierter Kurs)\n"
            f"- Unsicherheiten: Kontrolle ohne eigene Einschätzung; Zufall und Kosten bestimmen das Ergebnis\n\n")
    with datei.open("a", encoding="utf-8") as f:
        f.write(text)
    return jid


# --------------------------------------------------------------------------
# Regeln der drei Typen (reine Planung: was soll heute geschehen?)


def vorbild_statistik(vorbild: str) -> dict:
    """Kauffrequenz, Haltedauern (Tage) und Einsatzanteile (am Portfoliowert) des Claude-Portfolios."""
    if vorbild not in g.vorhandene_profile():
        return {"kaeufe": 0, "tage": 1, "dauern": [], "anteile": []}  # kein Vorbild: Vorgaben aus der Konfiguration
    nav = {z["datum"]: D(z["portfoliowert"]) for z in bewertung.nav_lesen(vorbild)}
    zeilen = g.trades_lesen(vorbild)
    kaeufe = [z for z in zeilen if z["aktion"] == "kauf" and z["grund"] == "order"]
    erste_kauf, letzte_verkauf = {}, {}
    for z in zeilen:
        if z["position_id"] and z["aktion"] == "kauf":
            erste_kauf.setdefault(z["position_id"], g.zeit_lesen(z["zeit"]))
        if z["position_id"] and z["aktion"] == "verkauf":
            letzte_verkauf[z["position_id"]] = g.zeit_lesen(z["zeit"])
    offen = {p["id"] for p in g.portfolio_laden(vorbild)["positionen"]}
    dauern = [max(1, (letzte_verkauf[pid] - erste_kauf[pid]).days) for pid in letzte_verkauf
              if pid in erste_kauf and pid not in offen]
    kapital = D(g.projekt()["startkapital"])
    anteile = [float(abs(D(z["betrag_eur"])) / nav.get(g.zeit_lesen(z["zeit"]).date().isoformat(), kapital)) for z in kaeufe]
    return {"kaeufe": len(kaeufe), "tage": max(1, len(nav)), "dauern": dauern, "anteile": anteile}


def zufall_entscheidung(profil: str, cfg: dict, tag: date, kandidaten: list[tuple[str, str]]) -> dict:
    """Die Ziehung des Tages: kaufen?, was, wie viel, wie lange halten. Feste Reihenfolge der Ziehungen = reproduzierbar."""
    stat = vorbild_statistik(cfg["vorbild"])
    genug = stat["kaeufe"] >= int(cfg["min_beobachtet"])
    p = min(1.0, stat["kaeufe"] / stat["tage"]) if genug else float(cfg["kaufwahrscheinlichkeit"])
    rng = random.Random(f"{cfg['seed']}|{profil}|{tag.isoformat()}")
    wurf = rng.random()
    ticker, typ = rng.choice(sorted(kandidaten))
    anteil = rng.choice(stat["anteile"]) if len(stat["anteile"]) >= int(cfg["min_beobachtet"]) else float(cfg["einsatz_anteil"])
    dauer = rng.choice(stat["dauern"]) if len(stat["dauern"]) >= int(cfg["min_beobachtet"]) else int(cfg["haltedauer_tage"])
    return {"kaufen": wurf < p, "wurf": round(wurf, 6), "wahrscheinlichkeit": round(p, 6), "ticker": ticker, "typ": typ,
            "einsatz_anteil": round(anteil, 6), "haltedauer_tage": int(dauer), "seed": f"{cfg['seed']}|{profil}|{tag.isoformat()}",
            "vorbild": cfg["vorbild"], "beobachtet": {"kaeufe": stat["kaeufe"], "tage": stat["tage"], "dauern": len(stat["dauern"])}}


def kandidatenliste(namen: list[str]) -> list[tuple[str, str]]:
    """Kandidaten wie im Screener (config/beobachtung.json), nur an erlaubten Börsen: (Ticker, Typ aktie/etf)."""
    listen = g.config("beobachtung")["listen"]
    ergebnis = {}
    for name in namen:
        for ticker in listen.get(name, {}).get("ticker", []):
            try:
                kurse.boerse_von(ticker)
            except Fehler:
                continue
            ergebnis[ticker] = "etf" if name.startswith("etf") else "aktie"
    return sorted(ergebnis.items())


def labor_ziel(cfg: dict, heute: date) -> tuple[list | None, str]:
    """Zielpositionen der Labor-Strategie nach Wiedergabe der Tagesdaten bis gestern; (None, Grund) wenn nicht möglich."""
    from labor import engine
    from labor.daten import Panel
    from labor.strategien import REGISTER

    strategie = REGISTER[cfg["strategie"]](**cfg["parameter"])
    try:
        panel = Panel.aus_cache(list(strategie.tickers))
    except Fehler as exc:
        return None, str(exc)
    vortag = max(d for d in (heute - timedelta(days=k) for k in range(1, 8)) if kurse.ist_handelstag(strategie.tickers[0], d))
    if panel.tage[-1] < vortag:
        return None, f"Labor-Daten veraltet (letzter Tag {panel.tage[-1]}, erwartet {vortag})"
    ziel = None
    for p in range(panel.punkte()):
        if ("close" if p % 2 else "open") in strategie.punkte:
            z = strategie.entscheiden(engine.Sicht(panel, p))
            if z is not None:
                ziel = z
    return ziel, ""


# --------------------------------------------------------------------------
# Ausführung


class _Tag:
    def __init__(self, profil: str, typ: str, portfolio: dict, jetzt: datetime, bericht: dict):
        self.profil, self.typ, self.portfolio, self.jetzt, self.bericht = profil, typ, portfolio, jetzt, bericht
        self.erledigt = True       # false, solange eine Aktion wegen geschlossener Börse oder fehlendem Kurs wartet
        self.lauf = g.Buchungslauf(portfolio)
        self.quotes: dict = {}
        self.fx = None

    def kurs(self, ticker: str):
        if ticker in self.quotes:
            return self.quotes[ticker]
        if not kurse.markt_offen(ticker, self.jetzt):
            return None
        try:
            self.quotes[ticker] = kurse.aktuell([ticker])[0]
        except Fehler as exc:
            self.bericht["fehler"].append({"profil": self.profil, "ticker": ticker, "text": str(exc)[:300]})
            return None
        return self.quotes[ticker]

    def markt(self, ticker: str) -> limits.Markt:
        tickers = {p["basiswert"] for p in self.portfolio["positionen"]} | {ticker}
        for t in tickers - set(self.quotes):  # gehaltene Werte bei geschlossener Börse: letzter protokollierter Kurs
            self.quotes[t] = kurse.aktuell([t])[0]
        if any(kurse.waehrung(t) == "USD" for t in tickers) and self.fx is None:
            self.fx = kurse.devisenkurs_aktuell()
        return ausfuehrung._markt(self.portfolio, self.quotes, self.fx, ticker, self.jetzt.date())

    def nav(self, ticker: str) -> Decimal:
        return limits.portfolio_bewerten(self.portfolio, self.markt(ticker))["nav"]

    def kaufen(self, ticker: str, typ: str, anteil: float, regel: str, seed: str = "", haltedauer: int | None = None) -> bool:
        q = self.kurs(ticker)
        if q is None:
            self.erledigt = False
            return False
        markt = self.markt(ticker)
        nav = limits.portfolio_bewerten(self.portfolio, markt)["nav"]
        mindest = D(g.kosten()["mindestorder"])
        plan = kennzahlen = None
        for stufe in EINSATZ_STUFEN:
            einsatz = g.geld(nav * D(str(anteil)) * D(str(stufe)))
            if einsatz < mindest:
                break
            kandidat = limits.kaufplan(typ, "long", ticker, einsatz, q.kurs, stop=None, kursziel=None, kauftag=q.zeit.date())
            verstoesse, kz = limits.pruefe_kauf(self.portfolio, kandidat, markt)
            if not verstoesse:
                plan, kennzahlen = kandidat, kz
                break
        if plan is None:
            text = f"{self.profil}: kein Kauf von {ticker} (Anteil {anteil}); auch der kleinste Einsatz verletzt Limits oder die Mindestorder"
            protokollieren(self.profil, "uebersprungen", tag=self.jetzt.date().isoformat(), text=text)
            self.bericht["uebersprungen"].append({"profil": self.profil, "text": text})
            return False
        jid = journal_eintrag(self.profil, ticker, "Kauf", self.typ, regel, q.zeit, seed)
        order = {"id": g.naechste_id(self.portfolio, "order"), "journal_id": jid}
        zusatz = g.automatisch_text("Kontrollportfolio", f"{self.typ}: {regel}")
        position = buchen.kauf_ausfuehren(self.lauf, order, plan, markt, q.zeit, "kurse", g.iso(q.zeit), kennzahlen, zusatz=zusatz)
        if haltedauer is not None:
            position["kontrolle"] = {"typ": self.typ, "verkauf_ab": (q.zeit.date() + timedelta(days=haltedauer)).isoformat()}
        protokollieren(self.profil, "kauf", tag=self.jetzt.date().isoformat(), ticker=ticker, journal_id=jid, regel=regel,
                       einsatz=str(plan.einsatz))
        return True

    def verkaufen(self, position: dict, regel: str) -> bool:
        q = self.kurs(position["basiswert"])
        if q is None:
            self.erledigt = False
            return False
        jid = journal_eintrag(self.profil, position["ticker"], "Verkauf", self.typ, regel, q.zeit)
        eurusd = ausfuehrung._fx_fuer(position["basiswert"], self.fx or (kurse.devisenkurs_aktuell()
                                      if bewertung.braucht_fx(position["basiswert"]) else None))
        zusatz = g.automatisch_text("Kontrollportfolio", f"{self.typ}: {regel}")
        buchen.verkauf_ausfuehren(self.lauf, position, EINS, q.kurs, eurusd, q.zeit, q.zeit.date(), "kurse", g.iso(q.zeit),
                                  "order", order_id=g.naechste_id(self.portfolio, "order"), journal_id=jid, zusatz=zusatz)
        protokollieren(self.profil, "verkauf", tag=self.jetzt.date().isoformat(), ticker=position["ticker"], journal_id=jid, regel=regel)
        return True


def _passiv(t: _Tag, cfg: dict) -> None:
    if any(e["ereignis"] == "kauf" for e in protokoll_lesen(t.profil)) or t.portfolio["positionen"]:
        return  # gekauft; gehalten wird bis zum Ende
    t.kaufen(cfg["ticker"], "etf", float(cfg["einsatz_anteil"]), f"Benchmark {cfg['ticker']} kaufen und halten")


def _zufall(t: _Tag, cfg: dict) -> None:
    heute = t.jetzt.date()
    entscheidung = ereignis_am(t.profil, heute, "entscheidung")
    if entscheidung is None:
        kandidaten = kandidatenliste(cfg["listen"])
        if not kandidaten:
            raise Fehler("Die Kandidatenliste des Zufallshändlers ist leer (config/beobachtung.json).")
        entscheidung = {"tag": heute.isoformat(), **zufall_entscheidung(t.profil, cfg, heute, kandidaten)}
        protokollieren(t.profil, "entscheidung", **entscheidung)
    for position in list(t.portfolio["positionen"]):
        ab = (position.get("kontrolle") or {}).get("verkauf_ab")
        if ab and date.fromisoformat(ab) <= heute:
            t.verkaufen(position, f"Haltedauer erreicht (zufällig gezogen, verkauf_ab {ab})")
    if entscheidung["kaufen"] and not ereignis_am(t.profil, heute, "kauf") \
            and not any(p["basiswert"] == entscheidung["ticker"] for p in t.portfolio["positionen"]):
        t.kaufen(entscheidung["ticker"], entscheidung["typ"], entscheidung["einsatz_anteil"],
                 f"Zufallskauf (Wurf {entscheidung['wurf']} < {entscheidung['wahrscheinlichkeit']}, Haltedauer "
                 f"{entscheidung['haltedauer_tage']} Tage)", seed=entscheidung["seed"], haltedauer=entscheidung["haltedauer_tage"])


def _labor(t: _Tag, cfg: dict) -> None:
    ziel, grund = labor_ziel(cfg, t.jetzt.date())
    if ziel is None:
        if grund:
            t.bericht["uebersprungen"].append({"profil": t.profil, "text": grund})
            t.erledigt = False
        return
    soll = {z.ticker: z.gewicht for z in ziel}
    for z in ziel:
        if z.typ not in ("etf", "aktie") or z.richtung != "long":
            raise Fehler(f"Die Labor-Strategie verlangt {z.typ}/{z.richtung}; Kontrollportfolios handeln nur Aktien und ETFs long.")
    for position in list(t.portfolio["positionen"]):
        if position["basiswert"] not in soll:
            t.verkaufen(position, f"Labor-Strategie {cfg['strategie']}: Ziel enthält {position['basiswert']} nicht")
    for z in ziel:
        gehalten = any(p["basiswert"] == z.ticker for p in t.portfolio["positionen"])
        if not gehalten and z.gewicht > 0:
            t.kaufen(z.ticker, z.typ, z.gewicht * float(cfg["einsatz_anteil"]), f"Labor-Strategie {cfg['strategie']}: Ziel enthält {z.ticker}")


REGELN = {"passiv": _passiv, "zufall": _zufall, "labor": _labor}


def _profil(profil: str, typ: str, jetzt: datetime, bericht: dict) -> None:
    portfolio = g.portfolio_laden(profil)
    if portfolio.get("status") != "aktiv":
        return
    heute = jetzt.date()
    if date.fromisoformat(portfolio["verarbeitet_bis"]) < heute - timedelta(days=1):
        bericht["uebersprungen"].append({"profil": profil, "text": "Nachbuchung steht aus; die Kontrollregel wartet."})
        return
    if ereignis_am(profil, heute, "tag_erledigt"):
        return
    t = _Tag(profil, typ, portfolio, jetzt, bericht)
    REGELN[typ](t, parameter(profil, typ))
    if t.lauf.zeilen:
        zeilen = list(t.lauf.zeilen)
        t.lauf.speichern()
        bericht["ausgefuehrt"] += [{"profil": profil, "trade_id": z["trade_id"], "aktion": z["aktion"], "ticker": z["ticker"]}
                                   for z in zeilen]
        bericht["meldungen"] += t.lauf.meldungen
    if t.erledigt:
        protokollieren(profil, "tag_erledigt", tag=heute.isoformat())


def tick(jetzt: datetime | None = None) -> dict:
    jetzt = jetzt or g.jetzt()
    bericht: dict = {"zeit": g.iso(jetzt), "ausgefuehrt": [], "uebersprungen": [], "fehler": [], "meldungen": [], "hinweis": ""}
    aktiv = aktive_profile()
    if not g.spiel_lesen().get("startdatum") or not aktiv:
        bericht["hinweis"] = "Keine aktiven Kontrollportfolios."
        return bericht
    einst = ausfuehrung.einstellungen()
    for profil, typ in aktiv.items():
        try:
            with g.buchungssperre(einst["sperre_wartezeit_sekunden"]):
                _profil(profil, typ, jetzt, bericht)
        except g.BuchungssperreBelegt:
            bericht["uebersprungen"].append({"profil": profil, "text": "Buchungssperre belegt, nächster Versuch folgt."})
        except Fehler as exc:
            bericht["fehler"].append({"profil": profil, "text": str(exc)[:300]})
    return bericht


def status() -> list[str]:
    zeilen = []
    konfig = g.kontrolle_profile()
    if not konfig:
        return ["Keine Kontrollportfolios konfiguriert (config/profile.json, Schlüssel \"kontrolle\")."]
    for profil, typ in konfig.items():
        vorhanden = profil in g.vorhandene_profile()
        letzte = next((e for e in reversed(protokoll_lesen(profil)) if e["ereignis"] in ("kauf", "verkauf")), None)
        zeilen.append(f"{profil}: Typ {typ}, {'Portfolio vorhanden' if vorhanden else 'noch kein Portfolio'}"
                      + (f", letzte Buchung {letzte['zeit'][:16]} ({letzte['ereignis']} {letzte.get('ticker', '')})" if letzte else ""))
    return zeilen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Mechanische Kontrollportfolios (ohne Claude).")
    unter = parser.add_subparsers(dest="befehl", required=True)
    unter.add_parser("status")
    p = unter.add_parser("tick")
    p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.befehl == "status":
            print("\n".join(status()))
        else:
            bericht = tick()
            print(json.dumps(bericht, ensure_ascii=False) if args.json else
                  "\n".join(bericht["meldungen"] + [f"Übersprungen: {u['text']}" for u in bericht["uebersprungen"]]
                            + [f"Fehler: {f['text']}" for f in bericht["fehler"]] + ([bericht["hinweis"]] if bericht["hinweis"] else [])))
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
