# Konzept: Claude-Trader-Experiment v1.1

Stand nach Review. Verbindliche Details stehen in regeln.md (Spielregeln),
CLAUDE.md (Arbeitsweise) und AUFTRAG_PHASE1.md (Umsetzung).

## 1. Zweck
Claude führt drei Spielgeld-Portfolios (defensiv, ausgewogen, aggressiv)
mit je 1.000 EUR und entwickelt daraus die bestmögliche Handelsstrategie.
Claude agiert als professioneller institutioneller Portfoliomanager:
Prozess, Risikokontrolle und Dokumentation statt Bauchgefühl.

Ziele:
- Rendite je Risiko besser als profilgerechte Benchmarks
- nachvollziehbare Strategieentwicklung (Journal, Reviews, Erkenntnisse)
- Vergleich dreier Risikoprofile über verschiedene Marktphasen
- prüfen, wie diszipliniert ein KI-Agent mit Live-Recherche handelt

Nicht-Ziele: echte Geldanlage, Anlageberatung, Hochfrequenzhandel.

## 2. Rollen
| Rolle | Aufgabe | Grenzen |
| --- | --- | --- |
| Claude (über Claude Code) | Recherche, Entscheidung, Journal, Reviews, Weiterentwicklung der Werkzeuge in Phase 1 | handelt autonom innerhalb regeln.md; ändert Regeln nie; umgeht keine Prüfung |
| Auftraggeber | Regeln, Ideen, Session-Start, Aufsicht, Freigaben | Regeländerungen nur gemeinsam per Commit |
| Opus | unabhängige Reviews von Konzept und Verlauf | beratend |

## 3. Leitprinzip
**Rechnen macht Code, Entscheiden macht Claude.** Kurse, Ausführung,
Zertifikatswerte, Zinsen, Limits und Kennzahlen kommen aus getesteten
Skripten. Claude recherchiert, entscheidet, begründet und lernt. So sind
Ergebnisse reproduzierbar und unabhängig prüfbar, obwohl Claude die
eigenen Trades verwaltet.

## 4. Architektur
- Privates GitHub-Repository, reine Text- und Datendateien, Git-Historie
  als Prüfspur.
- Python-Werkzeuge in tools/: Kurse (yfinance mit Protokoll),
  synthetische Zertifikate, Limitprüfung, Buchung, Nachbuchung und
  Bewertung, Prüfskript, Session-Sperre, Initialisierung.
- GitHub Action führt bei jedem Push Tests und Prüfskript aus.
- Sessions werden von einem Auftraggeber in Claude Code gestartet;
  Versäumtes seit der letzten Session wird nach festen Regeln
  nachgebucht.

## 5. Spielmechanik (Kurzfassung)
- Aktien und ETFs (Xetra, NYSE, NASDAQ), synthetische Knock-out- und
  Faktor-Zertifikate long und short auf eine feste Basiswertliste.
- Cash-Zins 2 % p. a.; 1 EUR Gebühr je Order; feste Spreads;
  Mindestorder 100 EUR.
- Orders außerhalb der Handelszeit zum nächsten Eröffnungskurs; kein
  Backdating; im Zweifel die ungünstigere Annahme.
- Profile mit harten Limits für Zertifikate-Anteil, Hebel,
  Gesamt-Exposure, Einzelposition, Cashquote, Risiko je Trade und einer
  zweistufigen Drawdown-Bremse.
- Benchmarks aus MSCI-World-ETF und Cash: 30/70, 60/40, 100/0.

## 6. Lernsystem
- Journal vor jeder Order (These, Szenarien, Stop, Ziel, Quellen),
  unveränderlich und per ID mit der Order verknüpft.
- Anlagerichtlinie und versionierte Strategie je Portfolio.
- Wochenreview, Monatsvergleich der Profile, Quartals-Meta-Review.
- Erkenntnisregister lessons.md als Gedächtnis zwischen Sessions;
  Einzelbeobachtungen bleiben Hypothesen.

## 7. Erfolgsmessung
Rendite gegen Benchmark, maximaler Drawdown, Sharpe Ratio (ab 60
Handelstagen), Trefferquote und Payoff-Ratio, Kostenquote,
Regelverstöße. Belastbare Aussagen frühestens nach etwa drei Monaten und
einer zweistelligen Zahl abgeschlossener Trades je Portfolio.

## 8. Phasen
1. **Phase 1, Aufbau:** Werkzeuge, Tests, Testsession, Freigabe
   (AUFTRAG_PHASE1.md).
2. **Phase 2, Startbetrieb (ca. 4 Wochen):** manuelle Sessions; danach
   Session-Rhythmus festlegen.
3. **Phase 3, Bewertung (nach ca. 3 Monaten):** Profile gegen
   Benchmarks; Entscheidung über Automatisierung und Regelanpassungen.
4. **Phase 4, Langzeitbetrieb:** quartalsweises Meta-Review, optional
   Opus-Review.

## 9. Risiken und Annahmen
| Nr. | Risiko | Umgang |
| --- | --- | --- |
| R1 | Freie Kursdaten verzögert oder lückenhaft | Protokoll, ungünstigere Annahme, kein Handel ohne Kurs |
| R2 | Tagesdaten statt Intraday für Stops und Barrieren | feste konservative Reihenfolge |
| R3 | Selbstkontrolle des Traders | Skripte rechnen, Prüfskript, Append-only, GitHub Action |
| R4 | Sprachmodell gibt News falsch wieder | Quellenpflicht mit URL und Datum |
| R5 | Kleine Stichprobe, Zufall und Hebel | Kennzahlen je Risiko, Mindestdauer für Schlüsse |
| R6 | Hohe Kosten bei 1.000 EUR | Kosten im Risiko, Mindestorder, Kostenquote |
| R7 | Profile nicht unabhängig (gleicher Trader) | im Vergleich offen ausweisen |
| R8 | Synthetische Zertifikate idealisiert | Vereinfachungen in regeln.md Abschnitt 13 |
| R9 | Profi-Persona fördert Überselbstvertrauen | Szenarien und Unsicherheit verpflichtend |

## 10. Review-Historie
- v1.0 (06.10.2026): Erstkonzept.
- v1.1 (06.10.2026): Review mit 18 Befunden. Wichtigste Änderungen:
  Skripte statt Web-Suche für Kurse und Rechnungen; synthetische
  Zertifikate; Orders außerhalb der Handelszeit zum nächsten
  Eröffnungskurs; Journal-ID-Pflicht und Append-only-Prüfung;
  Exposure-Limit und Drawdown-Bremse; Profil-Benchmarks; Gebühren im
  Risiko; Erkenntnisregister; Session-Sperre; Startdatum erst nach
  Aufbau; Entwicklungsauftrag mit Abnahmekriterien.

## 11. Offene Punkte
- Session-Rhythmus nach Phase 2 festlegen.
- Automatischer Session-Start (Kosten, Zugangsdaten, Sicherheit).
- Ob reale Zertifikatskurse später ergänzend genutzt werden.
- Überlegung (2026-10-07, nicht entschieden): Eine eigene Persona-Datei für die
  Claude-Instanz ("soul.md"). Sie würde nicht automatisch geladen, sondern nur
  über CLAUDE.md oder den Lauf-Prompt, und Analyse, Ton und Begründungen prägen,
  nicht Limits und Buchungen (die setzt der Code durch). Gegen weiche Regeln
  (Kapitalerhalt, Nichtstun, Quellenpflicht) könnte sie arbeiten; das berührt R7
  und R9. Käme sie, dann mit ausdrücklicher Rangfolge (regeln.md vor CLAUDE.md vor
  Persona), nur für Stil und Haltung, Profil-Ausrichtung weiter in
  strategie/<profil>.md, im Framework statt im Datenverzeichnis (im Lauf
  schreibgeschützt), mit Vermerk in STATUS.md und vorheriger Testsession.
