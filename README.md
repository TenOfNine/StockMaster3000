# Claude-Börsenexperiment

Spielgeld-Experiment: Claude handelt als institutioneller Portfoliomanager drei
Portfolios (defensiv, ausgewogen, aggressiv) mit je 1.000 EUR und entwickelt
die bestmögliche Strategie. Auftraggeber: Patrick und Philip.
Kein echtes Geld, keine Anlageberatung.

## Dateien

| Datei | Inhalt |
| --- | --- |
| KONZEPT.md | Zweck, Rollen, Architektur, Risiken (v1.1) |
| regeln.md | verbindliche Spielregeln |
| CLAUDE.md | Arbeitsanweisung für Claude Code (wird automatisch geladen) |
| AUFTRAG_PHASE1.md | Entwicklungsauftrag mit Arbeitspaketen und Abnahmekriterien |
| STATUS.md | aktueller Projektstatus und getroffene Entscheidungen |
| lessons.md | Erkenntnisregister, wächst mit dem Spiel |

## Werkzeuge (tools/)

| Befehl | Zweck |
| --- | --- |
| `python tools/session.py start --person <name>` / `ende` / `status` | Session-Sperre |
| `python tools/kurse.py aktuell <ticker...>` | aktuelle Kurse (protokolliert in data/kurse/) |
| `python tools/kurse.py historie <ticker> --von --bis` | Tagesdaten mit Dividenden und Splits |
| `python tools/limits.py pruefen --profil ... --typ ...` | Kauforder gegen Limits prüfen, ohne Buchung |
| `python tools/buchen.py kaufen/verkaufen/aendern/storno ...` | Orders (nur mit Journal-ID) |
| `python tools/bewertung.py nachbuchen` / `bericht` / `review` | Nachbuchung, ranking.md, Pflicht-Review |
| `python tools/pruefe.py [--historie]` | unabhängige Kontrolle |
| `python tools/init.py --startdatum JJJJ-MM-TT` | Spielstart (einmalig, nach Freigabe) |
| `python tools/produkte.py ko/faktor ...` | Zertifikatsrechner (nur Anzeige) |

Tests: `python -m pytest -q` (ohne Netzwerk). Die GitHub Action
(.github/workflows/pruefung.yml) führt bei jedem Push Tests und
`pruefe.py --historie` aus.

## Start

1. Privates GitHub-Repository anlegen, diese Dateien pushen, Philip als Collaborator einladen.
2. Repository klonen und im Ordner Claude Code starten (`claude`).
3. Erste Nachricht an Claude Code:
   > Lies CLAUDE.md und STATUS.md und beginne mit AUFTRAG_PHASE1.md.

## Später: Trading-Session

Nach Abschluss von Phase 1 reicht zum Start einer Session:
> Ich bin Patrick, starte eine Trading-Session.
