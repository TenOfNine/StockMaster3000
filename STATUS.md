# Projektstatus

- Phase: 2 (Startbetrieb-Vorbereitung). Phase 1 (Aufbau, AP1 bis AP11) abgeschlossen am 2026-10-06; AP12 nach Phase 2 verschoben (Entscheidung 5)
- Startdatum des Spiels: erst nach Freigabe von AP12 (wird dann mit tools/init.py gesetzt, nie rückwirkend; Entscheidung 11)
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
- [x] W0 Klärung der offenen Punkte zur Web-UI (Entscheidungen 1 bis 12)
- [ ] W1 bis W17 Web-UI (AUFTRAG_WEBUI.md); Stufe 1 (lesend) umgesetzt, Stand je Paket unten
- [x] Werkzeug-Ergänzungen vor dem Spielstart: Fälligkeiten (tools/termine.py),
  Session-Einträge und Journal-Vorlage in pruefe.py, Kalender bis 2028 mit
  NYSE-Frühschlüssen, Dateirechte atomar geschriebener Dateien (2026-10-06)

## Web-UI Stufe 1 (lesend), Stand 2026-10-06

Vorschlag aus der Planung: Die Web-UI in zwei Stufen bauen; Stufe 1 zeigt
das laufende Spiel, Stufe 2 bringt Arbeitsbereiche und Claude-Läufe.
Betrieb und Tests: webui/BETRIEB.md.

| Paket | Stand | Offen für Stufe 2 bzw. Abnahme |
| --- | --- | --- |
| W1 Grundgerüst und Docker | Compose mit proxy, api, db; interne Netze, Secrets, Healthchecks, Härtung; Caddy mit lokaler CA und Heimnetz-Schranke; Rauchtest (webui/deploy/rauchtest.sh) | Dienste worker und redis kommen mit W8/W9 |
| W2 Datenbank und RLS | Schema und Alembic-Migration (Benutzer, Sitzungen, Audit-Log), PostgreSQL mit Anwendungsrolle ohne Superuser- und BYPASSRLS-Recht | RLS-Policies folgen mit den mandantenbezogenen Tabellen (Arbeitsbereiche, W5); in Stufe 1 gibt es nur eigene Sitzungen |
| W3 Authentifizierung | erfüllt: Admin-Erstanlage per CLI (nur einmal), Login, serverseitige Sitzungen, CSRF und Origin-Prüfung, TOTP, Sperre bei Fehlversuchen, Passwortwechsel | Rate-Limits im Prozess statt Redis (ein API-Prozess) |
| W4 Benutzerverwaltung | erfüllt: Admin-Router (anlegen, sperren, Passwort und Zwei-Faktor zurücksetzen, Admin-Rolle), Kennung je Benutzer, Matrixtest | – |
| W7 Lesedienst | erfüllt für ein Spiel-Repository: Portfolios, Trades, NAV, Limits, Journal (J und S), Reviews, Strategie, Lessons, Ranking, STATUS.md, config, Git-Log | je Arbeitsbereich mit W5 |
| W8 Werkzeug-Ausführung | nur lesend: tools/pruefe.py in eigenem Prozess mit Zeitlimit, Zertifikatsrechner über tools/produkte.py | Positivliste im Worker mit W8 |
| W10 Frontend-Grundgerüst | Layout, Navigation, Befehlspalette, dunkles und helles Theme, deutsche Formate, mobile Navigation, App-Icon | Lighthouse-Messung steht aus |
| W11 Cockpit und Portfolios | erfüllt; Test: Werte stimmen mit ranking.md und data/nav überein | – |
| W12 Entscheidungen | Zeitachse, Trade-Akten, Session-Einträge (Abwägungen, Nichtstun) | Ideen und Verknüpfung zu Läufen mit W9 |
| W13 Regelwerk, Einrichtung | Anzeige von Regeln, Limits, Kosten, Universum, Arbeitspaketen, Entscheidungen, Auslegungsfragen | Formulare und Änderungsanträge |
| W15 CI | GitHub Action um Backend-, Frontend-, E2E- und Docker-Jobs erweitert; bestehender Job unverändert | Audits, Image-Scan, SBOM |
| W16 Dokumentation | webui/BETRIEB.md, README | Neuinstallation auf frischem Rechner |

Technische Festlegungen Stufe 1:
- Profilfarben: Die geplanten Töne (#38BDF8, #22C55E, #F59E0B) fielen im
  Palette-Validator bei Farbsehschwäche durch (Grün und Orange für
  Protanopie kaum unterscheidbar, ΔE 5,7). Verwendet werden geprüfte
  Stufen derselben Farbfamilien: dunkel #3987E5 / #199E70 / #D95926,
  hell #2A78D6 / #1BAF7A / #EB6834. App-Icon entsprechend angepasst.
- Gewinne und Verluste immer mit Vorzeichen und Pfeil, nie nur über Farbe;
  jedes Diagramm hat eine Tabellenansicht bzw. Beschriftung.
- Portainer (2026-10-06): Stack `webui/deploy/portainer/stack.yml` ohne lokale Dateien; Images
  (api, proxy, db) baut `.github/workflows/images.yml` nach ghcr.io; Geheimnisse als
  Stack-Umgebungsvariablen statt Docker Secrets (Portainer Standalone kennt keine Secrets-Dateien);
  Anwendungspasswort nur Buchstaben und Ziffern (steht in der Datenbank-URL). Anleitung:
  webui/PORTAINER.md. Das Root-Zertifikat ist unter /stockmaster-root.crt abrufbar (nur Heimnetz).
- Startreihenfolge (2026-10-06, Fund bei der Einrichtung in Portainer): Der PostgreSQL-Healthcheck über
  den Unix-Socket meldete „bereit“, solange noch der temporäre Init-Server lief; die API startete zu früh
  und stürzte ab. Behoben durch Healthcheck über TCP, Wartelogik der API (bis zu 2 Minuten, mit klarer
  Meldung) und einen Passwortabgleich des DB-Images bei jedem Start (geänderte Passwörter bei vorhandenem
  Volume). Der Proxy hängt nicht mehr am API-Healthcheck.
- Die Web-UI importiert die Werkzeuge des eingebundenen Spiel-Repositorys
  und ruft keine Kurse ab (Kursquelle im Prozess durch eine Attrappe ohne
  Netzwerk ersetzt); das Repository ist nur lesend eingebunden.
- E-Mail-Adressen werden bewusst einfach geprüft, damit Heimnetz-Adressen
  wie name@heimnetz.local möglich sind.
- In der Cloud-Umgebung von Claude Code sind Yahoo Finance und die
  Debian-Paketquellen gesperrt. Der Docker-Rauchtest lief dort mit einem
  Test-Image ohne git; der vollständige Build läuft in der GitHub Action.

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
8. Je Arbeitsbereich gibt es immer die drei Profile defensiv, ausgewogen
   und aggressiv (AUFTRAG_WEBUI.md, Frage 14.1). Ersetzt durch
   Entscheidung 13.
9. Mitglieder mit Vollzugriff dürfen Sessions mit ihrem eigenen Pro-Abo
   starten; Sperre und Journal tragen die Kennung des Auftraggebers
   (AUFTRAG_WEBUI.md, Frage 14.2).
10. Claude darf regeln.md einmalig anpassen. Umgesetzt am 2026-10-06 als
    v1.2: Auftraggeber als neutrale Kennungen, Startdatum nach Freigabe
    von AP12, Arbeitsbereiche und Schwerpunkt je Arbeitsbereich,
    Session-Start durch Mitglieder mit Vollzugriff, Session-Eintrag und
    Datenschutz in Abschnitt 10, Änderungshistorie in Abschnitt 14. Die
    Limit-Tabelle in Abschnitt 7 blieb unverändert. Danach ändert Claude
    regeln.md nie wieder unaufgefordert (CLAUDE.md, Grundsatz 1).
11. Startdatum: erst nach Freigabe von AP12 (beantwortet Frage 18).
12. Namen werden überall außer in der Git-Historie entfernt (beantwortet
    Frage 19). Neutrale Kennungen in config/projekt.json:
    `auftraggeber-a`, `auftraggeber-b`. Die Zuordnung zu Personen liegt
    außerhalb des Repositorys. Die Git-Historie bleibt unverändert,
    damit Prüfspur und Nur-Anhängen-Prüfung intakt bleiben.
13. Die Profile defensiv, ausgewogen und aggressiv sind je Arbeitsbereich
    per Mehrfachauswahl an- und abschaltbar (ersetzt Entscheidung 8;
    Umsetzung AUFTRAG_WEBUI.md 4.4 und W6). Voraussetzung ist eine
    Regelgrundlage in regeln.md (offene Auslegungsfrage 20).
14. App-Icon und Favicon: Vorschlag "Drei Profile",
    abgelegt als assets/icons/drei-profile.svg.

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

## Auslegungsfragen Phase 2 (beide entschieden, siehe Entscheidungen 11 und 12)

18. regeln.md Abschnitt 2 nennt als Startdatum den "ersten Handelstag
    nach Abschluss von Phase 1". Phase 1 ist seit 2026-10-06
    abgeschlossen, AP12 (Freigabe) aber noch offen. Konservative
    Auslegung: Das Startdatum wird erst nach der Freigabe in AP12
    festgelegt; "nach Abschluss von Phase 1" gilt als frühester Zeitpunkt.
    Entschieden: siehe Entscheidung 11; regeln.md Abschnitt 2 angepasst.
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
    Entschieden: siehe Entscheidung 12; umgesetzt bis auf die Historie.

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

## Offene Auslegungsfragen (Phase 2, Freigabe erbeten)

20. Profilauswahl (Entscheidung 13) und regeln.md v1.2 widersprechen
    sich: Abschnitt 2 nennt "1.000 EUR je Portfolio (defensiv,
    ausgewogen, aggressiv)" und "eigenen drei Portfolios", Abschnitt 11
    den "Monatsvergleich der drei Profile". Die einmalige Freigabe zur
    Änderung von regeln.md ist verbraucht (Entscheidung 10); Claude
    ändert die Datei nicht erneut. Bis zur Klärung bleiben in diesem
    Repository und in den Werkzeugen alle drei Profile aktiv.
    Formulierungsvorschlag für die Auftraggeber:
    - Abschnitt 2: "Startkapital: 1.000 EUR je aktivem Portfolio. Je
      Arbeitsbereich sind die Profile defensiv, ausgewogen und aggressiv
      einzeln aktivierbar (mindestens eines; config/projekt.json,
      `profile_aktiv`; ohne Angabe alle drei)."
    - Abschnitt 2: "eigenen drei Portfolios" ersetzen durch "eigenen
      Portfolios".
    - Abschnitt 2, neu: "Nach dem Startdatum ändern nur die
      Auftraggeber die Auswahl, mit Datum und ohne Rückwirkung.
      Aktivieren: neues Portfolio mit 1.000 EUR ab dem nächsten
      Handelstag nach der Freigabe, Benchmark ab demselben Tag.
      Deaktivieren: nur ohne offene Positionen und Orders; Bewertung und
      Verzinsung enden, die Historie bleibt."
    - Abschnitt 11: "Monatsvergleich der drei Profile" ersetzen durch
      "Monatsvergleich der aktiven Profile".
