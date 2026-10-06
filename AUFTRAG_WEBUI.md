# Entwicklungsauftrag Web-UI (Entwurf v0.1)

Status: **Entwurf zur Abstimmung**. Noch kein Code. Offene Entscheidungen
stehen in Abschnitt 13; erst nach deren Klärung durch Patrick und Philip
wird dieser Auftrag umgesetzt.

## 1. Ziel

Eine moderne, lokal per Docker betriebene Weboberfläche für das
Börsenexperiment:

- Alles aus dem Repository einsehbar: Portfolios, Trades, Journal,
  Reviews, Strategien, Lessons, Ranking, Prüfergebnisse, Git-Historie.
- Alle Punkte aus AUFTRAG_PHASE1.md einsehbar und, soweit regelkonform,
  konfigurierbar (Arbeitspakete, Konfiguration, Auslegungsfragen,
  Initialisierung, Freigabe).
- Claude-Sessions aus der Oberfläche starten, live verfolgen und
  nachlesen. Jeder Benutzer verbindet seinen eigenen Claude-Zugang.
- Mehrbenutzerbetrieb: ein initialer Administrator legt Benutzer an;
  Arbeitsbereiche lassen sich mit Rechten (Lesen/Bearbeiten) teilen.
- Das Reasoning hinter jedem Trade und jeder Abwägung (auch "nichts
  tun") ist übersichtlich nachvollziehbar.

## 2. Leitplanken (gelten zusätzlich zu CLAUDE.md und regeln.md)

1. **Die Web-UI rechnet nicht.** Kurse, Buchungen, Limits, Kennzahlen
   kommen weiterhin ausschließlich aus `tools/`. Die UI ruft die
   Werkzeuge auf und zeigt deren Ergebnisse an; sie implementiert keine
   Spiellogik nach.
2. **Die Web-UI bucht nicht.** Es gibt keine manuelle Ordermaske.
   Orders entstehen nur durch Claude über `tools/buchen.py`. Benutzer
   können Ideen einreichen, die Claude kritisch prüft (CLAUDE.md, Haltung).
3. **Keine Handbearbeitung** von `portfolios/`, `trades/`, `data/`,
   `journal/` (nur Anhängen durch Claude) – auch nicht über die UI.
4. **Git bleibt die Prüfspur.** Jeder Arbeitsbereich ist ein eigenes
   Git-Repository; `pruefe.py` und die Nur-Anhängen-Prüfung funktionieren
   unverändert.
5. **Regeländerungen nur gemeinsam** (regeln.md Kopf, Abschnitt 12):
   Änderungen an regeln.md und `config/` laufen über einen
   Änderungsantrag mit Zustimmung aller Auftraggeber des Arbeitsbereichs,
   mit Datum, ohne Rückwirkung.
6. **Kein Backdating:** Zeitstempel setzt ausschließlich der Server.
7. Die bestehenden Werkzeuge und Tests in `tools/` und `tests/` bleiben
   unberührt. Die Phase-1-Festlegung "nur pandas, yfinance, pytest" gilt
   weiter für `tools/`; die Web-UI hat eigene, gesperrte Abhängigkeiten
   unter `webui/` (Begründung wird in STATUS.md vermerkt).

## 3. Toolstack

| Schicht | Wahl | Begründung |
| --- | --- | --- |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4, shadcn/ui (Radix), lucide-Icons | modernes, zugängliches Designsystem, Dark/Light-Theme |
| Routing/Daten | TanStack Router, TanStack Query, react-hook-form + zod | typsicher, Caching, Formularvalidierung |
| Diagramme | Recharts (KPIs, NAV, Drawdown), TradingView lightweight-charts (Kursverlauf mit Einstieg/Stop/Ziel) | schön und performant |
| Markdown | react-markdown + rehype-sanitize (kein Roh-HTML) | Journal, Reviews, Regeln sicher rendern |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic | gleiche Sprache wie `tools/`, starke Validierung |
| Jobs | Arq (Redis) als Worker für Werkzeug- und Claude-Läufe | lange Läufe außerhalb des Request-Zyklus |
| Datenbank | PostgreSQL 16 mit Row Level Security | Mandantentrennung in der Datenbank |
| Cache/Limits | Redis 7 | Rate-Limiting, Job-Queue, Live-Events (Pub/Sub) |
| Claude | offizielle Claude Code CLI (headless, `claude -p --output-format stream-json`), Version gepinnt | gleiche Werkzeuge und Arbeitsweise wie heute (CLAUDE.md, Hooks, Rechte) |
| Reverse Proxy | Caddy 2 (TLS `internal`, Security-Header, statische Auslieferung der SPA) | HTTPS auch lokal, damit `Secure`-Cookies greifen |
| Paketmanager | uv (Python, Lockfile mit Hashes), pnpm (Frontend, Lockfile) | reproduzierbar, prüfbar |

## 4. Architektur

### 4.1 Container (docker-compose.yml)

| Dienst | Aufgabe | Netz | Besonderheiten |
| --- | --- | --- | --- |
| `proxy` | Caddy, liefert SPA aus, leitet `/api` weiter | `edge`, `app` | einziger veröffentlichter Port, Standard `127.0.0.1:8443` |
| `api` | FastAPI | `app`, `data` | nicht-root, read-only Root-FS, keine Docker-Socket-Rechte |
| `worker` | führt `tools/` und Claude-Läufe aus | `data`, `egress` | enthält Python, git, Node + Claude Code CLI; Internet für Anthropic, Yahoo, Web-Suche |
| `db` | PostgreSQL | `data` (internal) | kein veröffentlichter Port |
| `redis` | Redis mit Passwort | `data` (internal) | kein veröffentlichter Port |

Volumes: `pgdata`, `workspaces` (Git-Repos), `backups`. Geheimnisse
(DB-Passwörter, Schlüssel für Token-Verschlüsselung, Session-Secret)
ausschließlich als Docker Secrets; `.env.example` ohne Werte im Repo.
Alle Container: `cap_drop: ALL`, `no-new-privileges`, Ressourcenlimits,
Healthchecks, Basis-Images per Digest gepinnt.

### 4.2 Arbeitsbereich = eigene Spielinstanz

- Ein Arbeitsbereich ist ein Git-Repository unter
  `/data/workspaces/<uuid>/repo`, erzeugt aus einer Vorlage (Spielteil
  dieses Repositorys: CLAUDE.md, regeln.md, config/, tools/, tests/ …).
- Als `origin` dient ein lokales Bare-Repository im selben Volume, damit
  `session.py start` (commit + push) unverändert funktioniert. Optional:
  Spiegelung auf ein GitHub-Repository (Deploy-Key verschlüsselt
  gespeichert), damit die bestehende GitHub Action weiterläuft.
- Das bestehende Spiel kann als Arbeitsbereich importiert werden
  (Klon mit vollständiger Historie).
- Werkzeug-Updates aus der Vorlage nur als expliziter, sichtbarer
  Merge-Vorgang mit Zustimmung (keine stillen Änderungen an `tools/`).
- Pro Arbeitsbereich höchstens ein laufender Claude-Lauf; zusätzlich
  gilt die bestehende Sperre `session.lock`.

### 4.3 Datenhaltung

- **Quelle der Wahrheit für Spieldaten bleibt das Git-Repository.** Die
  API liest Dateien über einen Lesedienst (Parser für JSON, CSV, JSONL,
  Markdown) und cacht Ergebnisse je Commit-Hash.
- **PostgreSQL** hält nur Metadaten: Benutzer, Sitzungen, Arbeitsbereiche,
  Mitgliedschaften, Claude-Zugänge (verschlüsselt), Läufe und deren
  Ereignisse, Änderungsanträge, Ideen, Audit-Log.

Tabellen (alle mandantenbezogenen mit RLS):

    users(id, email, anzeigename, passwort_hash, ist_admin, aktiv,
          totp_secret_enc, passwortwechsel_noetig, fehlversuche,
          gesperrt_bis, erstellt)
    auth_sessions(id_hash, user_id, erstellt, zuletzt_aktiv, laeuft_ab,
                  ip_hash, user_agent)
    workspaces(id, name, owner_id, phase, erstellt)
    workspace_members(workspace_id, user_id, rolle[read|modify|owner],
                      auftraggeber_name, gewaehrt_von, erstellt)
    claude_credentials(id, user_id, art[oauth_token|api_key], ciphertext,
                       nonce, key_version, letzte4, status, geprueft_am)
    runs(id, workspace_id, gestartet_von, art, auftraggeber, status,
         claude_session_id, modell, kosten_usd, tokens, start, ende,
         exit_code, pruefung_ok, commit_vorher, commit_nachher)
    run_events(id, run_id, seq, typ, payload_bereinigt, zeit)
    change_requests(id, workspace_id, art[config|regel|auslegung|init],
                    diff, status, erstellt_von, version)
    approvals(change_request_id, user_id, entscheidung, kommentar, zeit)
    ideas(id, workspace_id, user_id, text, status, run_id)
    audit_log(id, akteur, workspace_id, aktion, ziel, zeit, ip_hash, meta)

### 4.4 Claude-Anbindung

**Zugang je Benutzer** (Konto → Claude-Verbindung):

- Variante A, Claude-Abo: Der Benutzer erzeugt lokal mit
  `claude setup-token` ein langlebiges OAuth-Token (Pro/Max/Team/
  Enterprise, ein Jahr gültig) und hinterlegt es. Der Worker setzt es
  als `CLAUDE_CODE_OAUTH_TOKEN` nur für den jeweiligen Lauf.
- Variante B, API-Key aus der Claude Console (`ANTHROPIC_API_KEY`).
- Hinweis: Anthropic erlaubt Drittanbietern ohne Freigabe nicht, claude.ai-
  Login bzw. Abo-Limits in eigenen Produkten anzubieten
  (https://code.claude.com/docs/en/agent-sdk/overview, abgerufen
  2026-10-06). Ob ein selbst betriebenes, privates Werkzeug, in dem jeder
  Nutzer sein eigenes Token mit der offiziellen CLI verwendet, darunter
  fällt, müssen die Auftraggeber selbst bewerten (siehe Abschnitt 13,
  Frage 2). Die Architektur unterstützt beide Varianten gleichwertig.
- "Verbindung testen": minimaler Lauf (`--max-turns 1`, kurzer Prompt),
  Ergebnis ok/Fehlertext ohne Geheimnisse, gedrosselt.
- Speicherung: AES-256-GCM, Schlüssel aus Docker Secret (mit
  Versionsnummer für Rotation), Zusatzdaten = user_id + credential_id.
  Die API gibt das Token nie zurück, nur Art, letzte 4 Zeichen, Status,
  Prüfdatum. Entschlüsselt wird ausschließlich im Worker, im Speicher.

**Ablauf eines Laufs:**

1. Benutzer mit Recht `modify` und Auftraggeber-Zuordnung wählt Art
   (Trading-Session, Review, Testsession AP12, Frage an Claude,
   Idee prüfen, Entwicklungsauftrag) und startet.
2. API prüft Rechte, Phase, Sperre, Rate-Limits und legt den Lauf an
   (Idempotenzschlüssel).
3. Worker: `git pull` im Arbeitsbereich, startet
   `claude -p <Vorlagen-Prompt> --output-format stream-json` mit
   `cwd` = Arbeitsbereich, eigenem temporärem `CLAUDE_CONFIG_DIR`,
   minimaler Umgebung (nur Token, PATH, HOME, TZ), Zeit- und
   Speicherlimit. Der Prompt nennt die startende Person, damit Schritt 1
   aus CLAUDE.md entfällt.
4. Ereignisse werden bereinigt (Token-Muster entfernt), in `run_events`
   gespeichert und per Server-Sent Events live an die UI gestreamt.
5. Rückfragen von Claude beendet den Lauf im Status
   "wartet auf Antwort"; die Antwort setzt ihn mit `--resume` fort.
6. Nach dem Lauf: `pruefe.py` durch den Worker; Ergebnis, Kosten, Tokens
   und Commit-Bereich werden am Lauf gespeichert.

**Leitplanken für Claude im Arbeitsbereich** (vom Worker erzwungen,
nicht vom Arbeitsbereich änderbar):

- Verwaltete Claude-Code-Einstellungen mit `permissions.deny` für
  Write/Edit auf `portfolios/**`, `trades/**`, `data/**`, `config/**`,
  `regeln.md`, `tools/**` (außer im Entwicklungsauftrag) sowie auf
  `env`, `printenv`, `/proc`, `~/.claude`, `cat` von Geheimnissen.
- Bash nur für eine Positivliste: `python tools/*.py …`, `python -m
  pytest`, ausgewählte `git`-Befehle.
- PreToolUse-Hook als zweite Absicherung: prüft Pfade und Befehle,
  verhindert Änderungen an bestehendem Journal-Inhalt (nur Anhängen).
- Web-Suche erlaubt (Quellenpflicht bleibt).

## 5. Menüstruktur

Kopfzeile: Arbeitsbereich-Umschalter, Sessionstatus (Sperre, laufender
Lauf), Befehlspalette (Strg+K), Konto-Menü.

1. **Cockpit**
   - drei Portfolio-Karten: Wert, Rendite gegen Benchmark, Drawdown-Stufe,
     Cashquote; NAV-Verlauf gegen Benchmark; Warnungen aus `pruefe.py`;
     offene Orders; anstehende Termine und fällige Reviews; letzter Lauf.
2. **Portfolios** → Defensiv / Ausgewogen / Aggressiv, je mit Reitern:
   - Überblick (Kennzahlen aus ranking.md, NAV, Drawdown)
   - Positionen (Einstand, Wert, Hebel, Stop/Ziel, Abstand zum Stop)
   - Orders (offen, vorgemerkt, storniert, verfallen)
   - Trades (Ledger aus `trades/<profil>.csv`, filterbar)
   - Limits (Auslastung als Balken: Zertifikate-Anteil, Hebel, Exposure,
     Einzelposition, Cashquote, Risiko je Trade, Drawdown-Bremse)
   - Anlagerichtlinie (`strategie/<profil>.md` mit Änderungsverlauf)
3. **Entscheidungen** (Reasoning, Kernbereich)
   - Zeitachse: Session → Abwägungen je Portfolio → Orders → Ausführung
     → Änderungen → Verkauf/Stop/Ziel → Review
   - Trade-Akten: Liste aller Journal-Einträge; Detailseite je
     `J-…`-ID mit These, Szenario-Balken Bull/Base/Bear, Katalysator und
     Horizont, Kursdiagramm mit Einstieg/Stop/Ziel und Ausführungen,
     Risikorechnung, Limit-Schnappschuss zur Ausführung (aus
     `data/limits/`), Quellen (URL, Datum), Unsicherheiten, Ergebnis,
     Bezug in späteren Reviews und Lessons
   - Abwägungen und Nichtstun: begründete Nicht-Entscheidungen je
     Session und Portfolio (siehe Abschnitt 13, Frage 4)
   - Ideen der Auftraggeber: eingereicht → von Claude geprüft →
     angenommen/abgelehnt mit Begründung
4. **Sessions**
   - Neue Session (Art wählen, Hinweise auf fällige Reviews)
   - Live-Ansicht: Claude-Schritte, Werkzeugaufrufe und Ausgaben als
     aufklappbare Karten, Fortschritt entlang der 12 Schritte aus CLAUDE.md
   - Verlauf: alle Läufe mit Transkript, Kosten, Commits, Prüfergebnis
5. **Analyse**
   - Ranking und Benchmark, Profilvergleich
   - Reviews (Woche, Monat, Quartal, Drawdown-Stufe 2)
   - Lessons (Hypothese vs. bestätigt)
   - Markt und Kurse (`kurse.py aktuell/historie`, protokolliert)
   - Zertifikatsrechner (`produkte.py`, nur Anzeige)
6. **Regelwerk**
   - Spielregeln (regeln.md, nur lesen, mit Verlauf)
   - Profile und Limits, Kosten, Universum (Börsen, Feiertage,
     Basiswerte), Projekt → jeweils Formular mit Validierung
   - Änderungsanträge (Diff-Vorschau, Zustimmungen, Status)
7. **Aufbau (Phase 1)**
   - Arbeitspakete AP1–AP12 mit Abnahmekriterien, Status aus STATUS.md,
     verknüpften Commits und Testergebnissen
   - Auslegungsfragen 1–17: bestätigen oder Änderung beantragen;
     Entscheidung wird mit Datum und Person in STATUS.md vermerkt
   - Tests und Prüfung (pytest, `pruefe.py --historie` auslösen)
   - Initialisierung und Freigabe (Startdatum, Zustimmung beider
     Auftraggeber, dann `init.py`)
8. **Prüfung und Audit**: Prüfskript-Ergebnisse, Git-Historie mit Diffs,
   Aktivitätsprotokoll des Arbeitsbereichs
9. **Arbeitsbereich**: Mitglieder und Freigaben (Lesen/Bearbeiten),
   Auftraggeber-Zuordnung, Git-Spiegel, Werkzeug-Update aus der Vorlage
10. **Konto**: Profil, Passwort, Zwei-Faktor, Claude-Verbindung, aktive
    Anmeldungen
11. **Administration** (nur Admins): Benutzer, Arbeitsbereiche
    (nur Metadaten), Systemstatus, globale Limits, Audit-Log

## 6. Rechtemodell

| Aktion | Leser (`read`) | Bearbeiter (`modify`) | Eigentümer (`owner`) | Admin |
| --- | --- | --- | --- | --- |
| Alles ansehen | ja | ja | ja | nur Metadaten, außer selbst Mitglied |
| Werkzeuge nur lesend (Kurse, Rechner, Prüfung) | ja | ja | ja | – |
| Idee einreichen | ja | ja | ja | – |
| Claude-Lauf starten (eigener Claude-Zugang) | nein | ja, wenn Auftraggeber | ja, wenn Auftraggeber | – |
| Änderungsantrag stellen/zustimmen | nein | ja, wenn Auftraggeber | ja, wenn Auftraggeber | – |
| Mitglieder/Freigaben verwalten | nein | nein | ja | – |
| Arbeitsbereich löschen | nein | nein | ja (mit Bestätigung) | – |
| Benutzer anlegen/sperren | – | – | – | ja |

Rollen können nie höher vergeben werden als die eigene; der Eigentümer
ist nicht entziehbar, nur übertragbar.

## 7. Sicherheitskonzept

| Anforderung | Umsetzung | Nachweis (Test) |
| --- | --- | --- |
| Keine einsehbaren API-Keys | Secrets nur als Docker Secrets; Frontend ohne Schlüssel; Claude-Tokens verschlüsselt, schreibgeschützte Felder; Log- und Transkript-Bereinigung (Muster `sk-ant-…`, OAuth-Token); Claude kann `env` nicht lesen; gitleaks in CI | Test: kein Endpunkt, Log oder Run-Event enthält ein gesetztes Test-Token |
| RLS | `ENABLE` + `FORCE ROW LEVEL SECURITY` auf allen Mandantentabellen; App-Rolle ohne `BYPASSRLS`, nicht Tabelleneigentümer; `SET LOCAL app.user_id` je Transaktion; Policies über `SECURITY DEFINER`-Funktion mit festem `search_path` | DB-Tests: ohne Kontext 0 Zeilen; fremder Kontext 0 Zeilen; Schreiben in fremde Zeilen scheitert |
| Admin-Routen sperren | eigener Router `/api/admin` mit Admin-Abhängigkeit auf Router-Ebene; Admin-Flag nur aus DB; Zwei-Faktor für Admins Pflicht; erneute Anmeldung für kritische Aktionen; Nicht-Admins erhalten 404 | Matrixtest aller Admin-Routen |
| Benutzer-Isolation testen | automatischer Matrixtest: alle Routen aus OpenAPI × {anonym, fremd, read, modify, owner, admin}; IDOR-Tests mit fremden UUIDs; SSE-Streams und Dateizugriffe einzeln; Playwright-E2E mit zwei Benutzern | neue Route ohne Matrixeintrag lässt den Test scheitern |
| Rate-Limiting | Redis Sliding Window je IP und Benutzer; Login 5/min mit wachsender Sperre; Verbindungstest 5/h; Claude-Läufe 1 parallel je Arbeitsbereich und Tageslimit je Benutzer; Kursabfragen gedrosselt; Body-Größenlimit; 429 mit `Retry-After` | Tests für jedes Limit |
| Storage sperren | Workspace-Volumes nie statisch ausgeliefert; Zugriff nur über API mit Rechteprüfung; Pfade kanonisch auflösen, `..` und Symlinks nach außen ablehnen; Downloads über kurzlebige, signierte, benutzergebundene URLs; Verzeichnisse `0700`; Backups verschlüsselt | Path-Traversal-Tests, abgelaufene/fremde Download-URLs |
| Alle Inputs validieren | Pydantic v2 `strict`, `extra="forbid"`, Muster für Ticker, IDs, Datumswerte, Decimal-Bereiche, Enums für Profile/Typen; Werkzeugaufrufe nur als Argumentliste aus Positivliste (`shell=False`); Längenlimits für Freitext und Prompts | Fuzz-/Negativtests je Endpunkt |
| Unauthentifizierte Routen blockieren | Default-Deny: globale Auth-Abhängigkeit; explizite Ausnahmeliste (Login, Health minimal, Erst-Einrichtung nur solange kein Admin existiert); OpenAPI/Docs in Produktion aus | Test: jede Route ohne Sitzung → 401, außer Ausnahmeliste |
| SQL-Injection blockieren | nur ORM/gebundene Parameter; Lint-Regeln (ruff `S608`, semgrep gegen `text()` mit f-Strings); minimale DB-Rechte | Payload-Tests |
| Field-Tampering unterbinden | getrennte Create/Update/Read-Schemas; `owner_id`, `rolle`, `workspace_id`, Zeitstempel nie vom Client; Rollenänderung nur über eigenen Endpunkt; Versionsfeld (ETag) gegen verlorene Updates; nicht erratbare UUIDs | Tests mit zusätzlichen/manipulierten Feldern |
| Server-Logik absichern | alle Regeln serverseitig (Rechte, Phase, Sperre, Vier-Augen bei Änderungsanträgen, Lauf-Zustandsautomat); Idempotenzschlüssel; Subprozesse mit Zeit-/Speicherlimit; `pruefe.py` nach jedem Lauf | Zustandsübergangstests |
| API-Responses trimmen | explizite `response_model`s; keine internen Pfade, Stacktraces, E-Mails fremder Benutzer; generische Fehlermeldungen mit Korrelations-ID; Paginierung | Snapshot-Tests der Antwortfelder |
| Auth-Sessions absichern | serverseitige Sitzungen (256-Bit-ID, gehasht gespeichert); Cookie `__Host-sid` HttpOnly, Secure, SameSite=Strict; Rotation bei Login und Rechtewechsel; Leerlauf 30 min, absolut 12 h; CSRF-Token + Origin-Prüfung; Argon2id; TOTP; Abmelden aller Geräte | Tests für Ablauf, Rotation, CSRF |
| Abhängigkeiten prüfen | Lockfiles mit Hashes; pip-audit, pnpm audit, osv-scanner; Trivy-Image-Scan; SBOM (syft); Dependabot/Renovate; Claude Code CLI gepinnt; `pnpm install --frozen-lockfile`, Install-Skripte nur für Positivliste | CI-Job bricht bei bekannten kritischen Lücken ab |

Zusätzlich: Security-Header über Caddy (strikte CSP ohne Inline-Skripte,
`frame-ancestors 'none'`, HSTS, Referrer-Policy, Permissions-Policy),
CORS nur gleiche Origin, Audit-Log für alle schreibenden Aktionen,
OWASP-ZAP-Baseline-Scan gegen die laufende Compose-Umgebung.

**Initialer Administrator:** Es gibt keine Selbstregistrierung.
`docker compose run --rm api stockmaster admin anlegen --email …`
erzeugt den Admin mit Einmalpasswort (nur in der Konsole ausgegeben);
bei der ersten Anmeldung sind Passwortwechsel und Zwei-Faktor Pflicht.
Weitere Benutzer legt nur ein Admin an (ebenfalls mit Einmalpasswort).

## 8. Zielstruktur im Repository

    webui/
      backend/          FastAPI-App, Alembic-Migrationen, Tests (pyproject, uv.lock)
      frontend/         React-SPA (package.json, pnpm-lock.yaml)
      worker/           Lauf-Steuerung, Claude-Leitplanken (Einstellungen, Hooks)
      deploy/           Caddyfile, Dockerfiles
    docker-compose.yml
    .env.example
    pytest.ini          beschränkt das bestehende `pytest` auf tests/ (CI unverändert)

## 9. Arbeitspakete

Je Paket: Code mit Tests, kleine Commits (`aufbau:`), Abnahme erfüllt,
dann in STATUS.md abhaken. Sicherheitsanforderungen werden in jedem
Paket mit umgesetzt; W14 prüft sie gesammelt.

**W0 Entscheidungen.** Antworten aus Abschnitt 13 in STATUS.md, Hinweis
auf diesen Auftrag in CLAUDE.md (nur nach Freigabe).
Abnahme: Entscheidungen mit Datum und Person vermerkt.

**W1 Grundgerüst und Docker.** Struktur aus Abschnitt 8, Compose mit
allen Diensten, Netzen, Secrets, Healthchecks, Caddy mit TLS `internal`.
Abnahme: `docker compose up` startet alle Dienste gesund; nur der
Proxy-Port ist erreichbar; bestehendes `pytest` läuft unverändert.

**W2 Datenbank und RLS.** Schema aus 4.3, Rollen, Policies, Migrationen.
Abnahme: RLS-Tests (ohne Kontext, fremder Kontext, Schreibversuch) grün.

**W3 Authentifizierung.** Admin-Erstanlage per CLI, Login, Sitzungen,
CSRF, TOTP, Sperre bei Fehlversuchen, Passwortwechsel.
Abnahme: Tests für alle Punkte aus Abschnitt 7 "Auth-Sessions".

**W4 Benutzerverwaltung.** Admin-Router: anlegen, sperren, Passwort
zurücksetzen, Zwei-Faktor zurücksetzen.
Abnahme: Matrixtest Admin-Routen.

**W5 Arbeitsbereiche und Freigaben.** Anlegen aus Vorlage, Import des
bestehenden Repos, lokales Bare-Origin, Mitglieder mit Rollen,
Auftraggeber-Zuordnung.
Abnahme: `session.py start/ende` und `pruefe.py --historie` laufen in
einem neuen Arbeitsbereich; Isolationstests für Freigaben.

**W6 Lesedienst.** Parser für portfolios, trades, nav, limits, journal
(Vorlage aus CLAUDE.md), reviews, strategie, lessons, ranking, STATUS.md
(Arbeitspakete, Entscheidungen, Auslegungsfragen), config, Git-Log.
Abnahme: Tests mit Beispieldaten aus den Szenario-Tests; unbekannte
Formate werden als Rohtext angezeigt statt zu scheitern.

**W7 Werkzeug-Ausführung.** Positivliste lesender Befehle (kurse,
limits pruefen, produkte, pruefe, bewertung bericht, session status,
pytest) über den Worker; Ausgaben gespeichert.
Abnahme: kein Aufruf außerhalb der Positivliste möglich; Zeitlimit greift.

**W8 Claude-Anbindung.** Zugangsverwaltung (verschlüsselt), Verbindungstest,
Lauf-Steuerung mit Leitplanken, Streaming, Rückfragen/Fortsetzen,
Kosten und Tokens, Prüfung nach dem Lauf.
Abnahme: Lauf mit Attrappe der CLI in Tests (ohne Netzwerk); Versuch,
`trades/` zu ändern oder `env` zu lesen, wird blockiert; kein Token in
Logs/Events.

**W9 Frontend-Grundgerüst und Designsystem.** Layout, Navigation aus
Abschnitt 5, Theme, Anmeldung, Fehler- und Ladezustände, deutsche
Zahlen- und Datumsformate.
Abnahme: Lighthouse-Barrierefreiheit ≥ 90; responsive bis Tablet.

**W10 Cockpit und Portfolios.** Abnahme: alle Werte stimmen mit
`ranking.md`/`data/nav` überein (Test gegen Beispieldaten).

**W11 Entscheidungen.** Zeitachse, Trade-Akten, Abwägungen, Ideen.
Abnahme: jede Order ist von der Akte aus bis zu Journal, Lauf und
Ausführung verfolgbar.

**W12 Regelwerk und Aufbau.** Konfigurationsformulare mit Validierung
(gleiche Prüfungen wie `tests/test_konfiguration.py`), Änderungsanträge
mit Vier-Augen-Freigabe, die regeln.md und config/ gemeinsam ändern,
Arbeitspakete, Auslegungsfragen, Initialisierung und Freigabe.
Abnahme: eine Limit-Änderung ohne passende Änderung in regeln.md ist
unmöglich; `pruefe.py` bleibt grün; kein Antrag wirkt ohne alle
Zustimmungen.

**W13 Prüfung, Audit, Konto, Administration (UI).**
Abnahme: E2E-Tests der wichtigsten Abläufe.

**W14 Sicherheitshärtung.** Vollständige Isolationsmatrix, ZAP-Scan,
Header-Prüfung, Review aller Punkte aus Abschnitt 7.
Abnahme: alle Nachweise aus Abschnitt 7 grün, Befunde behoben.

**W15 CI und Lieferkette.** GitHub Action um Jobs für Backend-, Frontend-
und E2E-Tests, Lint, Audits, Image-Scan, SBOM erweitern; bestehender
Job bleibt unverändert.
Abnahme: grüner Lauf auf GitHub.

**W16 Dokumentation und Betrieb.** README-Abschnitt Web-UI,
Betriebshandbuch (Start, Update, Backup/Restore, Schlüsselrotation).
Abnahme: Neuinstallation nach Anleitung auf einem frischen Rechner.

## 10. Reihenfolge und Abhängigkeiten

W0 → W1 → W2 → W3 → W4 → W5 → W6/W7 (parallel möglich) → W8 → W9 →
W10/W11/W12 (parallel möglich) → W13 → W14 → W15 → W16.
Frontend-Grundgerüst (W9) kann nach W3 parallel zu W5–W8 beginnen.

## 11. Teststrategie

- Backend: pytest mit echter PostgreSQL (Service-Container in CI),
  Claude-CLI und Yahoo als Attrappen; kein Netzwerk in Unit-Tests.
- Frontend: Vitest + Testing Library; Playwright-E2E gegen die
  Compose-Umgebung mit zwei Benutzern.
- Sicherheit: Isolationsmatrix, RLS-Tests, Fuzzing der Eingaben,
  ZAP-Baseline.
- Die bestehenden Werkzeuge und Tests bleiben unverändert und laufen
  weiter in ihrem eigenen Job.

## 12. Nicht Teil dieses Auftrags

Manuelle Orders, echte Broker, Zugriff aus dem Internet ohne
vorgeschalteten Zugangsschutz, Mobil-App, automatischer zeitgesteuerter
Session-Start (bleibt offener Punkt aus KONZEPT.md, kann später ergänzt
werden).

## 13. Offene Entscheidungen (vor Umsetzung zu klären)

1. **Bedeutung von "Arbeitsbereich":** eigenständige Spielinstanz mit
   eigenen drei Portfolios und eigenem Git-Repo (Vorschlag), oder ein
   gemeinsames Spiel mit mehreren Ansichten?
2. **Claude-Zugang:** beide Varianten (Abo-Token über `claude setup-token`
   und API-Key) anbieten (Vorschlag), oder nur API-Keys wegen des
   Anthropic-Hinweises in 4.4?
3. **Auftraggeber und Regeländerungen:** Web-Benutzer werden je
   Arbeitsbereich einem Auftraggeber-Namen zugeordnet; nur Auftraggeber
   starten Sessions; Änderungen an regeln.md/config/ brauchen die
   Zustimmung aller Auftraggeber des Arbeitsbereichs (Vorschlag). Passt das?
4. **Abwägungen sichtbar machen:** Heute schreibt Claude Journal-Einträge
   nur für Orders; "Nichtstun" steht nur in der Session-Zusammenfassung.
   Vorschlag: CLAUDE.md um einen nur anzuhängenden Session-Eintrag
   `S-JJJJMMTT-NN` je Session ergänzen (je Portfolio: Entscheidung,
   verworfene Alternativen, Begründung). Erlaubt?
5. **Zeitpunkt:** Web-UI vor oder nach AP12/Phase 2 bauen? (Laut
   AUFTRAG_PHASE1.md ist die Weboberfläche nicht Teil von Phase 1.)
6. **Erreichbarkeit:** nur auf dem eigenen Rechner (`127.0.0.1`,
   Vorschlag) oder im Heimnetz bzw. über das Internet?
