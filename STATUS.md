# Projektstatus

- Phase: 2 (Startbetrieb-Vorbereitung). Phase 1 (Aufbau, AP1 bis AP11) abgeschlossen am 2026-10-06; AP12 nach Phase 2 verschoben (Entscheidung 5)
- Startdatum des Spiels: Spielstand, steht je Instanz in spiel.json im Datenverzeichnis (Bezugspunkt der Auswertung, gesetzt beim Start in der Einrichtung → Spielstart bzw. mit tools/init.py nach Freigabe von AP12: heute, nie rückwirkend, kein fester Termin; Entscheidungen 11, 15 und 34)
- Letzte Session: Spielstand, ergibt sich aus dem Journal im Datenverzeichnis

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

- [ ] AP12 Testsession ohne Trades, Anlagerichtlinien, Freigabe und Initialisierung (AUFTRAG_PHASE1.md); je Instanz in der App: Testsession unter Claude-Läufe, Freigabe und Start unter Einrichtung → Spielstart
- [x] W0 Klärung der offenen Punkte zur Web-UI (Entscheidungen 1 bis 12)
- [ ] W1 bis W17 Web-UI (AUFTRAG_WEBUI.md); Stufe 1 (lesend) umgesetzt, Stand je Paket unten
- [x] App-Autarkie (2026-10-07): Spielstand nur im Datenverzeichnis, Einstellungen und Secrets in der App,
  Sessions im Container, Kurse mit Fallback-Kette, News über RSS (Abschnitt unten)
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
| W3 Authentifizierung | erfüllt: Admin-Erstanlage per CLI (nur einmal), Login (nur Passwort seit Entscheidung 40), serverseitige Sitzungen, CSRF und Origin-Prüfung, TOTP nur beim Anlegen von Benutzern, Sperre bei Fehlversuchen, Passwortwechsel | Rate-Limits im Prozess statt Redis (ein API-Prozess) |
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
  Passwörter dürfen beliebige Zeichen enthalten (die API baut die DB-URL aus Einzelteilen und maskiert das
  Passwort; Init- und Abgleichskript quotieren per psql-Variable). Anleitung:
  webui/PORTAINER.md. Das Root-Zertifikat ist unter /stockmaster-root.crt abrufbar (nur Heimnetz).
- Startreihenfolge (2026-10-06, Fund bei der Einrichtung in Portainer): Der PostgreSQL-Healthcheck über
  den Unix-Socket meldete „bereit“, solange noch der temporäre Init-Server lief; die API startete zu früh
  und stürzte ab. Behoben durch Healthcheck über TCP, Wartelogik der API (bis zu 2 Minuten, mit klarer
  Meldung) und einen Passwortabgleich des DB-Images bei jedem Start (geänderte Passwörter bei vorhandenem
  Volume). Der Proxy hängt nicht mehr am API-Healthcheck.
- Veraltete Images (2026-10-06, zweiter Fund in Portainer): Compose zieht ein vorhandenes `latest` nicht
  neu; der Redeploy startete weiter den alten Code. Der Stack nutzt jetzt `pull_policy: always`, die API
  schreibt ihre Version (Commit) als erste Logzeile, der DB-Healthcheck prüft die Anmeldung der
  Anwendungsrolle (API startet erst nach dem Passwortabgleich), und abgelehnte Anmeldungen werden
  mehrfach wiederholt, bevor die API aufgibt.
- Sonderzeichen in Passwörtern (2026-10-06, dritter Fund in Portainer): Die frühere Regel „nur Buchstaben
  und Ziffern“ ließ das Init-Skript beim ersten Start abbrechen; die halb initialisierte Datenbank hatte
  keine Anwendungsrolle (`role "stockmaster" does not exist`). Regel entfernt, Passwort getrennt von der
  URL, Abgleich legt fehlende Rolle und Datenbank an.
- Ungültiger Schlüssel (2026-10-06, vierter Fund in Portainer): Beim Einfügen ging das `=` am Ende von
  `SM_SCHLUESSEL` verloren (Fehler „Incorrect padding“). Die API startete trotzdem, meldete sich gesund und
  scheiterte erst bei der ersten Anmeldung mit Fehler 500, weil jede Anmeldung die IP mit dem Schlüssel
  hasht. Behoben: Der Schlüssel wird beim Start geprüft (`migrieren`, `admin-anlegen` und beim Start der
  Anwendung); ein ungültiger Wert verhindert den Start mit klarer Meldung (ohne den Wert zu nennen).
  Formfehler beim Kopieren (fehlendes `=`, Anführungszeichen, Leerraum, URL-sichere Schreibweise) werden
  korrigiert und im Log gemeldet; bisher gültige Schlüssel liefern unverändert dieselben Bytes, damit
  gespeicherte Zwei-Faktor-Geheimnisse gültig bleiben. `/api/health` prüft jetzt Schlüssel und Datenbank
  (503 ohne Details), und der Rauchtest meldet sich mit dem Einmalpasswort an. Eine automatische
  Schlüsselerzeugung gibt es bewusst nicht (Schlüssel und Sicherung bleiben ausdrücklich).
- Zugriff per IP-Adresse (2026-10-06, fünfter Fund in Portainer): `https://<IP>` scheiterte mit
  `ERR_SSL_PROTOCOL_ERROR`. Ein Browser sendet bei einer IP keinen Servernamen (SNI), und hinter Docker sieht
  Caddy als lokale Adresse die des Containers, nicht die getippte; es fand kein Zertifikat. Behoben mit der
  optionalen Variable `SM_ZUSAETZLICHE_HOSTS` (weitere Namen oder IPs): `default_sni` liefert Clients ohne
  Servernamen das Zertifikat der ersten IP, ein Fangblock erklärt unbekannte IP-Adressen (HTTP 421) statt
  einer leeren Seite. `webui/deploy/proxy-start.sh` prüft alle Namen streng, bevor sie in die Caddyfile
  gelangen (keine Platzhalter, Ports, Klammern, Zeilenumbrüche), und startet Caddy. Die Heimnetz-Schranke
  gilt unverändert für alle Namen. Mit echtem Caddy nachgestellt und getestet, auch unter BusyBox-ash.
- Anmeldeseite (2026-10-06): Der Text der Markenfläche stand unten über den Kurven und war schlecht lesbar;
  er steht jetzt oben, die Kurven bleiben unten.
- Die Web-UI importiert die Werkzeuge des eingebundenen Spiel-Repositorys
  und ruft keine Kurse ab (Kursquelle im Prozess durch eine Attrappe ohne
  Netzwerk ersetzt); das Repository ist nur lesend eingebunden.
- E-Mail-Adressen werden bewusst einfach geprüft, damit Heimnetz-Adressen
  wie name@heimnetz.local möglich sind.
- In der Cloud-Umgebung von Claude Code sind Yahoo Finance und die
  Debian-Paketquellen gesperrt. Der Docker-Rauchtest lief dort mit einem
  Test-Image ohne git; der vollständige Build läuft in der GitHub Action.

## App-Autarkie (2026-10-07)

Der Docker-Stack läuft autark; GitHub liefert nur das Framework. Betrieb: webui/BETRIEB.md und
webui/PORTAINER.md.

- Pfade: tools/pfade.py trennt Framework (Code, regeln.md, config/) und Datenverzeichnis
  (`STOCKMASTER_DATA_DIR`, im Container /data). Spielstand wird nie relativ zum Repository gelesen.
- Spielstand-Git: Das Datenverzeichnis ist ein eigenes Git-Repository ohne Remote; session.py und
  `tools/datenverzeichnis.py commit` committen dort, `pruefe.py --historie` prüft diese Historie (auch
  news/ nur anhängen) und warnt bei einem Remote. Leeres Volume: Erstinitialisierung aus
  vorlagen/datenverzeichnis/. Altes Layout: `tools/migriere.py --von <alte-arbeitskopie>` mit
  Herkunftsvermerk. Die Spielstand-Ordner sind aus dem Repository entfernt (frühere Commits unverändert).
- App-Konfiguration (/data-app, getrennt vom Spielstand): Einstellungen, Secrets mit AES-256-GCM,
  Master-Schlüssel 0600 (beim ersten Start erzeugt oder einmalig aus SM_SCHLUESSEL übernommen);
  Datenbank-Passwörter erzeugt der DB-Container im Volume geheim. Der Portainer-Stack braucht nur noch
  SM_HOSTNAME.
- Dienst worker: einziger mit Internetzugang; Kurse (5 Min. bei offenem Markt, sonst stündlich, einmal
  nach Schluss), News (15 Min.), Zeitplan, Claude-Sessions mit Live-Log, Verbindungstests; die API hat
  kein Internet.
- Kurse: Adapter mit Fallback-Kette Finnhub/Twelve Data → yfinance → letzter bekannter Kurs nur zur
  Anzeige („veraltet“). Ursache von „Markt & Kurse ist leer“: Kurse entstanden bisher nur während
  Sessions (data/historie/), und die Web-UI ruft absichtlich nichts ab; vor dem Spielstart gab es keine
  Session, also keine Daten. Jetzt füllt der worker die Übersicht laufend.
- News: tools/news.py (feedparser), Standard-Feeds in config/news.json, Änderungen in der App.
- Claude: Optionen für Modell und Aufwand in config/claude.json, geprüft gegen `claude --help` der im
  Image fest installierten Claude Code 2.1.292 (`--model`, `--effort low|medium|high|xhigh|max`).
- Web-UI: neue Seite „Einrichtung“ (Admin; Zwei-Faktor-Pflicht entfiel mit Entscheidung 40), bisherige Seite heißt „Roadmap & Status“,
  neue Seite „Claude-Läufe“, Cockpit-Hinweis auf offene Pflichtschritte, „Markt & Kurse“ mit Quelle,
  Zeitstempel und Verzögerung, News im Cockpit und je Wert, Sicherung (Export/Restore).

## Umbau v2 (2026-10-09)

Auftrag der Auftraggeber: sechs Änderungen in vier Stufen (je Stufe ein Branch und ein Pull Request). Die
Auftraggeber erlauben dafür ausdrücklich Änderungen an regeln.md, CLAUDE.md, config/ und den Anlagerichtlinien;
das ist eine Ausnahme zu CLAUDE.md Grundsatz 1 und gilt nur für diesen Auftrag. Unklarheiten entscheidet Claude
selbst (regeln.md 12, Entscheidung 34); die Auslegungen stehen unter den Entscheidungen ab Nr. 40.

| Stufe | Punkte | Branch | Pull Request | Stand |
| --- | --- | --- | --- | --- |
| A | 1 Zwei-Faktor nur beim Anlegen neuer Benutzer | `aufbau/zwei-faktor-nur-beim-anlegen` | #20 | umgesetzt, CI grün (Entscheidung 40) |
| B | 2 Zeitfenster entfernen, 3 Handeln höher priorisieren | `aufbau/laeufe-ohne-zeitfenster-handeln-zuerst` | #21 (baut auf A) | umgesetzt, CI grün (Entscheidungen 41, 42) |
| C | 5 Ausführung ohne Claude-Lauf | `aufbau/ausfuehrung-ohne-claude-lauf` | #22 (baut auf B) | umgesetzt, CI grün (Entscheidung 43) |
| D | 4 Viertes Portfolio „Overnight“, 6 Regeln (v1.4) | `aufbau/viertes-portfolio-overnight` | #23 (baut auf C) | umgesetzt (Entscheidungen 44, 45) |

Die Pull Requests sind gestapelt: Jeder hat den Branch der vorigen Stufe als Basis, damit der Diff nur die eigene Stufe
zeigt. Zusammenführen in der Reihenfolge A, B, C, D (GitHub stellt die Basis des Folge-PR nach jedem Merge auf `main`
um). Abnahme (lokal und in der CI): Werkzeuge 292 Tests, Backend 312, Oberfläche 45, E2E 4, `pruefe.py --historie` auf
Demo- (mit simulierten Overnight-Nächten) und leerem Datenverzeichnis bestanden.

Ausgangslage (geprüft am 2026-10-09 auf `main` nach Pull Request 19): Werkzeuge 234 Tests, Backend 292, Oberfläche 39
(Komponenten) und E2E grün. Abweichungen zwischen Doku und Code, die dabei auffielen: (a) Entscheidung 37 und 39 sowie
`einrichtung.py` sprechen von „Administratoren mit Zwei-Faktor“; mit Stufe A gilt das nicht mehr. (b) CLAUDE.md
beschreibt „Modus bestimmen“ über das Startdatum, `buchen.py` lehnt Orders vor dem Startdatum ab, und der Lauf-Prompt
beschränkt Läufe dann auf Recherche (Entscheidung 33); alles entfällt mit Stufe B. (c) Ein Verzeichnis `webui/worker`
gibt es nicht; der Hintergrunddienst ist `webui/backend/stockmaster/worker.py` (Dienst `worker` im Compose).
(d) „Drei Profile“ ist in `tools/gemeinsam.py` (`PROFILE`), `appdaten.py` (`VORGABEN_PROFILE`), im Frontend
(`Profil`-Typ, Farben, Namen) und in regeln.md fest verdrahtet.

Inventur je Punkt (alle betroffenen Stellen, Stand vor der Umsetzung):

1. **Zwei-Faktor.** Backend: `auth.py` (Schritte `totp` und `zwei_faktor_einrichten` in `naechster_schritt`, Route
   `POST /api/auth/totp`, `totp/einrichten`, `totp/aktivieren`, `totp/deaktivieren`; Admins ohne TOTP kommen nicht
   über die Anmeldung hinaus), `auftraege.py` (`admin_2fa`/`Admin2FA`: Admin und `totp_aktiv`), verwendet in
   `einrichtung.py` (Router und rund 20 Routen), `auftraege.py` (Läufe starten und abbrechen), `freigaben.py`,
   `sicherung.py`; `admin.py` (`benutzer_anlegen` verlangt nur das Passwort, `zwei-faktor-zuruecksetzen`);
   `__main__.py` (Text der Admin-Erstanlage). Frontend: `Anmeldung.tsx` (TotpFormular, ZweiFaktorEinrichten),
   `Verwaltung.tsx` (Konto: Zwei-Faktor, Benutzer anlegen), `api.ts` (`Schritt`), Hinweistexte in `Einrichtung.tsx`.
   Tests: `conftest.py` (`anmelden` mit TOTP-Schritt, Fixture `admin` mit TOTP), `test_auth.py`, `test_admin.py`,
   `test_einrichtung.py`, E2E (`ablauf.spec.ts`, TOTP-Hilfen). Doku: AUFTRAG_WEBUI.md (Abschnitte 6 und 7),
   BETRIEB.md, PORTAINER.md, README.md, STATUS.md (W3, Entscheidungen 16, 37, 39).
2. **Zeitfenster und Datumsmechanik.** `tools/buchen.py` (`portfolio_pruefen`: „Das Spiel beginnt erst am …“),
   `tools/init.py` (`--vorziehen`, `vorziehen_pruefen`), `auftraege.py` (`lauf_pruefen(geplant=True)`, `hinweise`,
   `GET /api/laeufe/vorpruefung`), `worker.py` (`zeitplan`: Termin ohne Handelstag wird „kein Handelstag“, Fenster von
   30 Minuten, `geplanten_lauf_anlegen` meldet „übersprungen“ und markiert den Termin als erledigt;
   `richtlinien_standard` und `nachbuchen` warten auf das Startdatum), `claude_lauf.py` (Prompt: „nur Marktüberblick …
   keine Order versuchen“), `einrichtung.py` (Pflichtschritt „Spiel starten“, Checkliste, `vorziehen`),
   `tools/session.py`/`richtlinien.py` (Anzeige „Startdatum fehlt“), Frontend `Laeufe.tsx` (Hinweise im Startdialog)
   und `Einrichtung.tsx` (Spielstart, Vorziehen), CLAUDE.md („Modus bestimmen“, Entwicklungsmodus), STATUS.md
   (Entscheidungen 26, 33, 34). Bewusst nicht betroffen: die Wochentage und Uhrzeiten des Zeitplans selbst (fester
   Termin nur für geplante Läufe), Handelszeiten als Bedingung der Ausführung (regeln.md 5), das Kursalter, der
   Review-Rhythmus nach Spielzeit und die Kalendertage der Nachbuchung.
3. **Handeln priorisieren.** CLAUDE.md (Rolle, Haltung, Schritt 7, Session-Vorlage), `config/richtlinien/*.md`,
   `claude_lauf.py` (Trading-Prompt, `vorgaben_prompt`), regeln.md 10 und 12, STATUS.md Entscheidung 39 (Auslegung 2),
   Platzhalter im Editor „Vorgaben je Portfolio“ (`Einrichtung.tsx`), Warnungen in `pruefe.py` und im Cockpit
   (`Cockpit.tsx`, Backend `spiel/lesen.py`).
4. **Viertes Portfolio.** `tools/gemeinsam.py` (`PROFILE`, `limits_fuer`, `richtlinien_offen`, `vorhandene_profile`),
   `init.py`, `limits.py`, `buchen.py` (argparse `choices`), `bewertung.py` (Benchmark je Profil, Ranking, NAV),
   `pruefe.py` (Prüfungen je Profil, Abschnitt 7 gegen `config/profile.json`), `termine.py` (Monatsvergleich),
   `richtlinien.py`, `config/profile.json`, `config/richtlinien/`, `appdaten.py` (`VORGABEN_PROFILE`),
   `spiel/lesen.py` und `spiel/router.py` (Portfolios, Ranking), `einrichtung.py` (Vorgaben), `claude_lauf.py`,
   `webui/demo/demo_daten.py`, Frontend (`Profil`-Typ in `api.ts`, `PROFIL_NAME`/`PROFIL_FARBE` in `ui.tsx`,
   `styles.css`, `Bausteine.tsx`, `AppRahmen.tsx`, Cockpit, Portfolio, Analyse, Anmeldung, App-Icon
   `assets/icons/drei-profile.svg`), Tests (`tests/` und `webui/backend/tests/`), regeln.md 2, 7, 9, 11, README,
   CLAUDE.md, KONZEPT.md.
5. **Ausführung ohne Lauf.** Heute führt nur `buchen.py` (Market-Order bei offenem Markt, sonst Vormerkung) und
   `bewertung.py nachbuchen` (Tageskerzen, nur bis gestern, mit Session-Sperre) Orders aus; der Worker bucht nachts um
   00:30 nach (Entscheidung 38). Es gibt keine fortlaufende Ausführung während der Handelszeit. Vorhandene Bausteine:
   `kurse.py` (protokollierte aktuelle Kurse, `markt_offen`, Eröffnung und Schluss je Börse mit Frühschlüssen),
   `buchen.kauf_ausfuehren`/`verkauf_ausfuehren`/`wertlos_ausbuchen`, `limits.pruefe_kauf`, `gemeinsam.schreibsperre`
   (kurze Sperre je Schreibvorgang, nicht über Lesen-Ändern-Schreiben), Kurstakt des Workers (`planen`, 5 Minuten).
   Es fehlen: Ausführung von Stops, Kurszielen, Knock-outs und Limits in Echtzeit, eine Sperre über den ganzen
   Buchungsvorgang, ein idempotenter Orderzustand, die Anzeige „automatisch ausgeführt“ und der Systemstatus
   „Ausführung“.
6. **Regeln.** regeln.md Abschnitte 2, 5, 6, 7, 9, 11, 12, 13, 14; `config/profile.json`; Prüfung
   `pruefe_config_regeln` gleicht Abschnitt 7 mit `config/profile.json` ab (liest die Profile aus der Tabelle).

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

Auslegungsentscheidungen vom 2026-10-07 (Claude im Auftrag "App-Autarkie, Einrichtungsseite, Kurse und
News"; innerhalb von regeln.md und config/profile.json, ohne Limits, Kosten oder Risikogrenzen zu ändern):

15. Zum Spielstand gehören neben den im Auftrag genannten Ordnern auch spiel.json (Startdatum und
    Freigabe; früher eine Zeile in STATUS.md) und news/. STATUS.md, regeln.md und config/ bleiben
    Framework, weil sie Regeln und Projektstand beschreiben, nicht den Spielverlauf einer Instanz.
16. Spielstart aus der Web-UI nur mit Freigabe nach AP12 durch eine Auftraggeber-Kennung (regeln.md
    Abschnitt 2), Passwortbestätigung und Kursdaten für den Benchmark; Testsession und Claude-Test sind
    empfohlen, nicht Pflicht, weil die Freigabe allein Sache der Auftraggeber ist.
17. Kurse aus der Fallback-Kette werden mit der tatsächlich genutzten Quelle protokolliert. Ein Anbieter
    wird nur für Ticker gefragt, die dort dasselbe Instrument sind (Indizes und Futures bleiben bei
    yfinance); Tagesdaten kommen weiter aus yfinance, damit die Split-Rückrechnung einheitlich bleibt.
18. Der „letzte bekannte Kurs“ ist nur Anzeige („veraltet“), wird nie protokolliert und nie gebucht
    (regeln.md 1.4: ohne verlässlichen Kurs kein Handel).
19. Hintergrundabrufe protokollieren ihre Kurse in data/kurse/ wie jede Abfrage über tools/kurse.py; sie
    buchen nichts. Der worker committet sie höchstens stündlich lokal mit Präfix „daten:“, nie während
    einer Session.
20. Die Testsession (AP12) schreibt weder Journal noch Orders, damit der Spielstand vor dem Startdatum
    leer bleibt; das Ergebnis steht im Lauf-Log.
21. Der erste Administrator wird weiter per Kommandozeile angelegt (`admin-anlegen`, nur einmal). Es gibt
    keinen Weg über Umgebungsvariablen, deshalb ist kein Erststart-Assistent nötig.
22. Der Master-Schlüssel wird beim ersten Start automatisch erzeugt (ersetzt die frühere Festlegung „keine
    automatische Schlüsselerzeugung“). Gibt es Zwei-Faktor-Geheimnisse ohne Schlüssel, erzeugt die App
    keinen neuen, sondern verlangt einmalig SM_SCHLUESSEL, damit niemand ausgesperrt wird.
23. Ausnahme zu Entscheidung 7: tools/ nutzt zusätzlich feedparser (ausdrücklich beauftragt); HTTP für
    Kurs-APIs über die Standardbibliothek.
24. Modell und Aufwand: Optionen in config/claude.json statt im Frontend; Unverträglichkeiten werden vor
    dem Speichern angezeigt, und lehnt die CLI eine Kombination ab, bricht der Lauf mit deren Meldung ab
    (kein stilles Zurückfallen auf Standardwerte).
25. Claude-Anmeldung aus der App (2026-10-07, Wunsch der Auftraggeber): Der worker führt
    `claude setup-token` im Container aus; Link und Code laufen über die Einrichtung, das Token wird nie
    angezeigt. Der Ablauf hängt an der interaktiven Ausgabe der CLI (keine stabile Schnittstelle) und ist
    gegen Claude Code 2.1.292 geprüft (Link, Eingabe, Ablehnung eines ungültigen Codes); den Erfolgsfall
    deckt ein Test mit einer Attrappe ab. Das manuelle Eintragen bleibt als Ausweg.

Ergebnisse der Testsession (AP12) vom 2026-10-07 und Entscheidungen dazu (Claude im Auftrag der
Auftraggeber, innerhalb von regeln.md; keine Limits, Kosten oder Risikogrenzen geändert):

26. Anlagerichtlinien (regeln.md 11, AP12 Punkt 2) entstehen in einer **eigenen Session vor der ersten
    Trading-Session**: Laufart „Anlagerichtlinien ausformulieren“ (`session.py start --art richtlinien`,
    Vorlage mit den verbindlichen Limits aus `python tools/richtlinien.py vorlage`). Begründung: Die
    Richtlinie braucht Recherche und Zeit, die eine Trading-Session mit Orders nicht nebenbei haben soll;
    die Trennung hält die Prüfspur sauber. (Die ursprüngliche Ablehnung manueller Trading-Läufe in der App
    ist mit Entscheidung 33 durch Hinweise ersetzt.) `pruefe.py` meldet eine Vorlage nach dem Spielstart als Warnung (kein Fehler, damit die
    Prüfung Sessions nicht blockiert). Cockpit und Einrichtung zeigen den offenen Schritt.
27. AP12 gehört zur Instanz: Die Checkbox in STATUS.md bleibt als Framework-Vorlage offen (sie gilt für alle
    Instanzen und wird nicht je Instanz abgehakt). „Roadmap & Status“ leitet den Stand aus dem
    Datenverzeichnis ab: erledigt, wenn das Spiel gestartet (spiel.json mit Freigabe) und alle Richtlinien
    ausformuliert sind; das Detail nennt, was fehlt.
28. Testsessions, Richtlinien-Sessions und Review-Sessions schreiben keine Session-Einträge: Die Sperre
    merkt die Art (`--art`), `session.py ende` warnt dann nicht mehr. Trading-Sessions warnen weiter.
29. News: Je Feed filtern `titel_enthaelt` und `titel_ohne` das Rauschen aus (ganze Wörter, „Gold“ trifft
    nicht „Goldman“); Gold und Öl sind getrennte Feeds mit eigenem Ticker, MSCI World sucht nur im Titel;
    gleiche Titel aus mehreren Feeds oder Länderausgaben werden nur einmal gespeichert; bei Google News
    steht der Herausgeber im Feld `herausgeber` (der Link ist dort nur eine Weiterleitung, ein Auflösen
    wäre ein weiterer Abruf je Meldung), der Titel ohne Herausgeber-Suffix. Im Journal gilt für solche
    Meldungen News-ID, Link und Herausgeber als Beleg.
30. Echtzeit-Anbieter: Empfehlung Finnhub (kostenlos, Echtzeit für US-Aktien und -ETFs). Xetra, Indizes und
    Futures bleiben bei yfinance (etwa 15 Minuten, unter der Grenze von 30 Minuten), weil die kostenlosen
    Zugänge sie nicht als dasselbe Instrument führen; ein Key wird nicht von Claude, sondern von den
    Auftraggebern in der Einrichtung eingetragen. Die Einrichtung zeigt bei „Nur yfinance“ einen Hinweis.
31. `ranking.md` verwendet das Dezimalkomma (Anzeige für Menschen); Dateien und Berechnung bleiben beim
    Punkt.
32. Das Ergebnis eines Claude-Laufs wird vollständig gespeichert und als Markdown angezeigt (vorher
    gekürzt auf 2.000 Zeichen). Die Erlaubnisliste der Läufe kennt `git -C <pfad> log/status/diff/show`;
    `git push`, `remote`, `config` und `reset` sind auch mit `-C` verboten.
33. (Teile ersetzt durch Entscheidung 41: Vorprüfung, Überspringen und Startdatum-Sperre entfallen.) Läufe lassen sich jederzeit manuell und geplant starten und stoppen; es gibt kein festes Enddatum
    (regeln.md: „Kein festes Enddatum“) und kein zwingendes Startdatum für die App:
    - **Manuell** startet jeder Lauf immer (Admin, Bestätigung, Token, höchstens ein Lauf, Session-Sperre).
      Der Startdialog zeigt nur Hinweise (`GET /api/laeufe/vorpruefung`): Spiel nicht gestartet,
      Startdatum in der Zukunft, Anlagerichtlinien offen. Der Trading-Prompt weist Claude an, dann nur zu
      recherchieren und zu dokumentieren. Orders vor dem Startdatum lehnt `buchen.py` weiterhin ab
      (regeln.md 2, unverändert); damit bleibt das Backdating-Verbot technisch gesichert.
    - **Geplant** (Zeitplan-Automatik) überspringt einen Trading-Termin mit Grund im Zustand, wenn er nichts
      bewirken würde (nicht gestartet, Startdatum in der Zukunft, Richtlinien offen), und schont so das
      Abo-Kontingent; Reviews laufen immer.
    - **Stoppen:** „Lauf stoppen“ bricht den laufenden Lauf ab (Prozess beendet, Sperre freigegeben);
      „Automatik stoppen/starten“ auf der Lauf-Seite schaltet den Zeitplan (`POST
      /api/einrichtung/zeitplan/automatik`, Admin, Audit; Zwei-Faktor entfiel mit Entscheidung 40) ohne die Termine zu verlieren.
      `GET /api/laeufe/plan` zeigt Automatik, nächste Termine (Wochentag, Zeitzone, Handelstag) und die
      zuletzt übersprungenen.
    - **Startdatum:** Vorschlag im Spielstart ist heute. Ein bereits gesetztes, noch unberührtes
      Startdatum lässt sich auf heute vorziehen (`tools/init.py --vorziehen`, in der App mit Passwort):
      nur nach vorne, nie vor heute (kein Backdating), nur wenn keine Session läuft und keine Buchung, Order,
      Position, Nachbuchung oder Bewertung existiert (die Historie ändert sich nicht). Das alte Datum bleibt
      in `spiel.json` (`startdatum_vorher`) und im Commit nachvollziehbar.
    (Fortgeführt und ersetzt in Teilen durch Entscheidung 34.)
34. Auftrag vom 2026-10-07 („von den fixen Daten komplett wegkommen“, offene Fragen und Anlagerichtlinien
    selbst entscheiden, Regeländerung ausdrücklich erlaubt). regeln.md v1.3, umgesetzt in Werkzeugen und App:
    - **Kein fester Start- oder Endtermin.** Das Spiel beginnt beim Start in der App (`init.py` ohne
      `--startdatum` = heute, auch am Wochenende; ein Handelstag ist nicht nötig, weil Zins und Benchmark
      ab dem ersten Schlusskurs rechnen). Ein Datum vor heute bleibt Backdating und wird abgelehnt. Die
      Einrichtung hat kein Datumsfeld mehr. Das gespeicherte Startdatum ist nur noch der Bezugspunkt der
      Auswertung.
    - **Feste Zeiten nur im Zeitplan geplanter Läufe**, nicht in Bewertung, Benchmark, Limits oder Reviews.
    - **Reviews nach Spielzeit statt Kalender** (regeln.md 11): Zeiträume zu 7 Tagen (Woche), 28 Tagen
      (Monat) und 91 Tagen (Quartal) ab dem Starttag; Dateien `reviews/JJJJ-MM-TT_woche|monat|quartal.md`
      mit dem letzten Tag des Zeitraums. Begründung: Ein Start mitten in der Woche liefert sonst eine
      halbe Kalenderwoche, und die Auswertung hinge am Kalender. Bereits vorhandene Reviews nach dem alten
      Namensschema bleiben als Historie liegen; nur der Starttag eines neuen Spiels ist Bezugspunkt.
    - **Anlagerichtlinien:** Claude hat die drei Standard-Richtlinien ausformuliert
      (`config/richtlinien/<profil>.md`, Limits aus `config/profile.json` eingesetzt). Sie gelten ab
      Spielstart: `init.py` legt sie an, der Hintergrunddienst übernimmt sie in bestehenden Instanzen, wo
      noch die Vorlage steht (`tools/richtlinien.py standard`, überschreibt nie eine eigene Richtlinie),
      und der Trading-Prompt weist Claude an, dasselbe zu tun. Die Marktsicht entsteht je Session mit
      Quellen; die Richtlinie enthält bewusst keine Prognose. Der Lauf „Anlagerichtlinien ausformulieren“
      bleibt für individuelle Anpassungen (Änderung mit Datum, Anlass, Prüfkriterium).
    - **Offene Frage 20 (Profilauswahl) entschieden:** Es bleiben immer alle drei Profile; die in
      Entscheidung 13 beschriebene Profilauswahl (`profile_aktiv`) wird nicht umgesetzt. Begründung:
      regeln.md beschreibt drei Portfolios, Werkzeuge, Benchmark und Vergleich setzen sie voraus, und ein
      späteres Abschalten würde Historie und Vergleichbarkeit beschädigen. Eine Auswahl wäre eine eigene,
      größere Änderung.
    - **Claude entscheidet Unklarheiten** im Sinne von Kapitalerhalt und Nachvollziehbarkeit und
      dokumentiert sie hier (regeln.md 12); Limits, Kosten und Risikogrenzen bleiben unverändert.
    - **Absturz der Seite „Claude-Läufe“** (Fehlermeldung „Something went wrong“): Die Ursache ließ sich im
      Test nicht auslösen; deshalb wurde jede denkbare Stelle gehärtet. Die Zeitformatierung wirft bei
      ungültigen Werten nicht mehr, Markdown-Ergebnisse haben eine eigene Fehlergrenze (Ersatz:
      Rohtext) und verlinken nur noch Trade-Akten und externe Adressen, und die Fehlerseite des Routers
      nennt die technische Meldung und bietet „Seite neu laden“. Ein E2E-Test öffnet die Seite mit
      laufendem und fertigem Lauf, Zeitplan und Session-Sperre.
35. Seite „Claude-Läufe“, Fehler „l is not a function“ (2026-10-07, zweiter Absturzbericht): **Ursache gefunden
    und behoben.** Der Effekt im Log (`useEffect(() => ende.current?.scrollIntoView(...))`) gab den
    Rückgabewert von `scrollIntoView` an React zurück, und React ruft diesen Wert beim Aufräumen als
    Aufräumfunktion auf. Neuere Browser (nachgewiesen mit Chrome 153) liefern von `scrollIntoView()` ein Promise
    (Chromium 141: nichts); aus dem Aufruf wurde „… is not a function“, und beim Wechsel oder Verlassen des Laufs
    brach die ganze Seite ab. Deshalb ließ sich der Fehler mit dem älteren Browser der Entwicklungsumgebung nicht
    nachstellen; in der CI (aktuelles Playwright-Chromium) scheiterte der E2E-Test dagegen jedes Mal. Behoben:
    Der Effekt hat einen Block als Rumpf; die beiden anderen Effekte mit Ausdruck als Rumpf (`AppRahmen`,
    `Entscheidungen`) ebenso. Ein Komponententest simuliert das Promise, ein Quelltext-Test lässt keinen Effekt
    mit Ausdruck als Rumpf mehr zu. Zusätzlich ist jeder Bereich der Seite (Startdialog, Zeitplan, Liste,
    Lauf-Ansicht, Log) einzeln abgesichert, die Zeitplan-Leiste verträgt eine unvollständige Antwort, und die
    Fehlerseiten zeigen „Einzelheiten“ (Stack-Auszug).
36. Systemstatus und News-Fehler (2026-10-07, Rückmeldung eines Auftraggebers: gelber Punkt ohne erkennbaren Grund,
    Meldung „1 mit Fehler“ ohne Angabe, welcher Feed): **Umgesetzt.** Systemstatus: Zeilen mit Hinweis (gelb) oder
    Problem (rot) sind farblich hinterlegt, mit Beschriftung („Hinweis“/„Problem“, nie nur Farbe), und ein Banner
    „Gesamtstatus“ oben nennt die betroffenen Zeilen; Punkt in der Navigation und Banner nutzen dieselbe Funktion.
    Jede Zeile nennt die Ursache (auch „überfällig“ bei Kurs- und News-Abruf) und verlinkt auf den Bereich, in
    dem sich das beheben lässt. News: `tools/news.py` übersetzt Fehler in Klartext mit Abhilfe (HTTP 403/404/429/5xx,
    Zeitüberschreitung, DNS, TLS, abgelehnte oder abgebrochene Verbindung, Webseite statt Feed, leere Antwort, zu
    groß) und führt je Feed `url`, `art`, `hinweis`, `seit`, `in_folge` und `letzter_erfolg` in
    `.cache/news_stand.json` (nicht im Spielstand). Die Abschlussmeldung nennt die Feeds und den Grund („News: 3 neue
    Meldungen aus 18 Feeds, 1 mit Fehler – SEC 8-K: Zugriff verweigert (HTTP 403).“); der Hintergrunddienst
    zeigt sie ohne doppeltes Präfix. Einsehbar: Systemstatus-Zeile „Letzter News-Abruf“ mit Einzelheiten (höchstens
    fünf Feeds, Rest als Verweis), Bereich „News“ mit Abrufstatus (ausgefallene Feeds mit Ursache, Dauer und
    Abhilfe, aufklappbar alle Feeds) und Hinweis am betroffenen Feed in der Liste. „Jetzt abrufen“ meldet
    ausgefallene Feeds als Warnung statt als Erfolg. Stufen unverändert: gelb bei mindestens einem fehlerhaften
    Feed oder überfälligem Abruf, rot erst, wenn alle Feeds ausfallen. Tests: Werkzeug (Klartext je Ursache,
    Verlauf, Zusammenfassung), Backend (Details, Status je Feed, Worker), Oberfläche (Färbung, Banner, Details,
    Abrufstatus) und E2E.
37. Freigaben in der Web-UI (2026-10-07; Auftrag eines Auftraggebers nach einem Testlauf, in dem ein Shell-Befehl mit
    Schleife und Pipe abgelehnt wurde: „Approval Surface“, auch für Läufe ohne Bedienung, drei Minuten Wartezeit,
    Schreiben in den Spielstand bleibt gesperrt): **Umgesetzt.** Bisher lief die CLI mit
    `--permission-prompts none`: Was weder erlaubt noch verboten war, wurde ohne Rückfrage abgelehnt. Jetzt
    startet der Worker sie mit `--input-format stream-json --permission-prompt-tool stdio`; der Auftrag geht über
    stdin, und die CLI fragt Befehle, die weder auf der Positivliste noch unter den Verboten stehen, per
    `control_request` an. Der Worker legt je Anfrage eine Zeile in `freigaben` an, die Web-UI zeigt sie im Lauf
    (Befehl Zeichen für Zeichen ohne Ligaturen, Beschreibung von Claude als ungeprüft gekennzeichnet, Restzeit,
    „Erlauben“ und „Ablehnen“) und als Hinweis „n Freigaben offen“ in der Kopfzeile für Administratoren.
    Entscheiden dürfen nur Administratoren (seit Entscheidung 40 ohne Zwei-Faktor-Code; CSRF, Audit-Eintrag `freigabe_erlaubt` oder
    `freigabe_abgelehnt`; wer entschieden hat, steht nur in der Datenbank). Eine Freigabe gilt nur für den einen
    Aufruf. Ohne Entscheidung verfällt die Anfrage nach `SM_FREIGABE_WARTEZEIT_SEKUNDEN` (Standard 180) und gilt als
    abgelehnt; deshalb hängen auch Zeitplan-Läufe nie. Ein schon abgelehnter oder verfallener Befehl wartet im
    selben Lauf nicht erneut; Abbruch, Lauf-Ende und Neustart des Dienstes schließen offene Anfragen.
    Schichten, die zusammenwirken: (1) Verbotsregeln der CLI entscheiden vor jeder Anfrage und werden nie zur
    Freigabe vorgelegt (mit CLI 2.1.293 geprüft: `curl` unter `Bash(curl*)` wird ohne `control_request`
    abgelehnt). (2) `freigabe_regeln.py` lehnt ohne Rückfrage ab, was nicht erkennbar nur liest: nur Bash ist
    freigebbar; erlaubt sind lesende Werkzeuge (echo, printf, cat, head, tail, wc, sort, uniq, cut, tr, grep, awk,
    column, nl, tac, paste, comm, diff, ls, date, pwd, basename, dirname) und `python tools/…`, einfache
    `for`-Schleifen und Pipes; gesperrt sind Umleitungen in Dateien, Befehlsersetzung, Unterschalen,
    Hintergrundprozesse, schreibende oder ausführende Optionen (sort -o, tail -f, date -s, awk mit system, getline,
    `>`, `|` oder ENVIRON), Pfade außerhalb von Spielstand und Framework (kein /data-app, /proc, /etc, `..`, `~`),
    nicht definierte Variablen sowie Steuer- und Umkehrzeichen. Das ist eine Mustererkennung und kein Beweis.
    (3) `pruefe.py` nach jedem Lauf und die Git-Historie des Datenverzeichnisses. Konservative Auslegung (CLAUDE.md,
    Entwicklungsmodus), bitte am Ende bestätigen: `sed`, `find` und `xargs` sind nicht freigebbar, und im
    awk-Programm ist jedes `>` gesperrt (auch als Vergleich). Grenze: Ändert eine neue CLI-Version das Protokoll
    und beantwortet der Worker eine Anfrage nicht, endet der Lauf erst mit dem Zeitlimit. Der Lauf-Prompt nennt
    Claude die Regeln (einzelne Aufrufe bevorzugen, abgelehnte Befehle nicht wiederholen). Tests: Regeln (93 Fälle),
    Worker mit CLI-Attrappe (erlauben, ablehnen, Zeitablauf und Wiederholung, harte Sperre, Abbruch, Rechte,
    Dienststart), Oberfläche und E2E; zusätzlich ein Lauf mit der echten CLI (erlaubt: awk liefert 42; Verbot: curl
    ohne Anfrage; Sperre: Umleitung, Datei nicht angelegt).
38. Automatische Nachbuchung und Beobachtungsliste (2026-10-08; Rückmeldung eines Auftraggebers: vorgemerkte Orders
    wurden nicht ausgeführt, und der StockMaster solle „sämtliche Aktien und ETFs“ analysieren, schien sich aber nur
    auf die Werte in „Markt & Kurse“ zu beziehen; Entscheidung des Auftraggebers: feste, breite Liste mit yfinance und
    Nachbuchung nach Handelsschluss automatisch): **Umgesetzt.** Ursachen: (a) Eine Market-Order außerhalb der
    Handelszeit wird zur Eröffnung des nächsten Handelstags gebucht, aber erst bei der Nachbuchung (regeln.md
    Abschnitt 6), und die lief nur beim Session-Start; der Hintergrunddienst rief sie nie auf. (b) Die Marktübersicht
    zeigt nur Basiswerte, EUR/USD, den Benchmark-ETF und Werte aus Positionen und Orders; es gab keinen Blick auf das
    übrige Universum. Maßnahmen:
    1. **Nachbuchung nachts.** Der Worker bucht ab 00:30 Uhr deutscher Zeit nach: `session start --art nachbuchung`,
       `bewertung nachbuchen`, `bewertung bericht`, `pruefe`, lokaler Commit „session: Nachbuchung bis … (automatisch)“,
       `session ende`. 00:30 Uhr, weil `bewertung.py` nur Kalendertage bis gestern verarbeitet und der Handelstag
       (NYSE, Gold, Brent bis 22:00 Uhr) dann abgeschlossen ist: Eine Order, die am Abend des 8.10. vorgemerkt wird,
       wird zur Eröffnung am 9.10. ausgeführt und um 00:30 Uhr am 10.10. gebucht. Die neue Sperrart `nachbuchung`
       (nur der Dienst setzt sie) verlangt keinen Session-Eintrag und erlaubt keine Orders; Person ist der
       Auftraggeber des Zeitplans, sonst der erste in config/projekt.json. Nie während einer Session oder eines
       Laufs; bei Fehlern jede Stunde erneut, die Sperre wird immer freigegeben. Der Systemstatus zeigt die Zeile
       „Nachbuchung“ (Verbucht bis …, Rückstand gelb, ab drei Tagen rot, Prüfung mit Fehlern gelb). Sessions buchen
       weiterhin selbst nach, falls noch etwas offen ist.
    2. **Beobachtungsliste mit Screener.** `tools/beobachtung.py` rechnet aus Tagesdaten (yfinance, ein Jahr) Kennzahlen
       für die Listen in `config/beobachtung.json` (DAX 40, S&P 500, Nasdaq-100-Zusätze, 12 ETFs an Xetra, 32 ETFs in
       den USA; 603 Werte): Renditen über 1, 5, 20 und 60 Tage, Abstand zum 52-Wochen-Hoch und -Tief, Abstand zu den
       20- und 50-Tage-Schnitten, Eröffnungslücke, Volumen gegen den 20-Tage-Schnitt und Schwankung. Der Befehl
       `kandidaten` nennt je Kategorie die auffälligsten Werte (Tages- und Trendbewegung, Nähe zum Hoch, Volumen bei
       steigendem Kurs, Lücke), `liste`, `werte` und `pruefen` zeigen mehr. Der Worker aktualisiert den Stand je Handelstag
       ab 23:15 Uhr (nach Xetra und NYSE, vor der Nachbuchung; bei fehlendem Stand sofort; bei Fehlern stündlich); er liegt im
       Zwischenspeicher (`.cache/`), nicht im Spielstand. Die Web-UI zeigt ihn im Reiter „Beobachtungsliste“ unter
       „Markt & Kurse“ (Kandidaten, sortierbare Tabelle, Suche, Listenwahl), der Systemstatus als Zeile
       „Beobachtungsliste“. CLAUDE.md (Schritt 6) und der Lauf-Prompt verlangen den Screener und nennen die geprüften
       Kandidaten im Journal, auch bei Nichtstun.
    Die Kennzahlen sind Orientierung und keine Kurse im Sinne von regeln.md Abschnitt 5: Gebucht wird nur zu
    protokollierten Kursen aus `tools/kurse.py`, die Limits prüft `buchen.py` wie bisher.
    **Konservative Auslegungen, bitte bestätigen:** (1) regeln.md nennt die Nachbuchung in Abschnitt 2 („beim nächsten
    Session-Start“) und in Abschnitt 6 („Beim Session-Start …“). Der automatische Ablauf ist derselbe, regeln.md ist
    nicht geändert. Vorschlag für den Wortlaut, den die Auftraggeber selbst einfügen: „Die Nachbuchung erfolgt
    automatisch nachts durch den Hintergrunddienst (Sperre der Art nachbuchung) und spätestens beim Session-Start.“
    (2) Der Euro Stoxx 50 fehlt in den Listen: Werte ohne Xetra-Notierung (.PA, .AS, …) sind nach regeln.md Abschnitt 3
    nicht handelbar. (3) Der Mindestkurs von 1 EUR/USD wird je Wert geprüft; Werte darunter bleiben in der Liste,
    sind aber als „nicht handelbar“ gekennzeichnet und fehlen in den Kandidaten. (4) Zu den Werten der Liste gibt es
    keinen eigenen News-Feed; News bleiben bei Basiswerten, Positionen und Orders und kommen für Kandidaten aus der
    Web-Suche.
    **Grenzen:** yfinance ist inoffiziell (keine Zusicherung, kann drosseln oder Spalten ändern); der Abruf läuft in
    Blöcken zu 80 Werten, ein ausgefallener Block lässt nur seine Werte fehlen (sie behalten den alten Stand mit dem
    Kennzeichen „alter Stand“), ohne jede Antwort bleibt der bisherige Stand. Die Listen sind der Wissensstand vom
    Herbst 2025 und nicht gegen echte Daten geprüft (Yahoo ist aus der Entwicklungsumgebung nicht erreichbar):
    Indexwechsel und Umbenennungen sind nicht eingearbeitet; `python tools/beobachtung.py pruefen` und der
    Systemstatus nennen Werte ohne Kursdaten, die Auftraggeber pflegen die Listen. Der Abruf selbst ist nur mit
    synthetischen Antworten (beide Spaltenreihenfolgen, Einzelwert, Teilausfall) getestet, nicht gegen das echte
    yfinance. Tests: Werkzeuge 234 (30 neue für den Screener, Session-Art, Nachbuchung unter der neuen Sperre),
    Backend 286 (Worker-Takt von Nachbuchung und Abruf, Systemstatus, API), Oberfläche 34 und E2E.
39. Vorgaben der Auftraggeber je Portfolio (2026-10-08; Frage eines Auftraggebers: ob sich die Regeln der drei Portfolios
    in der Web-UI anpassen lassen, etwa „das aggressive Portfolio soll immer traden, sobald es irgendwo einen kleinen
    Gewinn sieht; kein Trade ist besser als Verlust, aber Nichtstun ist nie grundsätzlich neutral“; Entscheidungen des
    Auftraggebers: vorerst nur weiche Textvorgaben, keine Mindestschwelle für „kleinen Gewinn“, Änderungen gelten sofort
    und erscheinen in einem Verlauf, nur Administratoren ändern): **Umgesetzt.** Einrichtung → „Vorgaben je Portfolio“:
    je Portfolio ein Freitext (bis 4000 Zeichen). Jede Änderung ist eine Version (Text, Zeitpunkt, Kennung des
    Administrators, nie Name) im Verlauf der App-Konfiguration (`einstellungen.json`, damit in der Sicherung; die
    letzten 300 Fassungen); ein unveränderter Text legt keine Version an, eine alte Fassung lässt sich in den Editor
    übernehmen und neu speichern. Schreiben dürfen nur Administratoren (seit Entscheidung 40 ohne Zwei-Faktor-Code; CSRF, Audit-Eintrag
    `einrichtung_vorgabe` mit Version und Länge, ohne Text); lesen dürfen alle Angemeldeten (Reiter Anlagerichtlinie
    im Portfolio, ohne Verfasser). Wirkung: Der Prompt eines Trading-Laufs enthält die Vorgaben zwischen den Marken
    `VORGABE-BEGINN` und `VORGABE-ENDE` (Marken im Text werden entschärft) mit der Anweisung, dass sie die
    Anlagerichtlinie ergänzen, **nachrangig** gegenüber regeln.md, config/profile.json, CLAUDE.md und den Prüfungen der
    Werkzeuge sind, nichts erlauben, was dort verboten ist, und nur Handelsentscheidungen betreffen (nie Rechte,
    Werkzeuge, Dateien oder Freigaben). Widerspricht eine Vorgabe den Regeln, gilt die Regel, und Claude nennt den
    Konflikt im Session-Eintrag; dort trägt er je Portfolio Version und Umgang in der neuen Zeile „Vorgaben der
    Auftraggeber“ ein. Das Lauf-Log nennt die Versionen. Die Vorgaben gelten ab dem nächsten gestarteten Lauf; ein
    laufender Lauf behält seinen Stand. **Konservative Auslegungen, bitte bestätigen:** (1) Die Vorgaben ändern keine
    Zahl-Limits: Hebel, Exposure, Cash-Quote und Positionsgröße bleiben in regeln.md Abschnitt 7 bzw.
    config/profile.json. (2) [ersetzt durch Entscheidung 42] CLAUDE.md nannte Nichtstun eine gültige Entscheidung und verlangt Kapitalerhalt vor Rendite;
    eine Vorgabe kann die Anforderungen an die Begründung des Nichtstuns erhöhen („mit den geprüften Screener-Kandidaten
    begründen“), aber keinen Zwangstrade erzwingen. Die Platzhalter-Beispiele im Editor sind so formuliert. (3) Die
    Vorgaben stehen in der App-Konfiguration, nicht im Spielstand: Das Journal zitiert sie (mit Version), die
    Prüfspur im Datenverzeichnis enthält also, was Claude erhalten hat, aber nicht den Verlauf der Texte selbst.
    Grenzen: Eine Vorgabe ist eine Anweisung an ein Sprachmodell und keine Prüfung; ob sie befolgt wurde, zeigt nur der
    Session-Eintrag. Eine Vorgabe wie „immer traden“ ohne Einschränkung steht im Konflikt mit der Haltung in CLAUDE.md
    (Kapitalerhalt, Nichtstun ist gültig, Kosten von 1 EUR je Order plus 0,10 % Spread je Seite, Zertifikate 0,20 %); Claude
    folgt dann der Regel und meldet den Konflikt. Tests: Backend (Versionen, Verlauf und Begrenzung, Audit ohne
    Text, Rechte, Eingaben, Prompt mit Entschärfung der Marken), Oberfläche (Editor, Entwürfe je Portfolio, Verlauf,
    Lese-Karte) und E2E.
40. Zwei-Faktor nur beim Anlegen neuer Benutzer (Umbau v2, Stufe A, Auftrag der Auftraggeber vom 2026-10-09).
    **Umgesetzt.** Die Anmeldung braucht nur noch das Passwort (Argon2id, serverseitige Sitzung, CSRF, Rate-Limit und
    Sperre bei Fehlversuchen bleiben); der Schritt „Code bei der Anmeldung“ (`POST /api/auth/totp`) und der Pflichtschritt
    „Zwei-Faktor einrichten“ sind entfernt. Einen TOTP-Code verlangt die Web-UI nur noch, wenn ein Administrator einen
    neuen Benutzer anlegt (`POST /api/admin/benutzer` mit Feld `code`, zusätzlich zur Passwortbestätigung). Alle
    bisherigen „Admin + Zwei-Faktor“-Aktionen (Einrichtung, Vorgaben, Zeitplan und Automatik, Freigaben von
    Claude-Befehlen, Claude-Anmeldung, Spielstart, Sicherung, Läufe starten und abbrechen) behalten die
    Admin-Rollenprüfung (Rolle aus der Datenbank, Nicht-Admins erhalten 404), CSRF, den Audit-Eintrag und die schon
    vorhandene Passwortbestätigung, aber keinen Code (Abhängigkeit `admin_pflicht`, vorher `admin_2fa`). Vorhandene
    TOTP-Geheimnisse bleiben gespeichert und gültig (der Master-Schlüssel verschlüsselt sie weiter); niemand wird
    ausgesperrt, es gibt keine Datenbankmigration. Die Admin-Erstanlage per Kommandozeile bleibt.
    **Auslegungen:** (1) „Die Anmeldung braucht nur noch das Passwort“ gilt für alle Konten, auch für Benutzer mit
    schon aktivem TOTP; ihr Code wird nur beim Anlegen von Benutzern gebraucht. (2) Ein Administrator ohne eingerichtetes
    Zwei-Faktor kann sich anmelden und alles andere tun, aber keine Benutzer anlegen (409 mit Hinweis); der Dialog
    „Benutzer anlegen“ führt die Einrichtung (QR-Code, Bestätigung) gleich mit. (3) Ein falscher Code liefert 403 statt 401
    (die Oberfläche würde bei 401 abmelden), ist auf fünf Versuche je Minute begrenzt und steht als `totp_fehlgeschlagen`
    im Audit-Log; ein erfolgreiches Anlegen vermerkt `zwei_faktor` im Audit-Eintrag. (4) Zwei-Faktor lässt sich im Konto
    mit Passwort und Code auch von Administratoren wieder abschalten (vorher gesperrt). (5) Der Zugriff von außen
    „Variante B“ (AUFTRAG_WEBUI.md 4.7) setzte Zwei-Faktor für alle bei der Anmeldung voraus; sie war nie umgesetzt und
    ist ohne neuen Auftrag nicht zulässig.
    **Das senkt die Schutzstufe:** Wer das Passwort eines Administrators kennt, kann ohne zweiten Faktor die Einrichtung
    ändern, Claude-Befehle freigeben und das Spiel starten. Die Heimnetz-Schranke (Entscheidung 6: Caddy und API
    lassen nur private Netze zu, `SM_ERLAUBTE_NETZE`) trägt diese Schutzstufe weiter; die Web-UI darf deshalb nicht ins
    Internet gestellt werden. Tests: Anmeldung ohne Code (auch mit vorhandenem TOTP), Administrator ohne Zwei-Faktor,
    Anlegen mit gültigem, falschem und fehlendem Code, andere Admin-Aktionen ohne Code mit Passwortprüfung, E2E.


41. Keine Zeitfenster und Datumsmechanik mehr (Umbau v2, Stufe B, Punkt 2). **Umgesetzt.** Als „Zeitfenster“ wurde
    ausgelegt: alles, was einen Lauf oder eine Order wegen Datum, Wochentag, Uhrzeit oder Startdatum verhindert oder
    einschränkt. Entfernt sind: die Startdatum-Sperre in `buchen.py` (`portfolio_pruefen`), die Vorprüfung und die
    Hinweise im Startdialog (`GET /api/laeufe/vorpruefung`, `hinweise()`), die Prompt-Passage „nur recherchieren“, das
    Überspringen geplanter Trading-Termine (kein Handelstag, Startdatum in der Zukunft, Richtlinien offen), das
    30-Minuten-Fenster, die Pflichtschritte „Spiel starten“ und „Anlagerichtlinien“ der Einrichtung und der Abschnitt
    „Modus bestimmen“ in CLAUDE.md (Entwicklung und Trading trennt nur noch der Auftrag). **Bleibt:** Kein Backdating
    (regeln.md 1.3), Handelszeiten als Ausführungsbedingung (außerhalb vorgemerkt, nächste Gelegenheit), Kursalter,
    Review-Rhythmus nach Spielzeit, die Wochentage und Uhrzeiten des Zeitplans selbst (der Zeitplan ist eine Einstellung
    der Auftraggeber, keine Sperre). **Auslegungen:** (1) Ein geplanter Lauf wird nie übersprungen. Ist eine Session
    aktiv (Sperre), wird er sichtbar zurückgestellt (`zeitplan_offen`, Status „wartet“ im Plan, Cockpit und Laufseite)
    und alle fünf Minuten erneut versucht. (2) Nachholfenster: Fiel der Worker aus, wird ein verpasster Termin bis
    120 Minuten danach nachgeholt; ein wartender Termin gibt nach 24 Stunden mit sichtbarem Vermerk auf (sonst
    stauen sich Läufe beim nächsten Termin). Beides sind Betriebsgrenzen, keine Handelssperren. (3) Ist das Spiel beim
    Start eines Trading-Laufs nicht initialisiert, startet der Lauf es selbst: Startdatum heute, Standard-
    Anlagerichtlinien, Audit-Eintrag, Auslöser `lauf` in `spiel.json` (`init.py --freigabe <auftraggeber> --ausloeser
    lauf`). Die Freigabe nach AP12 erteilt damit der Auftraggeber, der den Lauf startet bzw. den Zeitplan eingerichtet
    hat. (4) Nachbuchung und Standard-Richtlinien warten nicht mehr auf das Startdatum. **Ersetzt** die Regeln der
    Entscheidung 33 zu Vorprüfung, Überspringen und Startdatum. Tests: Werkzeuge (Order am Starttag und davor
    Startdatum nicht gesetzt), Backend (wartender Lauf, Nachholen, Aufgeben nach 24 h, Selbststart, Prompt), Oberfläche
    und E2E.
42. Handeln hat Vorrang vor Cash (Umbau v2, Stufe B, Punkt 3; Auftrag der Auftraggeber vom 2026-10-09). **Umgesetzt.**
    CLAUDE.md (Rolle, Schritt 7 und 9, Session-Vorlage, Haltung), `config/richtlinien/*.md` (Standard-Richtlinie
    Version 2), regeln.md 10 und 12 (v1.4) und die Prompts verlangen: Handeln ist der Normalfall, Cash die Ausnahme,
    Nichthandeln ist nicht neutral (Cash bringt 2 %). Verzicht auf eine Order nur, wenn (a) keine Order alle harten
    Limits einhält und einen positiven Szenario-Erwartungswert nach Kosten hat, (b) Drawdown-Stufe 2 oder Portfolio-
    Stopp gilt oder (c) kein verlässlicher Kurs vorliegt. Beweislast je Session und Portfolio: eine Order (Journal-ID)
    oder die belegte Ausnahme mit Zahlen (Verlust bis Stop gegen Limit, Erwartungswert nach Kosten, geprüfte
    Kandidaten) in der neuen Pflichtzeile „Handlung oder Ausnahme“; zusätzlich die Zeile „Cashquote“ (Zielwert: die
    Mindest-Cashquote des Profils). Kosten bleiben Teil der Abwägung (kein Churning). **Ersetzt** Entscheidung 39,
    Auslegung 2 (Nichtstun gültig, Kapitalerhalt vor Rendite); Vorgaben der Auftraggeber bleiben nachrangig gegenüber den
    Regeln, die Platzhaltertexte im Editor sind angepasst. **Prüfung:** `pruefe.py` und das Cockpit warnen (nie Fehler)
    bei einer durchschnittlichen Cashquote über Mindestquote plus 25 Punkten in den letzten fünf NAV-Tagen (Cockpit und
    `pruefe.py`, nur aktive Portfolios) und bei Sessions ohne Order und ohne belegte Ausnahme; die Session-Warnung gilt
    erst für Sessions ab `handeln.pflicht_ab` (2026-10-09) in `config/projekt.json`, damit die Historie unverändert
    bleibt. Schwellen stehen in `config/projekt.json` (`handeln`). **Migration:** Der Worker aktualisiert unveränderte ältere Standard-Richtlinien
    selbst (Version im Kopf; Historie-Zeile „Standard-Update“); angepasste Richtlinien bleiben stehen und werden im
    Befund genannt. **Auslegungen:** (1) „Verlässlicher Kurs“ heißt: Kurs aus `tools/kurse.py`, nicht älter als 30
    Minuten während der Handelszeit, protokolliert; fehlt er, ist (c) erfüllt. (2) Für die Pflichtzeile gilt nur die Order bzw. Ausnahme
    der jeweiligen Session. (3) Die harten Limits und Kosten bleiben unverändert.
    Grenze: Eine Anweisung an ein Sprachmodell ist keine Prüfung; die Warnungen machen Abweichungen sichtbar.

43. Ausführung ohne Claude-Lauf (Umbau v2, Stufe C, Punkt 5). **Umgesetzt.** Neues Werkzeug `tools/ausfuehrung.py`
    (kein Sprachmodell, kein Token): Der Hintergrunddienst (`worker.py`, Schritt `ausfuehren`) ruft `tick` bei offenem
    Markt alle 5 Minuten auf, außerdem eine Minute nach der Öffnung und zwei Minuten vor dem Schluss jeder Börse
    (`ausfuehrung.faellig`/`ereignisse`; Zeitzonen, Sommerzeit-Unterschiede zwischen Europa und USA, Feiertage und
    Frühschlüsse kommen aus `config/universum.json`, `kurse.boersen_fenster`). Nach fehlendem Kurs, belegter Sperre oder
    Fehler wiederholt der Dienst nach einer Minute. Der Tick führt aus: vorgemerkte Market-Orders, Limit-Orders (Kurs auf
    oder besser als das Limit) und je Position Knock-out vor Stop vor Kursziel, jeweils zum protokollierten Kurs
    (`kurse.aktuell`, Kursalter höchstens 30 Minuten, ohne Kurs keine Ausführung und neuer Versuch). Die Order gilt erst ab
    ihrer Erfassung (die Quellzeit des Kurses muss nach der Erfassung liegen); die Limits werden vor jeder Kaufausführung
    mit `limits.pruefe_kauf` erneut geprüft (Verstoß: Order verfällt mit Vermerk, `verfall`-Zeile). Jede Buchung trägt die
    ursprüngliche Journal-ID und in der Bemerkung `automatisch (Auslöser: Eröffnung|Markt|Limit|Stop|Kursziel|Knock-out)`
    (Spalte `bemerkung`, damit sich die CSV-Köpfe bestehender Instanzen nicht ändern); Trade-Akte, Buchungstabelle und eine
    Cockpit-Karte „Automatisch ausgeführt“ zeigen sie, `pruefe.py` prüft sie (bekannter Auslöser, Kursquelle `kurse`,
    innerhalb der Handelszeit des Basiswerts, keine zweite Endbuchung je Order, keine Ausführung vor der Vormerkung).
    **Buchungssperre:** `gemeinsam.buchungssperre` (flock auf `.buchungssperre`, wiedereintrittsfähig, Wartezeit mit
    Abbruch) umfasst den ganzen Vorgang Laden–Prüfen–Schreiben. `buchen.py` (kaufen, verkaufen, aendern, storno),
    `bewertung.nachbuchen_profil` und die Ausführung nehmen sie; das Portfolio wird erst in der Sperre geladen. Sie ist von
    `session.lock` unabhängig: Eine laufende Claude-Session und die Ausführung buchen nacheinander, nie gleichzeitig;
    Kurse für die Ausführung werden vor der Sperre geholt, damit sie kurz bleibt. Eine Order hat genau einen Endzustand
    (Ausführung, Verfall, Storno steht in `trades/`); eine Order mit schon vorhandener Endbuchung führt der Tick nicht
    erneut aus (Hinweis im Bericht, `pruefe.py` meldet die Inkonsistenz). **Nachbuchung bleibt der Abgleich:** Sie
    bucht nachts weiter bis gestern, holt Eröffnungskurse und Zwischenberührungen (Tageshoch/-tief, ungünstigere Annahme)
    nach und meldet automatische Kurse außerhalb der Tageskerze (`bewertung.abgleich_automatisch`, nur Hinweis, nie eine
    Änderung vorhandener Buchungen). **Systemstatus** hat die Zeile „Ausführung“ (letzter Durchlauf, Warteschlange offener
    Orders, Rückstand nicht ausgeführter Market-Orders bei offenem Markt, Fehler, Hinweise; rot, wenn bei offenem Markt
    seit 15 Minuten kein Durchlauf stattfand). Protokoll: `data/ausfuehrung/JJJJ-MM-TT.jsonl` (nur Durchläufe mit Buchung,
    Fehler oder Problem; Nur-Anhängen-Prüfung) und der Log des Dienstes. Der Dienst committet Ausführungen lokal
    (`session: automatische Ausführung …`), solange keine Session aktiv ist; sonst übernimmt der Commit der Session.
    **Auslegungen:** (1) Eine vorgemerkte Market-Order wird zum ersten protokollierten Kurs nach der Eröffnung
    ausgeführt, sofern dessen Quellzeit höchstens 30 Minuten nach der Eröffnung liegt; sonst überlässt der Tick sie der
    Nachbuchung (offizieller Eröffnungskurs). Das ist eine Näherung an den Eröffnungskurs (Xetra-Kurse sind bei yfinance
    etwa 15 Minuten verzögert, gebucht wird nur zu protokollierten Kursen mit Quellzeit nach der Eröffnung). (2) Stops,
    Kursziele und Limits lösen auf dem protokollierten Kurs aus, nicht auf Zwischenwerten: Ein Stop wird zum Kurs des
    Ticks ausgeführt (nie besser als der Stop), Kursziel und Limit zum Kurs des Ticks (nie schlechter als vorgegeben); was
    zwischen zwei Ticks geschieht, holt die Nachbuchung mit der ungünstigeren Annahme nach. (3) Ein geänderter Stop wirkt für
    die laufende Ausführung sofort (Kurse nach der Änderung), für die nächtliche Kerzenprüfung weiter ab dem nächsten
    Handelstag (Entscheidung zu `buchen.py aendern`, unverändert). (4) Solange Tage der Nachbuchung ausstehen (Worker
    ausgefallen), führt der Dienst nicht aus, damit die Reihenfolge der Tage stimmt; der Systemstatus nennt es. (5) Stop und
    Kursziel gehören zu einer Position und schließen sich aus: Das ist die OCO-Wirkung. **Nicht umgesetzt (Vorschlag an
    die Auftraggeber):** Trailing-Stop, weil der Stop-Verlauf (`stop_historie`) und die Kerzenprüfung der Nachbuchung ihn
    nicht abbilden; als Vorschlag: Stufe `trailing` mit festem Abstand, vom Tick nachgezogen und je Anpassung als `aenderung`
    gebucht. **Grenzen:** yfinance liefert keine Tickdaten; die Ausführung ist so genau wie der 5-Minuten-Takt der
    Kursquelle, und ein Ausfall des Dienstes bei offenem Markt wird erst von der nächsten Nachbuchung ausgeglichen.
    Tests: Sonntagabend erfasst, Montag zur Eröffnung ohne Lauf ausgeführt (Kauf und Verkauf), verpasstes
    Eröffnungsfenster, fehlender und veralteter Kurs, Stop, Kursziel, Knock-out, Limit, Limit-Verstoß, Rückstand der
    Nachbuchung, gleichzeitige Ticks und Claude-Session ohne Doppelbuchung (Threads), Sperre prozessübergreifend, Uhr
    (Sommerzeit-Unterschied, Frühschluss, Feiertag, Takt), Prüfungen, Abgleich, Worker-Schritt und Systemstatus.

44. Profilliste aus der Konfiguration und Migration bestehender Instanzen (Umbau v2, Stufe D, Punkte 4 und 6).
    **Umgesetzt.** Die Profile stehen nur noch in `config/profile.json` (Reihenfolge = Anzeige); `gemeinsam.profile()`
    ersetzt die feste Liste `PROFILE` (das Kürzel `g.PROFILE` bleibt als Alias), alle Werkzeuge (`init`, `limits`, `buchen`,
    `bewertung`, `pruefe`, `richtlinien`, Benchmark, Ranking), das Backend (Routen, Vorgaben, Prompts) und die Oberfläche
    lesen sie von dort bzw. aus den Daten; ein Test der Oberfläche prüft, dass Namen und Farben alle Profile der
    Konfiguration abdecken. regeln.md 7 hat die Spalte Overnight, `pruefe.py` gleicht Tabelle und `config/profile.json`
    weiter ab (jetzt vier Spalten). **Migration:** Der Hintergrunddienst ergänzt fehlende Profile selbst (`worker.py`
    `profile_ergaenzen`, `tools/init.py --profile-ergaenzen`): Sicherung im App-Verzeichnis (`/data-app/sicherungen`,
    die letzten drei), lokaler Commit des Ist-Zustands, dann Portfolio, Trades, NAV, Standard-Anlagerichtlinie und die
    Hypothese H-OVERNIGHT-1 in lessons.md, danach ein Commit. Idempotent (zweiter Lauf tut nichts), nie während einer
    Session, nie rückwirkend (**Startdatum = Tag der Ergänzung, 1.000 EUR**); die drei bestehenden Portfolios, ihre
    Trades, Journal und Reviews bleiben Byte für Byte unverändert (Test auf einer Kopie eines Datenverzeichnisses mit
    Historie). Der Start eines neuen Spiels legt alle vier Profile gleich an. Das Redeploy in Portainer braucht keinen
    manuellen Eingriff. **Unterschiedliche Startdaten:** Die Benchmark rechnet je Portfolio ab dessen erstem
    Schlusskurs (`benchmark.csv` bekommt die Spalte `overnight`, Werte vor dem eigenen Start bleiben leer);
    Rendite, Drawdown und Sharpe zählen je Portfolio ab dem eigenen Start, `ranking.md` zeigt das Startdatum und nennt
    den Grund, warum Renditen dann an der eigenen Benchmark zu messen sind; Reviews bleiben nach Spielzeit
    (frühestes Startdatum). Session-Einträge werden für ein Profil erst ab dessen Startdatum vollständig verlangt (keine
    Rückwirkung auf alte Sessions). **Technisches:** `.buchungssperre` steht in der `.gitignore` der Datenverzeichnisse
    (bestehende bekommen die Zeile beim nächsten Commit), im Export ausgeschlossen. Unbekannte Profile liefern jetzt 404
    statt 422. Tests: Migration auf einer Kopie (Werkzeuge und Dienst), Idempotenz, Session-Sperre, Benchmark und Ranking
    mit unterschiedlichen Startdaten, `pruefe.py --historie` danach.
45. Viertes Portfolio „Overnight“ (Umbau v2, Stufe D, Punkt 4). **Umgesetzt**, mit einer **offenen Entscheidung** (unten).
    *Mechanik:* Daueranweisung (`tools/daueranweisung.py`, regeln.md 6): Claude setzt Instrumente (ETF, Aktie, Knock-out
    mit Hebel bis 3, höchstens drei), Gewichte, Einsatzanteil (Standard 97 %), Stop-Abstand (Standard 3 %), Gültigkeit
    (höchstens 90 Tage), Aussetzkriterien (Drawdown-Stufe ab 1, Verlustnächte in Folge, Portfoliowert unter x) mit
    Journal-ID; das Werkzeug rechnet vorher alle Limits mit den heutigen Kursen (Trockenlauf `--nur-pruefen`, sonst
    abgelehnt). Der Hintergrunddienst kauft nach dem Handelsschluss zum ersten protokollierten Kurs, dessen Quellzeit nach
    dem Schluss liegt (Fenster: Schluss plus 5 bis 90 Minuten), und verkauft die Positionen der Anweisung am nächsten
    Handelstag zum ersten Kurs nach der Eröffnung (höchstens 30 Minuten danach), sonst die Nachbuchung zum Eröffnungskurs
    der Tageskerze. Wochenenden, Feiertage und Frühschlüsse folgen dem Börsenkalender (Test über Wochenende und
    Weihnachten). Ohne gültige Anweisung geschieht nichts; eine Anweisung gilt erst ab ihrer Erfassung (wer sie nach
    dem Schluss erfasst, kauft erst am nächsten Tag). Nächte werden aus den Trade-Zeilen abgerechnet (Ergebnis inklusive
    Gebühren, Verlustserie), jeder Verkaufsweg zählt gleich. Protokoll `data/daueranweisung/overnight.jsonl` (nur
    anhängen); `pruefe.py` prüft: Kauf nur mit Anweisung im Protokoll, nach Erfassung, bis zur Gültigkeit, nicht
    während Aussetzung, Journal-ID gleich, liegengebliebene Positionen. *Preisquelle (konservativ, dokumentiert):*
    protokollierte Kurse aus `tools/kurse.py` (yfinance verzögert Xetra um etwa 15 Minuten): Der Kauf wartet, bis die
    Quelle einen Kurs nach dem Schluss liefert (nie vor dem Schluss), der Verkauf, bis sie einen nach der Eröffnung
    liefert (nie davor); die Nachbuchung meldet Kurse außerhalb der Tageskerze. Positionen, die nach dem Schluss gekauft
    wurden, zählen für die Tageskerze des Kauftags nicht (Stop und Barriere gelten ab der nächsten Kerze). *Limits
    Overnight* (neu, regeln.md 7, `config/profile.json`): Zertifikate-Anteil 30 %, Hebel 3x, Exposure 1,5x,
    **Einzelposition 100 %** (jede weitere Position kostet zwei Gebühren je Nacht), Mindest-Cashquote 2 %, Risiko je Trade
    4 % (verlangt einen Stop), Drawdown-Bremse -10 % / -20 %, Benchmark 100 % MSCI World (EUNL.DE). Die Limits und Kosten
    der drei bestehenden Profile sind unverändert. *Kostenmachbarkeit (gerechnet, `tools/overnight.py kosten`):* Bei
    1.000 EUR kostet eine Nacht mit einer ETF-Position (970 EUR) 2,97 EUR = **0,31 %** des Einsatzes (2 EUR Gebühr, 0,10 %
    Spread), mit zwei Positionen 4,97 EUR = **0,51 %**, mit einem Knock-out (Hebel 3, 300 EUR) 2,67 EUR = 0,89 % des
    Einsatzes, auf den Basiswert umgerechnet wieder **0,30 %**: Die festen Gebühren fressen den Hebel, Hebel bessert die
    Machbarkeit nicht. Der Basiswert müsste im Schnitt mindestens so viel zwischen Schluss und Eröffnung steigen. Die
    Erwartung ist, dass breite Indizes das nicht tun (Größenordnung wenige hundertstel Prozent je Nacht, eine
    Größenordnung darunter); das ist als **Hypothese H-OVERNIGHT-1** in lessons.md und in der Standard-Richtlinie
    festgehalten und **hier nicht mit Marktdaten geprüft**: Die Entwicklungsumgebung hatte keinen Zugang zu den Kursquellen.
    Das Rückblick-Werkzeug (`tools/overnight.py analyse`, Rohkurse eines Jahres aus den Listen von
    `config/beobachtung.json`, 70 % Training / 30 % Test, Kosten des Spiels, Kennzahlen: Mittel, Median, Trefferquote,
    5-%-Quantil, Wochenende gegen Wochentag, Streuung, Korrelation Xetra gegen US-Sitzung) läuft wöchentlich im
    Hintergrunddienst (ab 23:30 Uhr) und liefert die Zahlen mit echten Daten; Ergebnis über `overnight.py ergebnis`.
    Getestet ist es mit synthetischen Reihen (kein Netz). Rohkurse enthalten Dividendenabschläge (Aktien wirken zu
    schlecht, ETFs nicht), ein Jahr ist kurz, bei rund 600 Werten gibt es Zufallstreffer: ein Kandidat ist eine
    Hypothese. Die Demo (Zufallskurse ohne Vorteil) zeigt den Kostenverlust: 38 Nächte, Ergebnis rund -92 EUR (-0,24 %
    je Nacht). *Beste Variante im Rahmen der Kosten:* eine breite ETF-Position, Einsatz bis zur Mindest-Cashquote, wenn
    die Messung es stützt nur lange Nächte (`--nur-lange-naechte`: vor Wochenende und Feiertag), Aussetzen bei
    Drawdown-Stufe 1. **Offene Entscheidung für die Auftraggeber:** Ist das Profil im Kostenmodell strukturell nicht
    tragfähig (erwarteter Verlust von rund 0,3 % je Nacht gegenüber einem Ertrag von wenigen hundertstel Prozent), hat das
    Experiment drei Wege: (1) behalten und messen (Ausnahme (a) in jeder Session belegen, kein Handel bis die
    Messung einen positiven Erwartungswert zeigt; kostet nichts außer Aufmerksamkeit), (2) die Gebühr für dieses
    Profil senken (kein Entscheid dieses Auftrags: Kosten werden nie still zugunsten eines Profils gesenkt) oder (3) das
    Profil nach der ersten Messung schließen. Umgesetzt ist (1). *Oberfläche:* Profilfarbe `#F2AAE0` (dunkel) bzw.
    `#8C1C67` (hell) mit Test auf Kontrast (mindestens 2,8) und paarweise Unterscheidbarkeit bei Rot-Grün- und
    Blau-Gelb-Schwäche (CIELAB-Abstand mindestens 15, Simulation nach Machado); Reiter „Daueranweisung“ im Portfolio,
    Cockpit-Karten in vier Spalten, App-Icon `assets/icons/vier-profile.svg` (Favicon), Vorgaben-Editor mit Overnight.
    Gewinne und Verluste werden wie bisher zusätzlich über Vorzeichen und Symbol gezeigt. *Auslegungen:* (1) Die
    Daueranweisung ist generisch (Zyklus in `config/profile.json`), derzeit nur für Overnight. (2) Positionen mit dem
    Kennzeichen der Anweisung werden immer zur nächsten Eröffnung verkauft, auch wenn die Anweisung inzwischen
    beendet, ausgesetzt oder abgelaufen ist (`beenden --positionen-behalten` nimmt das Kennzeichen weg). (3) Verpasst der
    Dienst den Kauf zum Schluss (Ausfall), wird er nicht nachgeholt; der Verkauf wird nachgeholt. (4) Die Cash-Warnung in
    `pruefe.py` trifft Overnight ohne Anweisung dauerhaft, weil Cash dort der Zustand ohne Anweisung ist; sie ist nur eine
    Warnung, der Session-Eintrag belegt die Ausnahme.

## Auslegungsfragen Phase 1 (entschieden am 2026-10-07)

Wo regeln.md nicht eindeutig ist, wurde nach CLAUDE.md die konservativere
Auslegung gewählt und im Code kommentiert. Am 2026-10-07 hat Claude im Auftrag
alle Fragen entschieden: fachlich sinnvoll, mit dem größten Spielraum, den
regeln.md erlaubt, ohne Limits, Kosten oder Risikogrenzen zu lockern. Ergebnis:
Alle bisherigen Auslegungen bleiben, weil jede Alternative entweder Backdating
(regeln.md 1.3), eine günstigere Annahme bei unklaren Daten (1.4) oder geringere
Kosten (Abschnitte 4 und 5) bedeuten würde. Je Frage die Begründung:

1. Faktor-Kosten (0,02/365) je Kalendertag, nicht je Handelstag
   (Wochenende: dreifach). Knock-out-Aufzinsung ebenfalls an jedem
   Kalendertagsende, auch am Kauftag.
    Entschieden: bestätigt. regeln.md 4 rechnet die Aufzinsung ausdrücklich je Kalendertag; für den Faktor-Abschlag wäre „je Handelstag“ eine Kostenlockerung.
2. Kursziel am Kauftag wird nicht ausgelöst (das Tageshoch kann vor dem
   Kauf gelegen haben); der Stop zählt am Kauftag gegen die ganze
   Tagesspanne (regeln.md 4).
    Entschieden: bestätigt. Ein Kursziel aus Kursen vor dem Kauf auszulösen wäre Backdating; für Stop und Barriere schreibt regeln.md 4 die ganze Tagesspanne vor.
3. Änderungen von Stop/Kursziel wirken ab der nächsten Tageskerze.
    Entschieden: bestätigt. Tagesdaten zeigen nicht, wann ein Kurs im Tag lag; sofortige Wirkung könnte Kurse vor der Änderung nutzen.
4. Vorgemerkte Orders (Market und Limit) nutzen nur Tageskerzen, die nach
   ihrer Erfassung beginnen. Eine während der Handelszeit erfasste, nicht
   sofort ausführbare Limit-Order gilt also erst ab dem nächsten
   Handelstag. Limit-Orders gelten bis zum Storno.
    Entschieden: bestätigt. Folgt aus „kein Backdating“; Limits bis zum Storno ersparen tägliche Neuerfassung und kosten nichts.
5. Gold/Brent: Die Tageskerze der Futures beginnt am Vorabend; als Beginn
   gilt konservativ 23:00 des Vortags.
    Entschieden: bestätigt. Die Futures-Kerze beginnt real am Vorabend; 23:00 ist der ungünstigere der beiden möglichen Zeitpunkte.
6. Devisenkurs: Ausführung zur Eröffnung mit EURUSD-Eröffnung, Ereignisse
   im Tagesverlauf und Bewertung mit EURUSD-Schluss desselben Tages.
    Entschieden: bestätigt. Jeder Buchungszeitpunkt hat damit einen eindeutigen, protokollierten Devisenkurs aus derselben Tageskerze.
7. Nachgebucht werden nur abgeschlossene Tage (bis gestern). Ereignisse von
   heute (z. B. Ausführung einer Abendorder zur heutigen Eröffnung) bucht
   die nächste Session.
    Entschieden: bestätigt. Die heutige Kerze ist unvollständig; sie zu buchen hieße mit Daten zu rechnen, die sich noch ändern.
8. Ein aktueller Kurs gilt bei offenem Markt höchstens 30 Minuten
   (config/projekt.json); älter: kein Handel.
    Entschieden: bestätigt. Mit einem Echtzeit-Anbieter (Einrichtung → Kursdaten) ist die Grenze erreichbar; mehr Spielraum widerspräche „ohne verlässlichen Kurs kein Handel“.
9. Mindestorder (100 EUR) gilt auch für Teilverkäufe; Komplettverkauf
   immer erlaubt.
    Entschieden: bestätigt. Die Mindestorder gilt für jede Order; der Komplettverkauf bleibt immer möglich, Risikoabbau ist also nie blockiert.
10. Einzelposition: gleiche Instrumente werden zusammengezählt (Aktie je
    Ticker, Zertifikate je Typ, Richtung und Basiswert). Alle Limits werden
    bei jedem Kauf nach der Order geprüft; ein bereits überschrittenes
    Limit blockiert damit jeden Kauf, der es nicht verbessert.
    Entschieden: bestätigt. Zusammenzählen verhindert Umgehung durch Stückelung; Käufe, die ein überschrittenes Limit verbessern, bleiben möglich.
11. Unbekannte Marktkapitalisierung eines Aktien-Basiswerts gilt als zu
    klein.
    Entschieden: bestätigt. Fehlende Daten gelten nach regeln.md 1.4 als ungünstig.
12. Dividende nur für Positionen, die vor Beginn des Ex-Tags eröffnet
    wurden und am Ex-Tag zum Schluss noch bestehen (Verkauf am Ex-Tag
    verliert die Dividende).
    Entschieden: bestätigt. Entspricht der realen Ex-Tag-Logik.
13. Splits werden vor allen Ereignissen des Split-Tags angewendet (die
    Tageskerze ist bereits angepasst), nicht erst zum Tagesschluss.
    Entschieden: bestätigt. Die Tageskerze ist am Split-Tag bereits angepasst; sonst würden Stops fälschlich auslösen.
14. Portfolio-Stopp: Prüfung zum Tagesschluss; Glattstellung aller
    Positionen zum Schlusskurs inklusive Spread und Gebühr.
    Entschieden: bestätigt. regeln.md 7 nennt keine Prüfung im Tagesverlauf; Spread und Gebühr fallen bei jedem Verkauf an (Abschnitt 5).
15. Drawdown: Endet Stufe 2 (nach Review, Drawdown unter der Hälfte der
    Stufe-2-Schwelle), gilt Stufe 1 weiter, solange der Drawdown nicht
    unter der Hälfte der Stufe-1-Schwelle liegt.
    Entschieden: bestätigt. Folgt aus dem Wortlaut von Abschnitt 7 (jede Stufe endet unter der Hälfte ihrer eigenen Schwelle).
16. Je Kauf und Verkauf ein eigener Journal-Eintrag; der Eintrag muss das
    Portfolio nennen und in der Journal-Datei der Person stehen, die die
    Session-Sperre hält. Stop und Kursziel sind beim Kauf Pflichtangaben
    (`keiner` ausdrücklich möglich).
    Entschieden: bestätigt. Je Order ein Eintrag hält die Prüfspur eindeutig; „keiner“ als Stop bleibt erlaubt (Risiko dann mit 20 % bzw. 100 % angesetzt).
17. Kauf-Limit auf den Basiswert: Long bei Kurs <= Limit, Short bei
    Kurs >= Limit.
    Entschieden: bestätigt. Übliche Limit-Semantik: Long kauft bei fallendem, Short bei steigendem Basiswert.

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
  echte Daten geprüft am 2026-10-07 in der Testsession (AP12) im Betrieb:
  NVDA vor dem Split 1.208,88 am 2024-06-07, Split 10:1 am 2024-06-10,
  Dividende 0,01 am 2024-06-11 stimmen; Xetra-Kurse über yfinance waren etwa
  15 Minuten verzögert (Grenze 30 Minuten).

## Auslegungsfragen Phase 2: Frage 20 (entschieden)

20. Entschieden am 2026-10-07 (Entscheidung 34): Es bleiben immer alle drei Profile; die Profilauswahl
    (Entscheidung 13) wird nicht umgesetzt. Der ursprüngliche Formulierungsvorschlag entfällt, regeln.md
    bleibt bei drei Portfolios.
