# Entwicklungsauftrag Web-UI (Phase 2)

Stand: v0.3 vom 2026-10-06. Entscheidungen vom 2026-10-06 sind
eingearbeitet (STATUS.md, Entscheidungen 1 bis 12). Alle Punkte aus
Abschnitt 14 sind geklärt. Noch kein Code.

## 1. Ziel

Eine moderne Weboberfläche für das Börsenexperiment, lokal per Docker
betrieben und standardmäßig nur aus dem Heimnetz erreichbar:

- Ein initialer Administrator legt Benutzer an. Es gibt keine
  Selbstregistrierung.
- Jeder Benutzer legt eigene Arbeitsbereiche (Spielinstanzen mit
  Portfolios) an und teilt sie bei Bedarf mit anderen Benutzern, mit
  den Stufen **Lesen** und **Vollzugriff**.
- Jeder Arbeitsbereich ist über Mehrfachauswahlen nach Schwerpunkt und
  Anlagestrategie konfigurierbar, z. B. Technologie, Gesundheit, nur
  USA, nur Deutschland.
- Jeder Benutzer verbindet sein privates Claude-Pro-Abo und kann es
  testen. Claude führt die Sessions aus; die UI zeigt sie live.
- Alles aus dem Repository ist einsehbar, die Punkte aus
  AUFTRAG_PHASE1.md sind einsehbar und, soweit regelkonform,
  konfigurierbar.
- Das Reasoning hinter jedem Trade und jeder Abwägung, auch hinter
  begründetem Nichtstun, ist übersichtlich nachvollziehbar.

## 2. Leitplanken (zusätzlich zu CLAUDE.md und regeln.md)

1. **Die Web-UI rechnet nicht.** Kurse, Buchungen, Limits und Kennzahlen
   kommen ausschließlich aus `tools/`. Die UI ruft Werkzeuge auf und zeigt
   deren Ergebnisse; sie implementiert keine Spiellogik nach.
2. **Die Web-UI bucht nicht.** Es gibt keine manuelle Ordermaske. Orders
   entstehen nur durch Claude über `tools/buchen.py`. Benutzer reichen
   Ideen ein, die Claude kritisch prüft.
3. **Keine Handbearbeitung** von `portfolios/`, `trades/`, `data/` und
   bestehendem Journal-Inhalt, auch nicht über die UI.
4. **Git bleibt die Prüfspur.** Jeder Arbeitsbereich ist ein eigenes
   Git-Repository; `pruefe.py` und die Nur-Anhängen-Prüfung laufen
   unverändert.
5. **Regeländerungen nur durch die Auftraggeber** des Arbeitsbereichs,
   mit Datum, ohne Rückwirkung.
6. **Kein Backdating:** Zeitstempel setzt ausschließlich der Server.
7. **Keine Namen oder personenbezogenen Daten in Repositories**
   (CLAUDE.md, Grundsatz 5). Personen erscheinen in Arbeitsbereich-Repos
   nur als neutrale Kennung (z. B. `a-7k2m`); Anzeigenamen, E-Mail-
   Adressen und die Zuordnung Kennung → Person liegen ausschließlich in
   der Datenbank der Web-UI.
8. Die Phase-1-Festlegung "nur pandas, yfinance, pytest" gilt weiter für
   `tools/`. Die Web-UI hat eigene, gesperrte Abhängigkeiten unter
   `webui/`; die Begründung steht in STATUS.md.

## 3. Toolstack

| Schicht | Wahl | Begründung |
| --- | --- | --- |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4, shadcn/ui (Radix), lucide-Icons | modernes, zugängliches Designsystem, Dark/Light-Theme |
| Routing/Daten | TanStack Router, TanStack Query, react-hook-form + zod | typsicher, Caching, Formularvalidierung |
| Diagramme | Recharts (KPIs, NAV, Drawdown), TradingView lightweight-charts (Kursverlauf mit Einstieg/Stop/Ziel) | ansprechend und performant |
| Markdown | react-markdown + rehype-sanitize (kein Roh-HTML) | Journal, Reviews, Regeln sicher anzeigen |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic | gleiche Sprache wie `tools/`, strenge Validierung |
| Jobs | Arq (Redis) als Worker für Werkzeug- und Claude-Läufe | lange Läufe außerhalb des Request-Zyklus |
| Datenbank | PostgreSQL 16 mit Row Level Security | Mandantentrennung in der Datenbank |
| Cache/Limits | Redis 7 | Rate-Limiting, Job-Queue, Live-Ereignisse |
| Claude | offizielle Claude Code CLI, ohne Oberfläche (`claude -p --output-format stream-json`), Version gepinnt | gleiche Werkzeuge, Hooks und Rechte wie heute |
| Reverse Proxy | Caddy 2 (TLS mit lokaler CA, Security-Header, Auslieferung der SPA) | HTTPS auch im Heimnetz, damit `Secure`-Cookies greifen |
| Paketmanager | uv (Lockfile mit Hashes), pnpm (Lockfile) | reproduzierbar und prüfbar |

## 4. Architektur

### 4.1 Container (docker-compose.yml)

| Dienst | Aufgabe | Netz | Besonderheiten |
| --- | --- | --- | --- |
| `proxy` | Caddy, liefert die SPA aus, leitet `/api` weiter | `edge`, `app` | einziger veröffentlichter Port; lässt standardmäßig nur private Adressbereiche zu (Abschnitt 4.6) |
| `api` | FastAPI | `app`, `data` | nicht-root, read-only Root-FS, kein Docker-Socket |
| `worker` | führt `tools/` und Claude-Läufe aus | `data`, `egress` | Python, git, Node + Claude Code CLI; ausgehend nur Internet (Anthropic, Yahoo, Web-Suche) |
| `db` | PostgreSQL | `data` (internal) | kein veröffentlichter Port |
| `redis` | Redis mit Passwort | `data` (internal) | kein veröffentlichter Port |

Volumes: `pgdata`, `workspaces`, `backups`. Geheimnisse (DB-Passwörter,
Schlüssel für die Token-Verschlüsselung, Session-Secret) nur als Docker
Secrets; `.env.example` ohne Werte. Alle Container: `cap_drop: ALL`,
`no-new-privileges`, Ressourcenlimits, Healthchecks, Basis-Images per
Digest gepinnt.

### 4.2 Arbeitsbereich

- Ein Arbeitsbereich ist eine eigenständige Spielinstanz: eigenes
  Git-Repository unter `/data/workspaces/<uuid>/repo`, eigene Portfolios
  (immer defensiv, ausgewogen und aggressiv mit je 1.000 EUR;
  Entscheidung 8), eigene Benchmark, eigenes Journal.
- Erzeugt wird er aus einer **Vorlage** (Spielteil dieses Repositorys:
  CLAUDE.md, regeln.md, config/, tools/, tests/, Vorlagen in strategie/)
  als frischer erster Commit ohne Historie, damit keine Altdaten
  übernommen werden.
- Als `origin` dient ein lokales Bare-Repository im selben Volume, damit
  `session.py start` (commit und push) unverändert funktioniert.
  Optional: Spiegelung auf ein privates GitHub-Repository (Deploy-Key
  verschlüsselt gespeichert); dann läuft dort auch die GitHub Action.
- `config/projekt.json` des Arbeitsbereichs enthält als `auftraggeber`
  nur die neutrale Kennung des Erstellers (Entscheidung 3, Leitplanke 7).
- Werkzeug-Updates aus der Vorlage nur als sichtbarer Merge-Vorgang mit
  Zustimmung des Erstellers; keine stillen Änderungen an `tools/`.
- Je Arbeitsbereich höchstens ein laufender Claude-Lauf; zusätzlich gilt
  `session.lock`.
- Lebenszyklus: **Einrichtung** (Schwerpunkt wählen, Anlagerichtlinien
  durch Claude ausformulieren lassen, Testsession ohne Order, Freigabe
  durch den Ersteller, `init.py` mit Startdatum; entspricht AP12) →
  **Betrieb** → optional **Archiviert** (nur lesen).

### 4.3 Schwerpunkt und Anlagestrategie (Mehrfachauswahl)

Je Arbeitsbereich in `config/schwerpunkt.json`, in der UI als
Mehrfachauswahl (Chips mit Suche). Eine leere Auswahl bedeutet: keine
Einschränkung über regeln.md hinaus.

| Dimension | Auswahl | Datengrundlage | Prüfung |
| --- | --- | --- | --- |
| Region (Firmensitz) | Deutschland, Europa ohne Deutschland, USA, übrige Welt | Yahoo-Feld `country`, protokolliert | prüfbar |
| Handelsplatz | Xetra, NYSE/NASDAQ | Ticker-Suffix (config/universum.json) | prüfbar |
| Sektor | die 11 Yahoo-Sektoren, z. B. Technologie, Gesundheit, Finanzen, Industrie, Energie, Basiskonsum, zyklischer Konsum, Kommunikation, Versorger, Immobilien, Grundstoffe | Yahoo-Feld `sector`, protokolliert | prüfbar |
| Basiswerte für Zertifikate | DAX, Euro Stoxx 50, S&P 500, Nasdaq 100, Gold, Brent, Einzelaktien laut obiger Auswahl | config/universum.json | prüfbar |
| ETFs | Positivliste je Arbeitsbereich mit Zuordnung zu Region/Sektor | config/schwerpunkt.json | prüfbar |
| Anlagestil | Wachstum, Value, Dividende, Qualität, Momentum, defensiv-zyklisch | Einschätzung | Leitlinie |
| Themen | Freitext-Schlagworte, z. B. KI, Halbleiter, Medizintechnik (je max. 40 Zeichen, max. 10) | Einschätzung | Leitlinie |

- **Prüfbare Dimensionen** prüft ein neues Limit "Schwerpunkt" in
  `tools/limits.py` bei Erfassung und Ausführung, wenn die Durchsetzung
  auf **verbindlich** steht (Standard). Unbekannte Region oder unbekannter
  Sektor gelten als nicht passend (ungünstigere Annahme, wie bei der
  Marktkapitalisierung). Stufe **Leitlinie**: keine harte Prüfung; Claude
  begründet jede Abweichung im Journal.
- **Leitlinien** (Stil, Themen) fließen in die Anlagerichtlinien
  `strategie/<profil>.md` und in den Session-Prompt ein; Claude
  dokumentiert im Session-Eintrag, wie sie berücksichtigt wurden.
- Änderungen am Schwerpunkt nach dem Startdatum sind Regeländerungen
  (Datum, keine Rückwirkung); bestehende Positionen müssen nicht
  verkauft werden, neue Käufe müssen passen.
- Die Benchmark bleibt laut regeln.md Abschnitt 9 der MSCI-World-ETF.
  Eine schwerpunktgerechte Benchmark wäre eine Regeländerung und ist als
  späteres Arbeitspaket vorgemerkt.
- Regelgrundlage: regeln.md v1.2, Abschnitt 3 "Schwerpunkt je
  Arbeitsbereich" (Entscheidung 10).

### 4.4 Datenhaltung

- **Quelle der Wahrheit für Spieldaten ist das Git-Repository** des
  Arbeitsbereichs. Die API liest Dateien über einen Lesedienst (Parser für
  JSON, CSV, JSONL und Markdown) und cacht je Commit-Hash.
- **PostgreSQL** hält nur Metadaten. Alle mandantenbezogenen Tabellen
  haben RLS:

      users(id, email, anzeigename, kennung, passwort_hash, ist_admin,
            aktiv, totp_secret_enc, passwortwechsel_noetig, fehlversuche,
            gesperrt_bis, erstellt)
      auth_sessions(id_hash, user_id, erstellt, zuletzt_aktiv, laeuft_ab,
                    ip_hash, user_agent)
      workspaces(id, name, ersteller_id, phase, schwerpunkt_kurz,
                 erstellt, archiviert)
      workspace_members(workspace_id, user_id, stufe[lesen|vollzugriff],
                        gewaehrt_von, erstellt)
      claude_credentials(id, user_id, ciphertext, nonce, key_version,
                         letzte4, status, geprueft_am, laeuft_ab)
      runs(id, workspace_id, gestartet_von, art, status,
           claude_session_id, modell, tokens, start, ende, exit_code,
           pruefung_ok, commit_vorher, commit_nachher)
      run_events(id, run_id, seq, typ, payload_bereinigt, zeit)
      change_requests(id, workspace_id, art[schwerpunkt|config|regel|
                      auslegung|freigabe], diff, status, erstellt_von,
                      version)
      ideas(id, workspace_id, user_id, text, status, run_id)
      audit_log(id, akteur, workspace_id, aktion, ziel, zeit, ip_hash, meta)

- `kennung` ist eine zufällige, neutrale Kennung (z. B. `a-7k2m`), die in
  Repositories anstelle von Namen verwendet wird.

### 4.5 Claude-Anbindung

**Zugang** (Konto → Claude-Verbindung), Entscheidung 2:

- Ausschließlich private Claude-Pro-Abos, keine nutzungsabhängig
  abgerechneten API-Keys. Der Benutzer erzeugt auf seinem Rechner mit
  `claude setup-token` ein OAuth-Token (laut Anthropic-Doku für Pro, Max,
  Team und Enterprise; ein Jahr gültig) und hinterlegt es in der UI.
  Quelle: https://code.claude.com/docs/en/authentication (abgerufen
  2026-10-06).
- Der Worker setzt das Token nur für den jeweiligen Lauf als
  `CLAUDE_CODE_OAUTH_TOKEN`. `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`
  und `apiKeyHelper` werden im Lauf ausdrücklich entfernt bzw. gesperrt,
  weil sie laut Doku Vorrang vor dem OAuth-Token hätten.
- Hinweis in der UI: Falls im claude.ai-Konto eine kostenpflichtige
  Zusatznutzung aktiviert ist, sollte sie dort deaktiviert werden, damit
  wirklich keine nutzungsabhängigen Kosten entstehen. Das kann die Web-UI
  nicht selbst prüfen.
- Anthropic-Hinweis zu Drittanbieter-Produkten (siehe STATUS.md,
  Entscheidung 2): Entschieden wurde, die Variante mit
  eigenen Pro-Abos in der privat betriebenen Installation zu nutzen.
- "Verbindung testen": minimaler Lauf (`--max-turns 1`, kurzer Prompt),
  Ergebnis ok/Fehlertext ohne Geheimnisse, gedrosselt; Anzeige des
  Ablaufdatums des Tokens und Erinnerung 14 Tage vorher.
- Speicherung: AES-256-GCM, Schlüssel aus Docker Secret (mit Version für
  Rotation), Zusatzdaten = user_id + credential_id. Die API gibt das
  Token nie zurück, nur letzte 4 Zeichen, Status, Prüf- und Ablaufdatum.
  Entschlüsselt wird ausschließlich im Worker, im Speicher.
- **Nutzungslimits des Pro-Abos:** Eine volle Trading-Session mit
  Recherche kann das Kontingent des Abos erreichen. Der Lauf geht dann in
  den Status "pausiert (Nutzungslimit)" und kann nach dem Zurücksetzen
  fortgesetzt werden; angefangene Orders gibt es dabei nicht, weil jede
  Order einzeln über `buchen.py` läuft.
- Modell: Standard der CLI für das Abo; im Arbeitsbereich wählbar, soweit
  das Abo das Modell anbietet.

**Wer startet Läufe:** Ersteller und Mitglieder mit Vollzugriff, jeweils
mit dem **eigenen** Claude-Abo. In der Sperre und im Journal erscheint die
Kennung des Erstellers als Auftraggeber (`config/projekt.json`); wer den
Lauf tatsächlich gestartet hat, steht nur in der Datenbank (`runs`,
`audit_log`). Grundlage: Entscheidung 9, regeln.md Abschnitt 12.

**Ablauf eines Laufs:**

1. Art wählen: Trading-Session, Review, Testsession (Einrichtung),
   Anlagerichtlinien ausformulieren, Frage an Claude (nur lesend), Idee
   prüfen.
2. Die API prüft Rechte, Phase, Sperre, Rate-Limits und Claude-Zugang und
   legt den Lauf an (Idempotenzschlüssel).
3. Der Worker führt `git pull` aus und startet die CLI mit
   `cwd` = Arbeitsbereich, eigenem temporärem `CLAUDE_CONFIG_DIR`,
   minimaler Umgebung (Token, PATH, HOME, TZ), Zeit- und Speicherlimit.
   Der Prompt nennt die Auftraggeber-Kennung (Schritt 1 aus CLAUDE.md
   entfällt) sowie Schwerpunkt und Leitlinien.
4. Ereignisse werden bereinigt (Token-Muster entfernt), in `run_events`
   gespeichert und per Server-Sent Events live an die UI gestreamt.
5. Rückfragen von Claude beenden den Lauf im Status "wartet auf Antwort";
   die Antwort setzt ihn mit `--resume` fort.
6. Nach dem Lauf führt der Worker `pruefe.py` aus; Ergebnis, Tokens und
   Commit-Bereich werden am Lauf gespeichert.

**Leitplanken für Claude im Arbeitsbereich** (vom Worker erzwungen, im
Arbeitsbereich nicht änderbar):

- Verwaltete Claude-Code-Einstellungen mit `permissions.deny` für
  Write/Edit auf `portfolios/**`, `trades/**`, `data/**`, `config/**`,
  `regeln.md`, `tools/**`, `tests/**` sowie für `env`, `printenv`,
  `/proc`, `~/.claude` und das Lesen von Geheimnissen.
- Bash nur für eine Positivliste: `python tools/*.py …`,
  `python -m pytest`, ausgewählte `git`-Befehle.
- PreToolUse-Hook als zweite Absicherung: prüft Pfade und Befehle,
  erlaubt im Journal nur Anhängen und blockiert Namen und E-Mail-Adressen
  aus der Benutzertabelle in allen Schreibvorgängen (Leitplanke 7).
- Web-Suche erlaubt; Quellenpflicht bleibt.

### 4.6 Erreichbarkeit (Entscheidung 6)

- **Standard: nur Heimnetz.** Caddy lauscht auf dem Host, lässt aber nur
  private Adressbereiche zu (`10.0.0.0/8`, `172.16.0.0/12`,
  `192.168.0.0/16`, `127.0.0.0/8`, `fc00::/7`, `::1`); alles andere
  erhält 403. Am Router wird kein Port freigegeben.
- HTTPS mit lokaler Zertifizierungsstelle von Caddy; die Anleitung
  beschreibt das einmalige Installieren des Root-Zertifikats auf den
  Geräten im Heimnetz.
- **Optional, nie Standard: Zugriff von unterwegs** über ein Compose-
  Profil `extern`, das nur startet, wenn zusätzlich die Variable
  `ZUGRIFF_EXTERN=ein` gesetzt und die Option in der Administration
  bestätigt ist:
  - Variante A (empfohlen, geringer Aufwand): VPN (WireGuard oder
    Tailscale). Kein offener Port; der VPN-Adressbereich wird zur
    Positivliste hinzugefügt.
  - Variante B: eigene Domain mit Let's Encrypt und Portfreigabe. Nur
    zulässig, wenn Zwei-Faktor für alle Benutzer erzwungen ist; strengere
    Rate-Limits; die Anwendung verweigert den Start, wenn eine
    Voraussetzung fehlt.

## 5. Menüstruktur

Kopfzeile: Arbeitsbereich-Umschalter mit Schwerpunkt-Chips,
Sessionstatus (Sperre, laufender Lauf), Befehlspalette (Strg+K),
Konto-Menü.

1. **Cockpit**
   - Portfolio-Karten: Wert, Rendite gegen Benchmark, Drawdown-Stufe,
     Cashquote; NAV-Verlauf gegen Benchmark; Warnungen aus `pruefe.py`;
     offene Orders; fällige Reviews und Termine; letzter Lauf.
2. **Portfolios** → je Portfolio des Arbeitsbereichs mit Reitern:
   - Überblick (Kennzahlen aus ranking.md, NAV, Drawdown)
   - Positionen (Einstand, Wert, Hebel, Stop/Ziel, Abstand zum Stop,
     Region und Sektor)
   - Orders (offen, vorgemerkt, storniert, verfallen)
   - Trades (Ledger aus `trades/<profil>.csv`, filterbar)
   - Limits (Auslastung als Balken: Zertifikate-Anteil, Hebel, Exposure,
     Einzelposition, Cashquote, Risiko je Trade, Drawdown-Bremse,
     Schwerpunkt)
   - Anlagerichtlinie (`strategie/<profil>.md` mit Änderungsverlauf)
3. **Entscheidungen** (Reasoning, Kernbereich)
   - Zeitachse: Session → Abwägungen je Portfolio → Orders → Ausführung →
     Änderungen → Verkauf/Stop/Ziel → Review
   - Trade-Akten: alle Journal-Einträge `J-…`; Detailseite mit These,
     Szenario-Balken Bull/Base/Bear, Katalysator und Horizont,
     Kursdiagramm mit Einstieg/Stop/Ziel und Ausführungen,
     Risikorechnung, Limit-Schnappschuss zur Ausführung (aus
     `data/limits/`), Quellen (URL, Datum), Unsicherheiten, Ergebnis,
     Bezüge in späteren Reviews und Lessons
   - Abwägungen und Nichtstun: Session-Einträge `S-…` (CLAUDE.md) je
     Portfolio mit verworfenen Alternativen und Begründung
   - Ideen: eingereicht → von Claude geprüft → angenommen oder abgelehnt
     mit Begründung
4. **Sessions**
   - Neue Session (Art wählen, Hinweise auf fällige Reviews)
   - Live-Ansicht: Claude-Schritte, Werkzeugaufrufe und Ausgaben als
     aufklappbare Karten; Fortschritt entlang der Schritte aus CLAUDE.md
   - Verlauf: alle Läufe mit Transkript, Tokens, Commits, Prüfergebnis
5. **Analyse**
   - Ranking und Benchmark, Profilvergleich, Vergleich mit anderen
     eigenen bzw. geteilten Arbeitsbereichen (nur mit Leserecht)
   - Reviews (Woche, Monat, Quartal, Drawdown-Stufe 2)
   - Lessons (Hypothese oder bestätigt)
   - Markt und Kurse (`kurse.py aktuell/historie`, protokolliert)
   - Zertifikatsrechner (`produkte.py`, nur Anzeige)
6. **Regelwerk**
   - Spielregeln (regeln.md, nur lesen, mit Verlauf)
   - Schwerpunkt und Anlagestrategie (Mehrfachauswahlen aus 4.3,
     Durchsetzung verbindlich/Leitlinie)
   - Profile und Limits, Kosten, Universum (Börsen, Feiertage,
     Basiswerte), Projekt: jeweils Formular mit Validierung
   - Änderungsanträge (Diff-Vorschau, Freigabe, Status)
7. **Einrichtung und Aufbau**
   - Einrichtung des Arbeitsbereichs (entspricht AP12): Schwerpunkt,
     Anlagerichtlinien, Testsession, Freigabe, Startdatum
   - Aufbau Phase 1 (nur lesen): Arbeitspakete AP1–AP11 mit
     Abnahmekriterien, verknüpften Commits und Testergebnissen
   - Auslegungsfragen 1–17 (und folgende): bestätigen oder Änderung
     beantragen; Entscheidung mit Datum und Kennung in STATUS.md
   - Tests und Prüfung (pytest, `pruefe.py --historie` auslösen)
8. **Prüfung und Audit**: Prüfskript-Ergebnisse, Git-Historie mit Diffs,
   Aktivitätsprotokoll des Arbeitsbereichs
9. **Arbeitsbereich**: Freigaben (Lesen/Vollzugriff), Git-Spiegel,
   Werkzeug-Update aus der Vorlage, Archivieren, Löschen
10. **Konto**: Profil, Passwort, Zwei-Faktor, Claude-Verbindung, aktive
    Anmeldungen
11. **Administration** (nur Admins): Benutzer, Arbeitsbereiche (nur
    Metadaten), Systemstatus, Erreichbarkeit (4.6), globale Limits,
    Audit-Log

## 6. Rechtemodell

| Aktion | Lesen | Vollzugriff | Ersteller | Admin |
| --- | --- | --- | --- | --- |
| Alles im Arbeitsbereich ansehen | ja | ja | ja | nur Metadaten, außer selbst Mitglied |
| Lesende Werkzeuge (Kurse, Rechner, Prüfung) | ja | ja | ja | – |
| Idee einreichen | ja | ja | ja | – |
| Claude-Lauf starten (eigenes Pro-Abo) | nein | ja | ja | – |
| Änderungsantrag stellen | nein | ja | ja | – |
| Änderungsantrag freigeben (Regeln, Schwerpunkt, Startdatum) | nein | nein | ja | – |
| Freigaben verwalten, archivieren, löschen | nein | nein | ja | – |
| Arbeitsbereiche anlegen | jeder Benutzer für sich selbst | | | |
| Benutzer anlegen, sperren, Admin-Rolle vergeben | – | – | – | ja |

- Es gibt initial genau einen Administrator. Er kann weiteren Benutzern
  die Admin-Rolle geben; Admins brauchen Zwei-Faktor.
- Stufen können nie höher vergeben werden als die eigene; die
  Ersteller-Rolle ist nicht übertragbar (sie bestimmt die
  Auftraggeber-Kennung im Repository).

## 7. Sicherheitskonzept

| Anforderung | Umsetzung | Nachweis (Test) |
| --- | --- | --- |
| Keine einsehbaren API-Keys | Secrets nur als Docker Secrets; Frontend ohne Schlüssel; Claude-Tokens verschlüsselt, schreibgeschützte Felder; Log- und Transkript-Bereinigung; Claude kann Umgebungsvariablen nicht lesen; gitleaks in CI | kein Endpunkt, Log oder Run-Event enthält ein gesetztes Test-Token |
| RLS | `ENABLE` und `FORCE ROW LEVEL SECURITY` auf allen Mandantentabellen; App-Rolle ohne `BYPASSRLS`, nicht Tabelleneigentümer; `SET LOCAL app.user_id` je Transaktion; Policies über `SECURITY DEFINER`-Funktion mit festem `search_path` | ohne Kontext 0 Zeilen; fremder Kontext 0 Zeilen; Schreiben in fremde Zeilen scheitert |
| Admin-Routen sperren | eigener Router `/api/admin` mit Admin-Prüfung auf Router-Ebene; Admin-Flag nur aus der DB; Zwei-Faktor Pflicht; erneute Anmeldung für kritische Aktionen; Nicht-Admins erhalten 404 | Matrixtest aller Admin-Routen |
| Benutzer-Isolation testen | automatischer Matrixtest: alle Routen aus OpenAPI × {anonym, fremd, Lesen, Vollzugriff, Ersteller, Admin}; IDOR-Tests mit fremden UUIDs; SSE-Streams und Dateizugriffe einzeln; Playwright-E2E mit zwei Benutzern | eine neue Route ohne Matrixeintrag lässt den Test scheitern |
| Rate-Limiting | Redis Sliding Window je IP und Benutzer; Login 5/min mit wachsender Sperre; Verbindungstest 5/h; Claude-Läufe 1 parallel je Arbeitsbereich und Tageslimit je Benutzer; Kursabfragen gedrosselt; Body-Größenlimit; 429 mit `Retry-After` | Tests je Limit |
| Storage sperren | Workspace-Volumes nie statisch ausgeliefert; Zugriff nur über die API mit Rechteprüfung; Pfade kanonisch auflösen, `..` und Symlinks nach außen ablehnen; Downloads über kurzlebige, signierte, benutzergebundene URLs; Verzeichnisse `0700`; Backups verschlüsselt | Path-Traversal-Tests, abgelaufene/fremde Download-URLs |
| Alle Inputs validieren | Pydantic v2 `strict`, `extra="forbid"`; Muster für Ticker, IDs, Datumswerte; Decimal-Bereiche; Enums für Profile, Typen, Regionen, Sektoren; Werkzeugaufrufe nur als Argumentliste aus Positivliste (`shell=False`); Längenlimits für Freitext, Themen und Prompts | Negativ- und Fuzz-Tests je Endpunkt |
| Unauthentifizierte Routen blockieren | Default-Deny über globale Auth-Abhängigkeit; Ausnahmeliste (Login, minimaler Health-Check); OpenAPI/Docs in Produktion aus | jede Route ohne Sitzung → 401, außer Ausnahmeliste |
| SQL-Injection blockieren | nur ORM und gebundene Parameter; Lint-Regeln (ruff `S608`, semgrep gegen `text()` mit f-Strings); minimale DB-Rechte | Payload-Tests |
| Field-Tampering unterbinden | getrennte Create/Update/Read-Schemas; `ersteller_id`, `stufe`, `workspace_id`, `kennung`, Zeitstempel nie vom Client; Stufenänderung nur über eigenen Endpunkt; Versionsfeld (ETag) gegen verlorene Updates; nicht erratbare UUIDs | Tests mit zusätzlichen bzw. manipulierten Feldern |
| Server-Logik absichern | alle Regeln serverseitig (Rechte, Phase, Sperre, Freigaben, Zustandsautomat der Läufe); Idempotenzschlüssel; Subprozesse mit Zeit- und Speicherlimit; `pruefe.py` nach jedem Lauf | Zustandsübergangstests |
| API-Responses trimmen | explizite `response_model`s; keine internen Pfade, Stacktraces oder E-Mail-Adressen anderer Benutzer (nur Anzeigename); generische Fehlermeldungen mit Korrelations-ID; Paginierung | Snapshot-Tests der Antwortfelder |
| Auth-Sessions absichern | serverseitige Sitzungen (256-Bit-ID, gehasht gespeichert); Cookie `__Host-sid` HttpOnly, Secure, SameSite=Strict; Rotation bei Anmeldung und Rechtewechsel; Leerlauf 30 min, absolut 12 h; CSRF-Token und Origin-Prüfung; Argon2id; TOTP; Abmelden auf allen Geräten | Tests für Ablauf, Rotation, CSRF |
| Abhängigkeiten prüfen | Lockfiles mit Hashes; pip-audit, pnpm audit, osv-scanner; Trivy-Image-Scan; SBOM (syft); Dependabot; Claude Code CLI gepinnt; `pnpm install --frozen-lockfile`, Install-Skripte nur für eine Positivliste | CI bricht bei bekannten kritischen Lücken ab |
| Keine personenbezogenen Daten in Repos | Kennungen statt Namen; Hook blockiert Namen und E-Mail-Adressen; Prüfung vor jedem Commit des Workers | Test: Schreibversuch mit Benutzername wird blockiert |

Zusätzlich: Security-Header über Caddy (strikte CSP ohne Inline-Skripte,
`frame-ancestors 'none'`, HSTS, Referrer-Policy, Permissions-Policy),
CORS nur gleiche Origin, Audit-Log für alle schreibenden Aktionen,
OWASP-ZAP-Baseline-Scan gegen die laufende Compose-Umgebung.

**Initialer Administrator:** `docker compose run --rm api stockmaster
admin anlegen --email …` erzeugt den einzigen Admin mit Einmalpasswort
(nur in der Konsole ausgegeben). Bei der ersten Anmeldung sind
Passwortwechsel und Zwei-Faktor Pflicht. Der Befehl verweigert die
Ausführung, wenn bereits ein Admin existiert. Weitere Benutzer legt nur
ein Admin in der UI an (ebenfalls mit Einmalpasswort).

## 8. Zielstruktur im Repository

    webui/
      backend/          FastAPI-App, Alembic-Migrationen, Tests (pyproject, uv.lock)
      frontend/         React-SPA (package.json, pnpm-lock.yaml)
      worker/           Lauf-Steuerung, Claude-Leitplanken (Einstellungen, Hooks)
      vorlage/          Erzeugung neuer Arbeitsbereiche aus dem Spielteil
      deploy/           Caddyfile, Dockerfiles, Compose-Profil extern
    docker-compose.yml
    .env.example
    pytest.ini          beschränkt das bestehende `pytest` auf tests/ (CI unverändert)

## 9. Arbeitspakete

Je Paket: Code mit Tests, kleine Commits (`aufbau:`), Abnahme erfüllt,
dann in STATUS.md abhaken. Sicherheitsanforderungen werden in jedem
Paket mit umgesetzt; W14 prüft sie gesammelt.

**W0 Klärung.** Offene Punkte aus Abschnitt 14 klären und in STATUS.md
vermerken. Erledigt am 2026-10-06 (Entscheidungen 1 bis 12).
Abnahme: Entscheidungen mit Datum vermerkt.

**W1 Grundgerüst und Docker.** Struktur aus Abschnitt 8, Compose mit
allen Diensten, Netzen und Secrets, Healthchecks, Caddy mit lokaler CA
und Heimnetz-Positivliste.
Abnahme: `docker compose up` startet alle Dienste gesund; nur der
Proxy-Port ist erreichbar; Anfragen von öffentlichen Adressen erhalten
403; das bestehende `pytest` läuft unverändert.

**W2 Datenbank und RLS.** Schema aus 4.4, Rollen, Policies, Migrationen.
Abnahme: RLS-Tests (ohne Kontext, fremder Kontext, Schreibversuch) grün.

**W3 Authentifizierung.** Admin-Erstanlage per CLI (nur einmal), Login,
Sitzungen, CSRF, TOTP, Sperre bei Fehlversuchen, Passwortwechsel.
Abnahme: Tests für alle Punkte aus Abschnitt 7 "Auth-Sessions"; zweiter
Aufruf der Admin-Erstanlage wird abgelehnt.

**W4 Benutzerverwaltung.** Admin-Router: anlegen, sperren, Passwort und
Zwei-Faktor zurücksetzen, Admin-Rolle vergeben; Kennung je Benutzer.
Abnahme: Matrixtest der Admin-Routen.

**W5 Arbeitsbereiche und Freigaben.** Anlegen aus der Vorlage mit
Ersteller-Kennung, lokales Bare-Origin, Freigaben Lesen/Vollzugriff,
Archivieren, Löschen.
Abnahme: `session.py start/ende` und `pruefe.py --historie` laufen in
einem neuen Arbeitsbereich; Isolationstests für Freigaben; das neue
Repository enthält keine Namen.

**W6 Schwerpunkt.** Mehrfachauswahlen aus 4.3, `config/schwerpunkt.json`,
Erweiterung von `kurse.py` um protokollierte Stammdaten (Region, Sektor),
neues Limit "Schwerpunkt" in `limits.py` mit Tests (Grundlage:
regeln.md v1.2, Abschnitt 3). Eine Datei `config/schwerpunkt.json` wird
erst zusammen mit der Prüfung eingeführt.
Abnahme: je Dimension ein Test für Annahme und Ablehnung; unbekannte
Stammdaten führen bei "verbindlich" zur Ablehnung mit Regel, Grenzwert
und Istwert.

**W7 Lesedienst.** Parser für portfolios, trades, nav, limits, journal
(J- und S-Einträge), reviews, strategie, lessons, ranking, STATUS.md
(Arbeitspakete, Entscheidungen, Auslegungsfragen), config, Git-Log.
Abnahme: Tests mit Beispieldaten aus den Szenario-Tests; unbekannte
Formate werden als Rohtext angezeigt statt zu scheitern.

**W8 Werkzeug-Ausführung.** Positivliste lesender Befehle (kurse, limits
pruefen, produkte, pruefe, bewertung bericht, session status, pytest)
über den Worker; Ausgaben gespeichert.
Abnahme: kein Aufruf außerhalb der Positivliste möglich; Zeitlimit greift.

**W9 Claude-Anbindung.** Pro-Token verschlüsselt hinterlegen,
Verbindungstest, Ablaufwarnung, Lauf-Steuerung mit Leitplanken,
Streaming, Rückfragen und Fortsetzen, Pause bei Nutzungslimit, Prüfung
nach dem Lauf.
Abnahme: Lauf mit Attrappe der CLI in Tests (ohne Netzwerk); Versuche,
`trades/` zu ändern, Umgebungsvariablen zu lesen oder einen Namen ins
Journal zu schreiben, werden blockiert; kein Token in Logs oder Events;
gesetzte `ANTHROPIC_API_KEY` erreicht den Lauf nicht.

**W10 Frontend-Grundgerüst und Designsystem.** Layout, Navigation aus
Abschnitt 5, Theme, Anmeldung, Fehler- und Ladezustände, deutsche
Zahlen- und Datumsformate, App-Icon.
Abnahme: Lighthouse-Barrierefreiheit ≥ 90; nutzbar auf Tablet und
Smartphone im Heimnetz.

**W11 Cockpit und Portfolios.** Abnahme: alle Werte stimmen mit
`ranking.md` und `data/nav` überein (Test gegen Beispieldaten).

**W12 Entscheidungen.** Zeitachse, Trade-Akten, Abwägungen, Ideen.
Abnahme: jede Order ist von der Akte aus bis zu Journal, Session-Eintrag,
Lauf und Ausführung verfolgbar.

**W13 Regelwerk, Einrichtung und Aufbau.** Schwerpunkt- und
Konfigurationsformulare mit Validierung (gleiche Prüfungen wie
`tests/test_konfiguration.py`), Änderungsanträge mit Freigabe durch den
Ersteller, die regeln.md und config/ gemeinsam ändern; Einrichtungsablauf
(AP12) je Arbeitsbereich; Phase-1-Ansicht; Auslegungsfragen.
Abnahme: eine Limit-Änderung ohne passende Änderung in regeln.md ist
unmöglich; `pruefe.py` bleibt grün; kein Antrag wirkt ohne Freigabe.

**W14 Sicherheitshärtung.** Vollständige Isolationsmatrix, ZAP-Scan,
Header-Prüfung, Review aller Punkte aus Abschnitt 7.
Abnahme: alle Nachweise aus Abschnitt 7 grün, Befunde behoben.

**W15 CI und Lieferkette.** GitHub Action um Jobs für Backend-, Frontend-
und E2E-Tests, Lint, Audits, Image-Scan und SBOM erweitern; der bestehende
Job bleibt unverändert.
Abnahme: grüner Lauf auf GitHub.

**W16 Dokumentation und Betrieb.** README-Abschnitt Web-UI,
Betriebshandbuch (Start, Root-Zertifikat im Heimnetz, Update,
Backup/Restore, Schlüsselrotation, Pro-Token erneuern).
Abnahme: Neuinstallation nach Anleitung auf einem frischen Rechner.

**W17 Zugriff von unterwegs (optional).** Compose-Profil `extern` mit
Variante A (VPN) und Variante B (Domain, Let's Encrypt) nach 4.6.
Abnahme: ohne `ZUGRIFF_EXTERN=ein` und Admin-Bestätigung startet das
Profil nicht; Variante B startet nur mit erzwungener Zwei-Faktor-
Anmeldung für alle Benutzer.

## 10. Reihenfolge und Abhängigkeiten

W0 → W1 → W2 → W3 → W4 → W5 → W7/W8 (parallel möglich) → W9 → W10 →
W11/W12/W13 (parallel möglich) → W14 → W15 → W16 → W17 (optional).
W6 frühestens nach W5.
W10 kann nach W3 parallel zu W5 bis W9 beginnen.

## 11. Teststrategie

- Backend: pytest mit echter PostgreSQL (Service-Container in CI);
  Claude-CLI und Yahoo als Attrappen; kein Netzwerk in Unit-Tests.
- Frontend: Vitest und Testing Library; Playwright-E2E gegen die
  Compose-Umgebung mit zwei Benutzern.
- Sicherheit: Isolationsmatrix, RLS-Tests, Fuzzing der Eingaben,
  ZAP-Baseline.
- Die bestehenden Werkzeuge und Tests laufen weiter in ihrem eigenen Job.

## 12. Gestaltung

- Ruhiges, dunkles Standard-Theme mit hellem Alternativ-Theme; eine
  Akzentfarbe je Risikoprofil (z. B. Blau defensiv, Grün ausgewogen,
  Orange aggressiv) durchgängig in Karten, Diagrammen und Badges.
- Gewinne und Verluste nicht nur über Farbe, sondern zusätzlich über
  Vorzeichen und Symbol (Barrierefreiheit).
- Trade-Akten als gut lesbare Dokumentseiten mit Seitenleiste
  (Kennzahlen, Status, Verknüpfungen) statt reiner Tabellen.
- App-Icon und Favicon aus den Icon-Vorschlägen (Auswahl durch die
  Auftraggeber).

## 13. Nicht Teil dieses Auftrags

Manuelle Orders, echte Broker, nutzungsabhängig abgerechnete API-Keys,
öffentliche Erreichbarkeit als Standard, Mobil-App, zeitgesteuerter
Session-Start (bleibt offener Punkt aus KONZEPT.md), schwerpunktgerechte
Benchmarks (spätere Regeländerung).

## 14. Geklärte Punkte

1. Portfolios je Arbeitsbereich: immer die drei Profile (Entscheidung 8).
2. Läufe durch Mitglieder mit Vollzugriff: erlaubt mit eigenem Pro-Abo;
   Sperre und Journal tragen die Kennung des Auftraggebers
   (Entscheidung 9).
3. regeln.md: einmalig auf v1.2 angepasst, neutral formuliert und um den
   Schwerpunkt ergänzt; dient so auch als Vorlage für neue
   Arbeitsbereiche (Entscheidung 10).
4. Namen im Repository: entfernt bis auf die Git-Historie
   (Entscheidung 12).
5. Startdatum: erst nach Freigabe von AP12 (Entscheidung 11).
