<img src="assets/icons/drei-profile.svg" alt="StockMaster 3000 Icon" width="96" height="96">

# StockMaster 3000 – Claude-Börsenexperiment

[![Prüfung](https://github.com/TenOfNine/StockMaster3000/actions/workflows/pruefung.yml/badge.svg)](https://github.com/TenOfNine/StockMaster3000/actions/workflows/pruefung.yml)

Claude handelt als institutioneller Portfoliomanager drei
Spielgeld-Portfolios mit je 1.000 EUR und entwickelt daraus die
bestmögliche Strategie. Jede Entscheidung ist begründet, jede Buchung
nachrechenbar, jede Änderung in Git nachvollziehbar.

> **Simulation.** Kein echtes Geld, kein echter Handel, keine
> Anlageberatung.

## Projektstand

| Phase | Inhalt | Stand |
| --- | --- | --- |
| 1 Aufbau | Werkzeuge, Tests, GitHub Action, Initialisierung (AP1–AP11) | abgeschlossen (2026-10-06) |
| 2 Startbetrieb | Testsession, Anlagerichtlinien, Freigabe, Spielstart (AP12); Web-UI (W0–W17) | in Vorbereitung |
| 3 Bewertung | Profile gegen Benchmarks nach etwa drei Monaten | offen |
| 4 Langzeitbetrieb | Quartals-Meta-Reviews | offen |

Aktueller Stand, Entscheidungen und offene Fragen: [STATUS.md](STATUS.md).

## Grundidee

**Rechnen macht Code, Entscheiden macht Claude.** Kurse, Ausführung,
Zertifikatswerte, Zinsen, Limits und Kennzahlen kommen ausschließlich aus
getesteten Python-Werkzeugen. Claude recherchiert, entscheidet, begründet
und lernt. So bleiben die Ergebnisse reproduzierbar und unabhängig
prüfbar, obwohl Claude seine eigenen Trades verwaltet.

| | Defensiv | Ausgewogen | Aggressiv |
| --- | --- | --- | --- |
| Max. Anteil Zertifikate | 10 % | 30 % | 70 % |
| Max. Hebel je Zertifikat | 3x | 5x | 10x |
| Max. Risiko je Trade | 1 % | 2 % | 5 % |
| Benchmark (MSCI World / Cash) | 30 / 70 | 60 / 40 | 100 / 0 |

Verbindlich sind allein [regeln.md](regeln.md) und
`config/profile.json`.

Weitere Eckpunkte:

- Aktien und ETFs (Xetra, NYSE, NASDAQ) sowie synthetische Knock-out- und
  Faktor-Zertifikate, long und short, nach festen Formeln.
- Cash-Zins 2 % p. a., Gebühr 1 EUR je Order, feste Spreads,
  Mindestorder 100 EUR.
- Kein Backdating: Orders außerhalb der Handelszeit werden zum nächsten
  Eröffnungskurs ausgeführt; im Zweifel gilt die ungünstigere Annahme.
- Zweistufige Drawdown-Bremse je Profil; Portfolio-Stopp unter 200 EUR.
- Vor jeder Order steht ein Journal-Eintrag mit These, Szenarien, Stop,
  Kursziel, Risikorechnung und Quellen. Jede Session endet mit einem
  Session-Eintrag, der auch begründetes Nichtstun festhält.

## Ablauf einer Trading-Session

1. Session-Sperre setzen, damit nie zwei Sessions gleichzeitig laufen.
2. Versäumte Handelstage nachbuchen und alles mit dem Prüfskript
   kontrollieren.
3. Regeln, Strategien, Lessons, Ranking und letzte Einträge lesen;
   fällige Reviews zuerst erstellen.
4. Marktüberblick: Kurse über das Kurswerkzeug, News und Termine über die
   Web-Suche mit Quelle und Datum.
5. Je Portfolio entscheiden; für jede Order erst Journal, dann Buchung.
6. Session-Eintrag, Bericht, Prüfung, Commit, Sperre lösen, Push.

Die vollständige Arbeitsanweisung steht in [CLAUDE.md](CLAUDE.md).

## Schnellstart

Voraussetzungen: Python 3.11 oder neuer, Git, Claude Code.

```bash
pip install -r requirements.txt
python -m pytest -q            # Tests ohne Netzwerk
python tools/pruefe.py         # unabhängige Kontrolle
```

Eine Session startet ein Auftraggeber in Claude Code mit einer Nachricht
wie:

> Ich bin Auftraggeber `<kennung>`, starte eine Trading-Session.

Die Kennungen der Auftraggeber stehen in `config/projekt.json`.

## Werkzeuge (`tools/`)

| Befehl | Zweck |
| --- | --- |
| `python tools/session.py start --person <kennung>` / `ende` / `status` | Session-Sperre |
| `python tools/kurse.py aktuell <ticker...>` | aktuelle Kurse, protokolliert in `data/kurse/` |
| `python tools/kurse.py historie <ticker> --von --bis` | Tagesdaten mit Dividenden und Splits |
| `python tools/limits.py pruefen --profil ... --typ ...` | Kauforder gegen die Limits prüfen, ohne Buchung |
| `python tools/buchen.py kaufen/verkaufen/aendern/storno ...` | Orders, nur mit Journal-ID |
| `python tools/bewertung.py nachbuchen` / `bericht` / `review` | Nachbuchung, `ranking.md`, Pflicht-Review |
| `python tools/pruefe.py [--historie]` | unabhängige Kontrolle |
| `python tools/init.py --startdatum JJJJ-MM-TT` | Spielstart, einmalig nach Freigabe |
| `python tools/produkte.py ko/faktor ...` | Zertifikatsrechner, nur Anzeige |

Die GitHub Action ([.github/workflows/pruefung.yml](.github/workflows/pruefung.yml))
führt bei jedem Push die Tests und `pruefe.py --historie` aus.

## Repository-Struktur

    CLAUDE.md, regeln.md        Arbeitsanweisung und verbindliche Spielregeln
    STATUS.md, lessons.md       Projektstand, Entscheidungen, Erkenntnisse
    KONZEPT.md                  Zweck, Rollen, Architektur, Risiken
    AUFTRAG_PHASE1.md           Aufbau der Werkzeuge (AP1–AP12)
    AUFTRAG_WEBUI.md            Plan der Web-UI (W0–W17)
    config/                     Limits, Kosten, Universum, Projektwerte
    tools/                      Python-Werkzeuge (rechnen, buchen, prüfen)
    tests/                      Tests ohne Netzwerk, inkl. Szenario-Tests
    portfolios/ trades/ data/   Spielstand, nur über tools/ geschrieben
    journal/ reviews/ strategie/  Begründungen, Reviews, Anlagerichtlinien
    assets/icons/               App-Icon (drei Profile)

## Web-UI (geplant)

Eine Docker-basierte Weboberfläche ist geplant, standardmäßig nur im
Heimnetz erreichbar:

- Ein Administrator legt Benutzer an; jeder Benutzer verbindet sein
  eigenes Claude-Pro-Abo.
- Eigene Arbeitsbereiche mit Schwerpunkt-Mehrfachauswahl (z. B.
  Technologie, Gesundheit, nur USA, nur Deutschland) und an- und
  abschaltbaren Risikoprofilen, teilbar mit den Stufen Lesen und
  Vollzugriff.
- Trade-Akten mit These, Szenarien, Risikorechnung und Quellen;
  Zeitachse der Abwägungen; Live-Ansicht der Claude-Sessions.

Die Web-UI rechnet und bucht nicht selbst, sie nutzt dieselben
Werkzeuge. Details, Sicherheitskonzept und Arbeitspakete:
[AUFTRAG_WEBUI.md](AUFTRAG_WEBUI.md).

## Datenschutz

Im Repository stehen keine Namen oder personenbezogenen Daten. Personen
erscheinen nur als neutrale Kennung (`config/projekt.json`). Ältere
Commits der Git-Historie bleiben bewusst unverändert, damit die Prüfspur
intakt bleibt ([STATUS.md](STATUS.md), Entscheidung 12).

## Haftungsausschluss

Dieses Projekt ist ein Experiment mit Spielgeld. Nichts in diesem
Repository ist eine Anlageberatung oder eine Empfehlung zum Kauf oder
Verkauf von Wertpapieren.
