#!/usr/bin/env python3
"""Erzeugt ein Demo-Datenverzeichnis (Spielstand) mit simulierten Kursen.

Nur für Entwicklung, Tests und Vorführung der Web-UI. Alle Buchungen laufen
über die echten Werkzeuge in tools/ (init, session, buchen, bewertung,
termine, pruefe); nur die Kursquelle und die Uhr sind simuliert. Das
Ergebnis ist ein Datenverzeichnis wie im Betrieb (eigenes, lokales Git ohne
Remote) und gelangt nie in das Framework-Repository.

    python webui/demo/demo_daten.py --ziel /tmp/stockmaster-demo --tage 100
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import random
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

QUELLE_REPO = Path(__file__).resolve().parents[2]
KENNUNGEN = ("auftraggeber-a", "auftraggeber-b")

# Ticker, Startkurs, Tagesvolatilität, Drift
WERTE = {
    "EUNL.DE": (102.0, 0.008, 0.0004),
    "EURUSD=X": (1.10, 0.003, 0.0),
    "SAP.DE": (238.0, 0.016, 0.0006),
    "SIE.DE": (204.0, 0.015, 0.0004),
    "ALV.DE": (342.0, 0.011, 0.0003),
    "MUV2.DE": (520.0, 0.010, 0.0002),
    "AAPL": (228.0, 0.016, 0.0005),
    "MSFT": (455.0, 0.014, 0.0005),
    "NVDA": (178.0, 0.028, 0.0010),
    "JNJ": (162.0, 0.009, 0.0001),
    "^GDAXI": (24150.0, 0.011, 0.0003),
    "^GSPC": (6480.0, 0.009, 0.0004),
    "^NDX": (23400.0, 0.013, 0.0005),
    "GC=F": (3380.0, 0.010, 0.0003),
}

IDEEN = {
    "defensiv": [("etf", "EUNL.DE", "Breite Marktbasis über den MSCI World statt Einzelwertrisiko"),
                 ("aktie", "ALV.DE", "Stabile Ertragslage und hohe Dividendenrendite im Versicherungssektor"),
                 ("aktie", "MUV2.DE", "Rückversicherer mit Preissetzungsmacht nach der Erneuerungsrunde"),
                 ("aktie", "JNJ", "Defensiver Gesundheitswert mit planbarem Cashflow")],
    "ausgewogen": [("aktie", "SAP.DE", "Cloud-Umsatz wächst stärker als erwartet, Margen steigen"),
                   ("aktie", "SIE.DE", "Automatisierungsnachfrage zieht an, Auftragseingang über Vorjahr"),
                   ("aktie", "MSFT", "KI-Erlöse im Cloud-Geschäft stützen das Wachstum"),
                   ("aktie", "AAPL", "Produktzyklus und Dienstleistungsumsatz tragen die Bewertung"),
                   ("etf", "EUNL.DE", "Beta-Baustein zur Annäherung an die Benchmark")],
    "aggressiv": [("ko", "^GDAXI", "Kurzfristiges Momentum im DAX nach Ausbruch über die Seitwärtsrange"),
                  ("faktor", "^NDX", "Halbleiter-Stärke treibt den Nasdaq 100"),
                  ("aktie", "NVDA", "Rechenzentrums-Nachfrage bleibt über dem Angebot"),
                  ("ko", "GC=F", "Gold als Absicherung gegen Realzinsrückgang"),
                  ("ko", "^GSPC", "Breite Erholung im S&P 500 nach Rücksetzer")],
}


class SimulierteQuelle:
    """Kursquelle mit vorab erzeugten Tageskerzen (zufällige Pfade, fester Seed)."""

    name = "demo"

    def __init__(self, uhr, start: date, ende: date, seed: int):
        import kurse

        self.uhr = uhr
        self.kerzen: dict[str, dict[date, kurse.Kerze]] = {}
        zufall = random.Random(seed)
        for ticker, (kurs, vola, drift) in WERTE.items():
            reihe = {}
            schluss = kurs
            tag = start - timedelta(days=40)
            while tag <= ende + timedelta(days=5):
                if kurse.ist_handelstag(ticker, tag):
                    luecke = zufall.gauss(0, vola * 0.35)
                    eroeffnung = schluss * (1 + luecke)
                    neu = eroeffnung * (1 + zufall.gauss(drift, vola))
                    spanne = abs(zufall.gauss(0, vola * 0.6))
                    hoch = max(eroeffnung, neu) * (1 + spanne)
                    tief = min(eroeffnung, neu) * (1 - spanne)
                    stellen = 4 if ticker == "EURUSD=X" else 2
                    dividende = 0
                    if ticker == "ALV.DE" and tag.month == 7 and tag.day in (8, 9, 10) and not reihe.get("_div"):
                        dividende, reihe["_div"] = 15.40, True
                    reihe[tag] = kurse.Kerze(tag, *(Decimal(str(round(w, stellen))) for w in
                                                    (eroeffnung, hoch, tief, neu)),
                                             dividende=Decimal(str(dividende)), split=Decimal("0"))
                    schluss = neu
                tag += timedelta(days=1)
            reihe.pop("_div", None)
            self.kerzen[ticker] = reihe

    def aktuell(self, ticker):
        jetzt = self.uhr()
        heute = jetzt.date()
        reihe = self.kerzen[ticker]
        if heute in reihe:
            k = reihe[heute]
            # Innerhalb der Tageskerze: Mischung aus Eröffnung und Schluss nach Uhrzeit
            anteil = min(1.0, max(0.0, (jetzt.hour + jetzt.minute / 60 - 9) / 9))
            wert = k.open + (k.close - k.open) * Decimal(str(round(anteil, 3)))
            wert = min(k.high, max(k.low, wert))
            return wert.quantize(Decimal("0.0001")), jetzt - timedelta(minutes=1)
        vorher = max(d for d in reihe if d < heute)
        return reihe[vorher].close, jetzt - timedelta(hours=12)

    def historie(self, ticker, von, bis):
        heute = self.uhr().date()
        return [k for d, k in sorted(self.kerzen[ticker].items()) if von <= d <= min(bis, heute)]

    def marktkapitalisierung(self, ticker):
        return Decimal("2.5e12")


class Uhr:
    def __init__(self):
        self.zeit = None

    def stellen(self, tag: date, uhrzeit: str):
        import gemeinsam as g

        stunde, minute = map(int, uhrzeit.split(":"))
        self.zeit = datetime(tag.year, tag.month, tag.day, stunde, minute, tzinfo=g.TZ)
        os.environ["GIT_AUTHOR_DATE"] = os.environ["GIT_COMMITTER_DATE"] = self.zeit.isoformat()

    def __call__(self):
        return self.zeit


def git(ziel: Path, *argumente):
    subprocess.run(["git", *argumente], cwd=ziel, check=True, capture_output=True)


def still(funktion, *argumente):
    puffer_aus, puffer_err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(puffer_aus), contextlib.redirect_stderr(puffer_err):
        code = funktion(*argumente)
    return code, puffer_aus.getvalue() + puffer_err.getvalue()


def vorbereiten(ziel: Path) -> None:
    """Leeres Datenverzeichnis aus der Vorlage des Frameworks (wie beim ersten Containerstart)."""
    if ziel.exists():
        shutil.rmtree(ziel)
    import datenverzeichnis

    datenverzeichnis.einrichten(ziel)
    (ziel / "DEMO.md").write_text(
        "# Demo-Arbeitsbereich\n\nSimulierte Kurse, erzeugt mit webui/demo/demo_daten.py. Kein echtes Spiel.\n",
        encoding="utf-8")


def demo_news(g, jetzt: datetime, start: date) -> None:
    """Einige erfundene, klar als Demo gekennzeichnete Meldungen im Format von tools/news.py."""
    import json as _json

    meldungen = [
        ("^GDAXI", "Demo: DAX schließt fester", "Simulierte Meldung für die Vorführung der Web-UI."),
        ("SAP.DE", "Demo: Softwarewerte gefragt", "Simulierte Meldung, kein echter Inhalt."),
        ("EURUSD=X", "Demo: Euro stabil zum Dollar", "Simulierte Meldung zur Geldpolitik."),
        ("GC=F", "Demo: Goldpreis seitwärts", "Simulierte Rohstoffmeldung."),
        ("NVDA", "Demo: Chipwerte im Fokus", "Simulierte Meldung aus den USA."),
    ]
    zeilen = []
    for i, (ticker, titel, text) in enumerate(meldungen):
        zeit = (jetzt - timedelta(hours=3 * i + 1)).isoformat()
        zeilen.append(_json.dumps({"id": f"N-demo{i:08d}", "abgerufen": jetzt.isoformat(), "zeit": zeit, "quelle": "demo",
                                   "quelle_name": "Demo-Feed", "titel": titel, "kurztext": text,
                                   "link": f"https://example.org/demo/news-{i}", "ticker": [ticker]}, ensure_ascii=False))
    g.text_anhaengen(g.pfad("news", f"{jetzt:%Y-%m}.jsonl"), "\n".join(zeilen) + "\n")


def strategie_text(profil: str) -> str:
    texte = {
        "defensiv": ("Kapitalerhalt mit leichter Mehrrendite gegen 30/70", "Breite ETFs und Qualitätsaktien, "
                     "Zertifikate nur ausnahmsweise mit niedrigem Hebel"),
        "ausgewogen": ("Rendite über der 60/40-Benchmark bei kontrolliertem Drawdown", "Qualitätsaktien aus "
                       "Europa und den USA, ergänzt um den MSCI World"),
        "aggressiv": ("Deutliche Mehrrendite gegen den MSCI World", "Trendfolge mit Knock-outs und "
                      "Faktor-Zertifikaten auf Indizes, dazu wachstumsstarke Einzelwerte"),
    }
    ziel, ansatz = texte[profil]
    return (f"# Anlagerichtlinie {profil.capitalize()} (Demo)\n\n## Ziel\n{ziel}.\n\n## Ausgangsstrategie\n"
            f"{ansatz}. Positionsgröße strikt nach Risikobudget; Stops auf den Basiswert.\n\n"
            "## Änderungshistorie\n| Datum | Anlass | Änderung | Prüfkriterium |\n| --- | --- | --- | --- |\n")


def journal_eintrag(jid, profil, typ, ticker, zeit, these, einsatz, stop, ziel, kurs, hebel=None) -> str:
    art = {"aktie": "Aktie", "etf": "ETF", "ko": f"Knock-out long, Hebel {hebel}",
           "faktor": f"Faktor long, Faktor {hebel}"}[typ]
    bull = random.choice((25, 30, 35))
    bear = random.choice((20, 25, 30))
    return (f"\n### {jid} | {profil} | {ticker}\n"
            f"- Zeit: {zeit:%Y-%m-%d %H:%M}\n"
            f"- Aktion: Kauf, {art}\n"
            f"- These: {these}.\n"
            f"- Szenarien: Bull {bull} % (Ausbruch über das Hoch) / Base {100 - bull - bear} % (Seitwärts mit "
            f"leichtem Aufwärtstrend) / Bear {bear} % (Rücksetzer bis zum Stop)\n"
            f"- Katalysator und Zeithorizont: Quartalszahlen und Makrodaten, 4 bis 8 Wochen\n"
            f"- Einstieg, Stop, Kursziel: ca. {kurs:.2f} / {stop:.2f} / {ziel:.2f} (Basiswert)\n"
            f"- Positionsgröße und Risikorechnung: Einsatz {einsatz} EUR, Verlust bis Stop laut "
            f"tools/limits.py innerhalb des Risikobudgets, Kosten 2 Gebühren plus Spread\n"
            f"- Quellen: https://example.org/demo/{ticker.lower().replace('^', '')}, {zeit:%Y-%m-%d} (Demo)\n"
            f"- Unsicherheiten: simulierte Demo-Daten; Zinsentscheid und Konjunkturdaten können die These kippen\n")


def session_eintrag(sid, kennung, zeit, entscheidungen: dict) -> str:
    zeilen = [f"\n### {sid} | Session | {kennung}", f"- Zeit: {zeit:%Y-%m-%d %H:%M}",
              "- Marktlage: Demo – simulierte Kurse; Indizes leicht fester, Volatilität moderat "
              f"(https://example.org/demo/markt, {zeit:%Y-%m-%d}). Einschätzung: freundliches Umfeld."]
    for profil in ("defensiv", "ausgewogen", "aggressiv"):
        zeilen.append(f"- {profil.capitalize()}: {entscheidungen.get(profil, 'keine Order; Positionierung passt zur Anlagerichtlinie')}")
    zeilen.append("- Offene Punkte und Termine für die nächste Session: Stops prüfen, Zahlenveröffentlichungen beobachten")
    return "\n".join(zeilen) + "\n"


def review_text(faellig: dict, zeit: datetime) -> str:
    import bewertung

    zeilen = [f"# {faellig['text']} (Demo)", "", f"Erstellt: {zeit:%Y-%m-%d %H:%M}", "",
              "| Profil | Wert | Rendite | gegen Benchmark | Drawdown-Stufe |", "| --- | ---: | ---: | ---: | ---: |"]
    benchmark = bewertung.benchmark_berechnen()
    for profil in ("defensiv", "ausgewogen", "aggressiv"):
        k = bewertung.kennzahlen(profil, benchmark)
        zeilen.append(f"| {profil} | {k['wert']:.2f} EUR | {bewertung._p(k['rendite'])} | {bewertung._p(k['gegen_bench'])} "
                      f"| {k['stufe']} |")
    zeilen += ["", "## Beobachtungen", "Demo: Kosten bleiben unter Kontrolle; Stops greifen wie geplant.",
               "", "## Schlussfolgerungen", "Keine Strategieänderung; Einzelbeobachtungen bleiben Hypothesen.", ""]
    return "\n".join(zeilen)


def erzeugen(ziel: Path, tage: int, seed: int, ende: date | None = None) -> Path:
    ziel = ziel.resolve()
    os.environ["STOCKMASTER_DATA_DIR"] = str(ziel)
    os.environ.pop("STOCKMASTER_FRAMEWORK_DIR", None)
    sys.path.insert(0, str(QUELLE_REPO / "tools"))
    vorbereiten(ziel)
    import bewertung
    import buchen
    import gemeinsam as g
    import init
    import kurse
    import session
    import termine

    random.seed(seed)
    uhr = Uhr()
    g.jetzt = uhr
    ende = ende or (date.today() - timedelta(days=1))
    start = ende - timedelta(days=tage)
    while not kurse.ist_handelstag("EUNL.DE", start):
        start += timedelta(days=1)
    kurse.QUELLE = SimulierteQuelle(uhr, start, ende, seed)

    uhr.stellen(start, "08:00")
    still(init.main, ["--startdatum", start.isoformat(), "--freigabe", KENNUNGEN[0]])
    for profil in g.PROFILE:
        (ziel / "strategie" / f"{profil}.md").write_text(strategie_text(profil), encoding="utf-8")
    git(ziel, "add", "-A")
    git(ziel, "commit", "-q", "-m", f"aufbau: Demo-Arbeitsbereich initialisiert (Start {start})")

    tag = start
    nummer_session = 0
    while tag <= ende:
        if tag.weekday() in (0, 2, 4) and kurse.ist_handelstag("EUNL.DE", tag):
            kennung = KENNUNGEN[(tag.isocalendar()[1]) % 2]
            nummer_session += 1
            uhr.stellen(tag, "10:05")
            still(session.main, ["start", "--person", kennung])
            still(bewertung.main, ["nachbuchen"])
            journal = ziel / "journal" / f"{tag.isoformat()}_{kennung}.md"
            if not journal.exists():
                journal.write_text(f"# Journal {tag.isoformat()} ({kennung})\n", encoding="utf-8")
            for faellig in termine.faellige_reviews(tag):
                if faellig["art"] == "stufe2":
                    continue
                (ziel / faellig["datei"]).write_text(review_text(faellig, uhr()), encoding="utf-8")
            entscheidungen = {}
            nummer = 0
            for profil in g.PROFILE:
                portfolio = g.portfolio_laden(profil)
                if portfolio["status"] != "aktiv":
                    continue
                # Gewinne mitnehmen: Positionen mit mehr als 8 % Plus teilweise verkaufen
                for position in list(portfolio["positionen"]):
                    if position["typ"] in g.AKTIEN and random.random() < 0.15:
                        nummer += 1
                        jid = f"J-{tag:%Y%m%d}-{nummer:02d}"
                        uhr.stellen(tag, f"10:{10 + nummer:02d}")
                        with journal.open("a", encoding="utf-8") as datei:
                            datei.write(
                                f"\n### {jid} | {profil} | {position['ticker']}\n- Zeit: {uhr():%Y-%m-%d %H:%M}\n"
                                "- Aktion: Verkauf, Gewinnmitnahme bzw. Risikoabbau\n- These: Chance-Risiko-Verhältnis "
                                "nach der Bewegung nicht mehr attraktiv.\n- Szenarien: Bull 20 % / Base 50 % / Bear 30 %\n"
                                "- Katalysator und Zeithorizont: sofort\n- Einstieg, Stop, Kursziel: Verkauf zum Marktkurs\n"
                                "- Positionsgröße und Risikorechnung: gesamte Position\n"
                                f"- Quellen: https://example.org/demo/verkauf, {uhr():%Y-%m-%d} (Demo)\n"
                                "- Unsicherheiten: Trend könnte weiterlaufen\n")
                        code, _ = still(buchen.main, ["verkaufen", "--profil", profil, "--position-id",
                                                      position["id"], "--journal-id", jid])
                        entscheidungen[profil] = (f"Verkauf {position['ticker']} ({jid}); Alternative Halten verworfen, "
                                                  "weil das Kursziel weitgehend erreicht ist")
                        break
                if len(portfolio["positionen"]) >= {"defensiv": 3, "ausgewogen": 4, "aggressiv": 4}[profil]:
                    entscheidungen.setdefault(profil, "keine Order; Portfolio voll investiert, Stops aktiv")
                    continue
                if random.random() < 0.45:
                    entscheidungen.setdefault(profil, "keine Order; Abwarten bis zur Bestätigung des Trends, "
                                                      "Nachkauf bestehender Werte verworfen")
                    continue
                typ, ticker, these = random.choice(IDEEN[profil])
                kurs = float(kurse.QUELLE.aktuell(ticker)[0])
                nummer += 1
                jid = f"J-{tag:%Y%m%d}-{nummer:02d}"
                uhr.stellen(tag, f"10:{10 + nummer:02d}")
                hebel = None
                if typ == "ko":
                    hebel = random.choice((3, 4, 5))
                    stop, ziel_kurs, einsatz = kurs * 0.985, kurs * 1.04, 200
                elif typ == "faktor":
                    hebel = 3
                    stop, ziel_kurs, einsatz = kurs * 0.97, kurs * 1.08, 150
                else:
                    abstand = {"defensiv": 0.05, "ausgewogen": 0.06, "aggressiv": 0.08}[profil]
                    stop, ziel_kurs = kurs * (1 - abstand), kurs * (1 + 2 * abstand)
                    einsatz = {"defensiv": 140, "ausgewogen": 220, "aggressiv": 280}[profil]
                with journal.open("a", encoding="utf-8") as datei:
                    datei.write(journal_eintrag(jid, profil, typ, ticker, uhr(), these, einsatz, stop, ziel_kurs,
                                                kurs, hebel))
                argv = ["kaufen", "--profil", profil, "--typ", typ, "--einsatz", str(einsatz),
                        "--stop", f"{stop:.2f}", "--kursziel", f"{ziel_kurs:.2f}", "--journal-id", jid]
                argv += ["--ticker", ticker] if typ in g.AKTIEN else ["--basiswert", ticker]
                if typ == "ko":
                    argv += ["--hebel", str(hebel)]
                if typ == "faktor":
                    argv += ["--faktor", str(hebel)]
                code, ausgabe = still(buchen.main, argv)
                if code == 0:
                    entscheidungen[profil] = (f"Order {jid} ({typ} {ticker}); Alternativen "
                                              f"{', '.join(t for _, t, _ in IDEEN[profil] if t != ticker)[:60]} verworfen")
                else:
                    grund = ausgabe.strip().splitlines()[-1][:160] if ausgabe.strip() else "abgelehnt"
                    entscheidungen[profil] = f"Order {jid} von tools/ abgelehnt ({grund}); nicht umgangen"
            uhr.stellen(tag, "10:40")
            nummer_s = 1
            with journal.open("a", encoding="utf-8") as datei:
                datei.write(session_eintrag(f"S-{tag:%Y%m%d}-{nummer_s:02d}", kennung, uhr(), entscheidungen))
            still(bewertung.main, ["bericht"])
            git(ziel, "add", "-A")
            git(ziel, "commit", "-q", "-m", f"session: {tag.isoformat()} {kennung}")
            uhr.stellen(tag, "10:45")
            still(session.main, ["ende"])
        tag += timedelta(days=1)
    # Abschluss: Stand bis zum Ende nachbuchen, damit die Ansicht aktuell ist
    uhr.stellen(ende + timedelta(days=1), "07:30")
    still(session.main, ["start", "--person", KENNUNGEN[0]])
    still(bewertung.main, ["nachbuchen"])
    still(bewertung.main, ["bericht"])
    git(ziel, "add", "-A")
    git(ziel, "commit", "-q", "-m", "session: Abschluss Demo (Nachbuchung)")
    still(session.main, ["ende"])
    # Marktübersicht und News wie vom Hintergrunddienst (Werte ohne simulierte Kurse erscheinen "veraltet").
    uhr.stellen(ende + timedelta(days=1), "10:00")
    still(kurse.markt)
    demo_news(g, uhr(), start)
    git(ziel, "add", "-A")
    git(ziel, "commit", "-q", "-m", "daten: Demo-Kurse und Demo-News")
    for name in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"):
        os.environ.pop(name, None)
    return ziel


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Demo-Datenverzeichnis mit simulierten Kursen erzeugen.")
    parser.add_argument("--ziel", required=True, help="Zielverzeichnis (wird überschrieben)")
    parser.add_argument("--tage", type=int, default=100, help="Länge der Simulation in Kalendertagen")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--ende", help="letzter simulierter Tag (Standard: gestern)")
    args = parser.parse_args(argv)
    ziel = erzeugen(Path(args.ziel), args.tage, args.seed,
                    date.fromisoformat(args.ende) if args.ende else None)
    print(f"Demo-Datenverzeichnis erzeugt: {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
