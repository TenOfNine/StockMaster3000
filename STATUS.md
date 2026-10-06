# Projektstatus

- Phase: 2 (Startbetrieb-Vorbereitung). Phase 1 (Aufbau, AP1 bis AP11) abgeschlossen am 2026-10-06; AP12 nach Phase 2 verschoben (Entscheidung 5)
- Startdatum des Spiels: noch nicht gesetzt (wird mit tools/init.py nach der Freigabe in AP12 festgelegt, nie rückwirkend)
- Letzte Session: keine

## Arbeitspakete Phase 1

- [x] AP1 Grundgerüst und Konfiguration
- [x] AP2 Kursdaten (tools/kurse.py)
- [x] AP3 Synthetische Zertifikate (tools/produkte.py)
- [x] AP4 Limitprüfung (tools/limits.py)
- [x] AP5 Orders und Buchung (tools/buchen.py)
- [x] AP6 Nachbuchung und Bewertung (tools/bewertung.py)
- [x] AP7 Prüfskript (tools/pruefe.py)
- [x] AP8 Session-Sperre (tools/session.py)
- [x] AP9 Szenario-Tests
- [x] AP10 GitHub Action (grüner Lauf: https://github.com/TenOfNine/StockMaster3000/actions/runs/37445431578)
- [x] AP11 Initialisierung (tools/init.py)
- AP12 nach Phase 2 verschoben (siehe unten)

## Arbeitspakete Phase 2

- [ ] AP12 Testsession ohne Trades, Anlagerichtlinien, Freigabe und Initialisierung (AUFTRAG_PHASE1.md)
- [ ] W0 bis W17 Web-UI (AUFTRAG_WEBUI.md; Fortschritt wird dort je Paket hier ergänzt)

## Entscheidungen

Hier werden Klärungen zu Unklarheiten in regeln.md festgehalten
(Datum, Frage, Entscheidung, wer hat entschieden).

Entscheidungen vom 2026-10-06, mitgeteilt von einem Auftraggeber im Chat
mit Claude Code (ohne Namen gemäß Entscheidung 4):

1. Web-UI, Benutzer und Arbeitsbereiche: Es gibt initial genau einen
   Administrator, der Benutzer anlegt. Jeder Benutzer legt eigene
   Arbeitsbereiche an und teilt sie bei Bedarf mit den Stufen Lesen und
   Vollzugriff. Jeder Arbeitsbereich ist nach Schwerpunkt und
   Anlagestrategie per Mehrfachauswahl konfigurierbar (z. B. Technologie,
   Gesundheit, nur USA, nur Deutschland).
2. Claude-Anbindung: ausschließlich private Claude-Pro-Abos, keine
   nutzungsabhängig abgerechneten API-Keys. Der Hinweis von Anthropic zu
   claude.ai-Logins in Drittanbieter-Produkten
   (https://code.claude.com/docs/en/agent-sdk/overview, abgerufen
   2026-10-06) wurde vorgelegt; entschieden wurde für eigene Pro-Abos in
   der privat betriebenen Installation.
3. Auftraggeber eines Arbeitsbereichs ist dessen Ersteller.
4. CLAUDE.md wird um den Session-Eintrag (S-JJJJMMTT-NN) für Abwägungen
   und Nichtstun ergänzt sowie um den Grundsatz, dass keine Namen oder
   personenbezogenen Daten im Repository auftauchen dürfen.
5. AP12 wird in Phase 2 übernommen; Phase 1 gilt als abgeschlossen.
6. Die Web-UI ist standardmäßig nur aus dem Heimnetz erreichbar. Zugriff
   aus dem Internet ist optional und nie Standard.
7. Technische Festlegung Web-UI: eigene Abhängigkeiten nur unter webui/
   mit Lockfiles (Begründung: Weboberfläche, Datenbank und
   Sicherheitsfunktionen sind mit pandas, yfinance und pytest nicht
   umsetzbar). Für tools/ gilt weiterhin "nur pandas, yfinance, pytest".

## Offene Auslegungsfragen (Phase 1, konservativ umgesetzt, Freigabe erbeten)

Wo regeln.md nicht eindeutig ist, wurde nach CLAUDE.md die konservativere
Auslegung gewählt und im Code kommentiert. Bitte bestätigen oder ändern:

1. Faktor-Kosten (0,02/365) je Kalendertag, nicht je Handelstag
   (Wochenende: dreifach). Knock-out-Aufzinsung ebenfalls an jedem
   Kalendertagsende, auch am Kauftag.
2. Kursziel am Kauftag wird nicht ausgelöst (das Tageshoch kann vor dem
   Kauf gelegen haben); der Stop zählt am Kauftag gegen die ganze
   Tagesspanne (regeln.md 4).
3. Änderungen von Stop/Kursziel wirken ab der nächsten Tageskerze.
4. Vorgemerkte Orders (Market und Limit) nutzen nur Tageskerzen, die nach
   ihrer Erfassung beginnen. Eine während der Handelszeit erfasste, nicht
   sofort ausführbare Limit-Order gilt also erst ab dem nächsten
   Handelstag. Limit-Orders gelten bis zum Storno.
5. Gold/Brent: Die Tageskerze der Futures beginnt am Vorabend; als Beginn
   gilt konservativ 23:00 des Vortags.
6. Devisenkurs: Ausführung zur Eröffnung mit EURUSD-Eröffnung, Ereignisse
   im Tagesverlauf und Bewertung mit EURUSD-Schluss desselben Tages.
7. Nachgebucht werden nur abgeschlossene Tage (bis gestern). Ereignisse von
   heute (z. B. Ausführung einer Abendorder zur heutigen Eröffnung) bucht
   die nächste Session.
8. Ein aktueller Kurs gilt bei offenem Markt höchstens 30 Minuten
   (config/projekt.json); älter: kein Handel.
9. Mindestorder (100 EUR) gilt auch für Teilverkäufe; Komplettverkauf
   immer erlaubt.
10. Einzelposition: gleiche Instrumente werden zusammengezählt (Aktie je
    Ticker, Zertifikate je Typ, Richtung und Basiswert). Alle Limits werden
    bei jedem Kauf nach der Order geprüft; ein bereits überschrittenes
    Limit blockiert damit jeden Kauf, der es nicht verbessert.
11. Unbekannte Marktkapitalisierung eines Aktien-Basiswerts gilt als zu
    klein.
12. Dividende nur für Positionen, die vor Beginn des Ex-Tags eröffnet
    wurden und am Ex-Tag zum Schluss noch bestehen (Verkauf am Ex-Tag
    verliert die Dividende).
13. Splits werden vor allen Ereignissen des Split-Tags angewendet (die
    Tageskerze ist bereits angepasst), nicht erst zum Tagesschluss.
14. Portfolio-Stopp: Prüfung zum Tagesschluss; Glattstellung aller
    Positionen zum Schlusskurs inklusive Spread und Gebühr.
15. Drawdown: Endet Stufe 2 (nach Review, Drawdown unter der Hälfte der
    Stufe-2-Schwelle), gilt Stufe 1 weiter, solange der Drawdown nicht
    unter der Hälfte der Stufe-1-Schwelle liegt.
16. Je Kauf und Verkauf ein eigener Journal-Eintrag; der Eintrag muss das
    Portfolio nennen und in der Journal-Datei der Person stehen, die die
    Session-Sperre hält. Stop und Kursziel sind beim Kauf Pflichtangaben
    (`keiner` ausdrücklich möglich).
17. Kauf-Limit auf den Basiswert: Long bei Kurs <= Limit, Short bei
    Kurs >= Limit.

## Offene Auslegungsfragen (Phase 2, Freigabe erbeten)

18. regeln.md Abschnitt 2 nennt als Startdatum den "ersten Handelstag
    nach Abschluss von Phase 1". Phase 1 ist seit 2026-10-06
    abgeschlossen, AP12 (Freigabe) aber noch offen. Konservative
    Auslegung: Das Startdatum wird erst nach der Freigabe in AP12
    festgelegt; "nach Abschluss von Phase 1" gilt als frühester Zeitpunkt.
19. Grundsatz "keine Namen im Repository" (Entscheidung 4): Die
    Dokumente CLAUDE.md, README.md, KONZEPT.md, AUFTRAG_PHASE1.md und
    AUFTRAG_WEBUI.md sind bereinigt. Namen stehen noch in regeln.md
    (darf nur von den Auftraggebern geändert werden), in
    config/projekt.json (Auftraggeber-Liste, steuert die Session-Sperre),
    in der Hilfe von tools/session.py, in Tests und in früheren Commits
    der Git-Historie. Vorschlag: Auftraggeber in config/projekt.json und
    regeln.md auf neutrale Kennungen umstellen (die Auftraggeber legen
    die Kennungen fest und ändern regeln.md selbst), danach Code und
    Tests anpassen. Die Git-Historie bleibt unverändert, weil ein
    Umschreiben die Nur-Anhängen-Prüfung und die Prüfspur bricht.

## Technische Festlegungen Phase 1

- Keine weiteren Abhängigkeiten außer pandas, yfinance, pytest.
- Zusätzliche Datei config/projekt.json (Startkapital, Portfolio-Stopp,
  Auftraggeber, Sperrdauer, Benchmark, maximales Kursalter).
- trades/<profil>.csv um die Spalten devisenkurs, stop, kursziel, bemerkung
  ergänzt. Zusätzliche Aktionen: vormerkung, aenderung, storno, verfall,
  knockout, split, dividende, zins; zusätzlicher Grund: portfoliostopp.
  Cash-Zinsen stehen als Zeilen in trades/, damit Cash vollständig
  nachrechenbar ist.
- data/limits/<profil>.jsonl protokolliert die bei jeder Ausführung
  geprüften Kennzahlen (Grundlage für pruefe.py).
- Pflicht-Review bei Drawdown-Stufe 2 wird mit
  `python tools/bewertung.py review --profil <p> --datei reviews/<datei>.md`
  vermerkt.
- data/nav/ wird beim Nachbuchen an jedem Xetra-Handelstag geschrieben
  (Tage mit EUNL.DE-Kurs); Sharpe mit 2 % p. a. / 252 als risikofreiem
  Zins. Kostenquote = Gebühren und Spreads in % des Startkapitals.
  Bewertung zu Mittelkursen ohne Spread.
- Yahoo-Tagesdaten sind rückwirkend split-bereinigt; kurse.py rechnet sie
  auf gehandelte Kurse zurück und überschreibt gespeicherte Tage nie. Gegen
  Live-Daten noch ungeprüft, weil Yahoo aus der Cloud-Umgebung von
  Claude Code (Netzwerkrichtlinie) nicht erreichbar war; Prüfung in der
  Testsession (AP12) auf einem Rechner mit Internetzugang.
