# Datenverzeichnis (Spielstand)

Dieses Verzeichnis enthält den gesamten Spielstand einer StockMaster-Instanz.
Es ist ein eigenes, lokales Git-Repository **ohne Remote**: Die Historie ist die
Prüfspur (`python tools/pruefe.py --historie`), es wird nie nach GitHub gepusht.

| Pfad | Inhalt | Schreibt |
| --- | --- | --- |
| `portfolios/`, `trades/`, `data/` | Portfolios, Buchungen, Kurse, NAV, Limitprotokoll | nur die Werkzeuge in `tools/` |
| `news/` | News-Speicher (RSS, nur anhängen) | `tools/news.py` |
| `journal/`, `reviews/`, `strategie/`, `lessons.md` | Dokumentation der Sessions | Claude (Journal nur anhängen) |
| `ranking.md` | Bericht | `tools/bewertung.py bericht` |
| `spiel.json` | Startdatum und Freigabe | `tools/init.py` |
| `session.lock` | Session-Sperre | `tools/session.py` |

Angelegt aus `vorlagen/datenverzeichnis/` des Frameworks
(`python tools/datenverzeichnis.py einrichten`). Hand-Änderungen an
`portfolios/`, `trades/` und `data/` sind verboten (regeln.md Abschnitt 1).
