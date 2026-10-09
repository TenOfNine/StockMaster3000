# Betrieb

Der Docker-Stack läuft **autark**: Spielstand, Kurse, News, Journal, Reviews und Sessions leben nur
in Volumes im Container; Einstellungen und Secrets werden in der App gepflegt (Einrichtung). GitHub
liefert nur das Framework (Code, Regeln, Konfigurationsvorgaben, Vorlagen, Tests, Doku). Nach dem
Deployment liest die App keine Daten aus dem GitHub-Repository und pusht nie Spielstand.

> **Portainer:** Betrieb ohne Kommandozeile: siehe [PORTAINER.md](PORTAINER.md).

## Aufbau

| Dienst | Aufgabe | Netz |
| --- | --- | --- |
| `proxy` | Caddy: HTTPS mit lokaler CA, Heimnetz-Schranke, Sicherheits-Header, liefert die React-App aus | `edge` (veröffentlicht), `app` |
| `api` | FastAPI: Anmeldung, Benutzer, Spiel-API, Einrichtung, Sicherung; legt beim Start das Datenverzeichnis an | `app`, `data` (intern, kein Internet) |
| `worker` | Hintergrunddienst: Kurse (tools/kurse.py), News (tools/news.py), Zeitplan, Claude-Sessions, Verbindungstests | `data`, `aus` (Internet) |
| `db` | PostgreSQL 16 mit Anwendungsrolle ohne Superuser-Rechte; erzeugt beim ersten Start die Passwörter | `data` (intern) |

| Pfad im Container | Volume | Inhalt |
| --- | --- | --- |
| `/app/framework` | – (im Image, nur lesend) | tools/, config/, regeln.md, CLAUDE.md, STATUS.md, Vorlagen |
| `/data` (`STOCKMASTER_DATA_DIR`) | `daten` | Spielstand mit eigenem lokalem Git ohne Remote |
| `/data-app` (`STOCKMASTER_APP_DIR`) | `app_daten` | einstellungen.json, geheimnisse.json, master.key, Lauf-Logs, Zustand, Sicherungen |
| `/geheim` | `geheim` | Datenbank-Passwörter (vom DB-Container erzeugt) |

Alle Container laufen mit `cap_drop: ALL`, `no-new-privileges`, Ressourcenlimits und Healthchecks;
`proxy`, `api` und `worker` zusätzlich mit schreibgeschütztem Dateisystem und als eigener Benutzer.

## Erster Start

```bash
cp .env.example .env          # nur SM_HOSTNAME prüfen; keine Geheimnisse
docker compose up -d --build
docker compose exec api python -m stockmaster admin-anlegen --email du@heimnetz.local --anzeigename "Admin"
```

Der letzte Befehl gibt **einmalig** ein Einmalpasswort aus und verweigert die Ausführung, sobald ein
Administrator existiert. Bei der ersten Anmeldung ist der Passwortwechsel Pflicht. Die Anmeldung braucht danach nur das Passwort; Zwei-Faktor (TOTP) richtet der Administrator im Konto ein und braucht ihn nur zum Anlegen neuer Benutzer.
Danach führt das Cockpit zur **Einrichtung** (Claude, Kursdaten, News, Zeitplan, Spielstart).

Beim ersten Start mit leeren Volumes erzeugt der Stack selbst: Datenbank-Passwörter (`/geheim`),
Master-Schlüssel (`/data-app/master.key`, 0600) und das Datenverzeichnis aus
`vorlagen/datenverzeichnis/` mit eigenem Git (`git -C /data log`).

Die Web-UI ist unter `https://<SM_HOSTNAME>` erreichbar (Name im Heimnetz auflösbar machen).

### Root-Zertifikat im Heimnetz

Caddy erzeugt eine eigene Zertifizierungsstelle. Das Root-Zertifikat einmal je Gerät installieren:
`https://<SM_HOSTNAME>/stockmaster-root.crt` (Browserwarnung beim ersten Aufruf bestätigen) oder
`docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt ./stockmaster-root.crt`.

- Windows: Doppelklick → Zertifikat installieren → „Vertrauenswürdige Stammzertifizierungsstellen“.
- macOS: Schlüsselbundverwaltung → System → Datei importieren → „Immer vertrauen“.
- Android: Einstellungen → Sicherheit → Verschlüsselung → CA-Zertifikat installieren.
- iOS: Datei öffnen → Profil installieren → Einstellungen → Allgemein → Info → Zertifikatsvertrauenseinstellungen.
- Linux/Firefox: Einstellungen → Zertifikate → Importieren.

## Erreichbarkeit

Standard ist **nur Heimnetz**: Caddy beantwortet Anfragen aus nicht-privaten Adressbereichen mit 403,
die API prüft dasselbe noch einmal (zweite Schranke). Am Router **keinen** Port freigeben. Für einen
VPN-Bereich (z. B. Tailscale `100.64.0.0/10`) diesen unter `SM_ZUSAETZLICHE_NETZE` ergänzen.

Der Proxy antwortet nur auf `SM_HOSTNAME`, `localhost` und die Einträge in `SM_ZUSAETZLICHE_HOSTS`
(weitere Namen oder IP-Adressen, durch Leerzeichen oder Komma getrennt, ohne Port). Ein Aufruf per
nicht eingetragener IP-Adresse zeigt nach der Zertifikatswarnung den Hinweis „Unbekannter Name oder unbekannte
Adresse in der URL“ (HTTP 421), ein nicht eingetragener Name scheitert mit `ERR_SSL_PROTOCOL_ERROR`. Abhilfe:
den Hostnamen verwenden (Hosts-Datei oder Router-DNS) oder die IP des Servers unter
`SM_ZUSAETZLICHE_HOSTS` eintragen. Die Angaben werden beim Start geprüft; ungültige verhindern den Start
des Proxys. Bei mehreren IP-Adressen enthält das Zertifikat für Aufrufe ohne Namen nur die erste.

Hinweis: Docker Desktop (macOS/Windows) übersetzt Quelladressen teilweise in die interne
Gateway-Adresse; dort ist die Heimnetz-Schranke nicht verlässlich. Für den Betrieb einen Linux-Rechner
(z. B. Mini-PC, NAS) nutzen.

## Umgebungsvariablen (minimal)

| Variable | Zweck |
| --- | --- |
| `SM_HOSTNAME` | Name im Heimnetz (Pflicht im Portainer-Stack) |
| `SM_ZUSAETZLICHE_HOSTS`, `SM_ZUSAETZLICHE_NETZE`, `SM_HTTPS_PORT`, `SM_HTTP_PORT`, `TZ` | optional |
| `STOCKMASTER_DATA_DIR`, `STOCKMASTER_APP_DIR`, `STOCKMASTER_FRAMEWORK_DIR` | im Image gesetzt (`/data`, `/data-app`, `/app/framework`) |

Entfallen: `SPIEL_REPO`, `POSTGRES_ADMIN_PASSWORD`, `POSTGRES_APP_PASSWORD`, `SM_SCHLUESSEL`
(`SM_SCHLUESSEL_DATEI`, `./secrets/`). Sind sie bei einem Update noch gesetzt, werden sie einmalig
übernommen (ebenso `CLAUDE_CODE_OAUTH_TOKEN`, `FINNHUB_API_KEY`, `TWELVEDATA_API_KEY`); die
Einrichtung zeigt dann, welche Variablen entfernt werden können. Danach gilt die App-Konfiguration.

## Einstellungen und Secrets

- **Speicherort:** `/data-app/einstellungen.json` (ohne Secrets) und `/data-app/geheimnisse.json`;
  getrennt vom Spielstand, nie im Spielstand-Git.
- **Verschlüsselung:** Jedes Secret einzeln mit AES-256-GCM; der Schlüssel wird per HKDF aus dem
  Master-Schlüssel `/data-app/master.key` abgeleitet (32 Byte, beim ersten Start zufällig erzeugt,
  Rechte 0600). Derselbe Master-Schlüssel verschlüsselt die Zwei-Faktor-Geheimnisse in der Datenbank.
- **Ausgabe:** Die API liefert Secrets nie zurück, nur „gesetzt“ und die letzten vier Zeichen. Ändern
  geht nur durch neues Eintragen; Audit-Einträge nennen nur, *dass* ein Secret geändert wurde.
- **Logs:** Session-Logs schwärzen alle hinterlegten Secrets und Token-Muster. Ein Git-Hook im
  Datenverzeichnis lehnt Commits ab, die ein Secret enthalten.
- **Was das schützt:** Sicherungs-Exporte, Datenbank-Dumps, Kopien der Einstellungen und versehentlich
  geteilte Dateien enthalten Secrets nur verschlüsselt bzw. gar nicht; der Master-Schlüssel ist nie Teil
  eines Exports.
- **Was das nicht schützt:** Wer Zugriff auf das Volume `app_daten` hat (Docker-Host, Portainer-Konsole,
  Backup des Volumes), hat Schlüssel und verschlüsselte Werte zusammen und kann sie entschlüsseln. Während
  eines Claude-Laufs steht das Token in der Umgebung dieses Prozesses (Claude Code braucht es dort). Den
  Docker-Host und Portainer deshalb wie einen Tresor behandeln.
- **Schlüssel verloren:** Secrets neu eintragen; Zwei-Faktor aller Benutzer zurücksetzen
  (Administration → Zwei-Faktor zurücksetzen).

## Datenverzeichnis und Prüfspur

`/data` ist ein eigenes Git-Repository ohne Remote. Sessions committen dort lokal
(`python tools/datenverzeichnis.py commit -m "session: ..."`), der Worker committet Kurs- und News-Abrufe
höchstens stündlich („daten: …“), nie während einer Session. `python tools/pruefe.py --historie` prüft
die Nur-Anhängen-Regeln über diese lokale Historie. Kein Code-Pfad pusht Spielstand.

## Kurse und News

- **Kurse:** Kette aus konfiguriertem Anbieter (Finnhub oder Twelve Data, Key in der Einrichtung) und
  yfinance; der Worker ruft alle 5 Minuten bei offenem Markt (Xetra, NYSE) ab, sonst stündlich, einmal
  nach Börsenschluss und täglich Tagesdaten. Liefert keine Quelle einen verlässlichen Kurs, zeigt „Markt &
  Kurse“ den letzten bekannten Kurs mit Kennzeichnung „veraltet“ – nur zur Anzeige, nie für Buchungen.
  Kontingente der Anbieter werden gezählt; ist eins erschöpft, übernimmt yfinance.
- **Beobachtungsliste:** `tools/beobachtung.py` holt Tageskerzen von rund 600 Aktien und ETFs
  (`config/beobachtung.json`, yfinance) und rechnet Kennzahlen für den Screener. Der Worker ruft sie je
  Handelstag ab 23:15 Uhr ab (bei fehlendem Stand sofort, bei Fehlern stündlich); der Stand liegt in
  `/data/.cache/beobachtung.json`. Anzeige: „Markt & Kurse“ → Beobachtungsliste. Von Hand, mit Netzwerk:
  `docker compose exec worker python /app/framework/tools/beobachtung.py aktualisieren`; Werte ohne Daten nennt
  derselbe Aufruf mit `pruefen`. Die Listen pflegen die Auftraggeber (Indexwechsel, Umbenennungen).
- **Nachbuchung:** Der Worker bucht jede Nacht ab 00:30 Uhr bis gestern nach (Sperre der Art `nachbuchung`,
  danach Bericht, Prüfung und lokaler Commit „session: Nachbuchung …“), damit vorgemerkte Orders nicht bis zur
  nächsten Session liegen. Status: Einrichtung → Systemstatus → „Nachbuchung“. Bei Fehlern wiederholt er
  stündlich; eine laufende Session oder ein laufender Lauf geht vor.
- **Ausführung ohne Claude-Lauf:** Der Worker ruft `tools/ausfuehrung.py tick` bei offenem Markt alle 5 Minuten
  sowie kurz nach Öffnung und kurz vor Schluss jeder Börse auf (nach Fehler oder fehlendem Kurs nach einer
  Minute erneut). Er führt vorgemerkte Orders, Limits, Stops, Kursziele und Knock-outs zu protokollierten Kursen aus,
  ohne Sprachmodell und ohne Token, unter der Buchungssperre (`/data/.buchungssperre`, unabhängig von
  `session.lock`). Status: Einrichtung → Systemstatus → „Ausführung“ (letzter Durchlauf, Warteschlange, Rückstand,
  Fehler). Protokoll: `data/ausfuehrung/JJJJ-MM-TT.jsonl`; Buchungen tragen „automatisch (Auslöser: …)“. Von Hand,
  mit Netzwerk: `docker compose exec worker python /app/framework/tools/ausfuehrung.py tick`; Termine eines
  Tages: `ausfuehrung.py ereignisse --tag JJJJ-MM-TT`. Steht die Nachbuchung aus, wartet die Ausführung.
- **News:** `tools/news.py` ruft die Feeds aus `config/news.json` und der Einrichtung alle 15 Minuten ab,
  dedupliziert und speichert nur Titel, Kurztext und Link in `news/` (nur anhängen).

## Anmeldung mit dem Claude-Abo

Einrichtung → Claude → *Mit Claude anmelden*: Der worker startet `claude setup-token` in einem
Pseudo-Terminal (eigenes, danach gelöschtes Home-Verzeichnis), liest den Anmeldelink aus und zeigt ihn
in der UI (nur Links auf Anthropic-Domains). Nach der Anmeldung im Browser zeigt platform.claude.com
einen Code; die UI gibt ihn über eine 0600-Datei im App-Verzeichnis an den wartenden Prozess weiter
(sofort gelöscht). Das ausgegebene Token wird direkt verschlüsselt gespeichert; Ausgaben des Befehls
werden nie geloggt oder gespeichert. Zeitfenster 10 Minuten; der Prozess muss so lange laufen, weil die
Anmeldung an ihn gebunden ist (PKCE). Der Ablauf liest die interaktive Ausgabe der CLI und ist gegen die
im Image feste Version geprüft; ändert sie sich, meldet die UI das und das manuelle Eintragen bleibt
möglich.

## Claude-Sessions

Der Worker startet Claude Code im Container (Arbeitsverzeichnis Framework, Datenverzeichnis per
`--add-dir`), mit Token, Modell (`--model`) und Aufwand (`--effort`) aus der Einrichtung. Er setzt eine
minimale Umgebung (kein `ANTHROPIC_API_KEY`), verwaltete Berechtigungen (keine Änderungen an
portfolios/, trades/, data/, Framework; kein Lesen von `/data-app`) und ein Zeitlimit. Das Log ist live
unter „Claude-Läufe“ zu sehen; danach gibt der Worker eine liegengebliebene Sperre frei, committet Reste
und führt `pruefe.py` aus. Modell und Aufwand stehen am Lauf, im Audit-Log und im Session-Eintrag.
Optionen für Modell und Aufwand: `config/claude.json` (gegen `claude --help` der installierten Version).

### Freigaben

Befehle, die weder auf der Positivliste noch unter den Verboten stehen (etwa eine Schleife mit `echo` und
`awk`), lehnt der Worker nicht mehr pauschal ab: Die CLI fragt, und ein Administrator entscheidet in der
Web-UI. Die Anfrage erscheint unter „Claude-Läufe“ im Lauf (Befehl, Beschreibung von Claude, Restzeit,
„Erlauben“ oder „Ablehnen“) und als Hinweis „n Freigaben offen“ in der Kopfzeile. Eine Freigabe gilt nur für
diesen einen Aufruf. Ohne Entscheidung gilt die Anfrage nach drei Minuten als abgelehnt
(`SM_FREIGABE_WARTEZEIT_SEKUNDEN`, Standard 180), damit Läufe nach Zeitplan nie hängen bleiben.

Nie freigebbar, auch nicht auf Wunsch: alles, was nicht erkennbar nur liest, vor allem Umleitungen in Dateien,
Befehlsersetzung, Pfade außerhalb von Spielstand und Framework und Umgebungsvariablen. Der Spielstand bleibt
für Claude schreibgeschützt. Alle Anfragen samt Ausgang stehen am Lauf; wer entschieden hat, steht im Audit-Log.
Nachsehen im Container `worker`: `grep -B1 "Freigabe" /data-app/laeufe/<Lauf-ID>.log`.

### Vorgaben je Portfolio

Einrichtung → „Vorgaben je Portfolio“: weicher Text der Auftraggeber an Claude, getrennt je Portfolio, nur
Administratoren ändern, alle Angemeldeten sehen ihn im Portfolio (Reiter Anlagerichtlinie). Jede Änderung ist
eine Version im Verlauf; sie liegt in `einstellungen.json` (also in der Sicherung, nicht im Spielstand) und gilt
ab dem nächsten gestarteten Trading-Lauf. Der Prompt stellt klar, dass die Vorgaben nachrangig zu regeln.md, den
Limits und den Prüfungen sind; das Lauf-Log nennt die verwendeten Versionen, der Audit-Eintrag
`einrichtung_vorgabe` die Änderung (ohne Text).

## Sicherung und Wiederherstellung

```bash
# Spielstand inklusive lokalem Git (ohne Secrets) und Einstellungen
docker compose exec api python -m stockmaster sicherung-export --datei /data-app/tmp/sicherung.tar.gz
docker compose cp api:/data-app/tmp/sicherung.tar.gz .
# mit Secrets (passwortverschlüsselt, Passwort aus SM_SICHERUNG_PASSWORT oder Abfrage)
docker compose exec -it api python -m stockmaster sicherung-export --datei /data-app/tmp/s.tar.gz --mit-geheimnissen
# Wiederherstellen (vorheriger Stand wird unter /data-app/sicherungen/ gesichert)
docker compose exec api python -m stockmaster sicherung-import --datei /data-app/tmp/sicherung.tar.gz

# Datenbank (Benutzer, Zwei-Faktor, Audit-Log, Läufe)
docker compose exec -T db pg_dump -U postgres -Fc stockmaster > stockmaster-$(date +%F).dump
docker compose exec -T db pg_restore -U postgres -d stockmaster --clean < stockmaster-JJJJ-MM-TT.dump
```

Die Web-UI bietet Export und Wiederherstellung unter Einrichtung → Sicherung (nur Admin,
Passwortbestätigung). Für eine vollständige Wiederherstellung inklusive Zwei-Faktor zusätzlich
`master.key` getrennt und sicher aufbewahren (`docker compose cp api:/data-app/master.key .`).

## Aktualisieren

```bash
git pull
docker compose up -d --build
```

Datenbank-Migrationen laufen beim Start automatisch; Volumes bleiben erhalten.

## Registry-Spiegel

Drosselt Docker Hub die Basis-Images (HTTP 429), in `.env` `REGISTRY=mirror.gcr.io/library` setzen.

## Entwicklung ohne Docker

```bash
# Demo-Datenverzeichnis (simulierte Kurse, eigenes lokales Git)
python3 webui/demo/demo_daten.py --ziel /tmp/stockmaster-demo --tage 100
export STOCKMASTER_DATA_DIR=/tmp/stockmaster-demo STOCKMASTER_APP_DIR=/tmp/stockmaster-app

# Backend
cd webui/backend && uv sync
SM_COOKIE_SICHER=false SM_ENTWICKLUNG=1 SM_DATENBANK_URL=sqlite:///./entwicklung.db uv run python -m stockmaster vorbereiten
SM_COOKIE_SICHER=false SM_ENTWICKLUNG=1 SM_DATENBANK_URL=sqlite:///./entwicklung.db uv run uvicorn stockmaster.main:app --reload
# Hintergrunddienst (optional, braucht Internet)
SM_DATENBANK_URL=sqlite:///./entwicklung.db uv run python -m stockmaster worker

# Frontend (zweites Terminal), Proxy auf 127.0.0.1:8000
cd webui/frontend && pnpm install && pnpm dev
```

Werkzeuge ohne Web-UI: `python tools/datenverzeichnis.py einrichten --ziel ~/stockmaster-daten`, dann
`export STOCKMASTER_DATA_DIR=~/stockmaster-daten` und z. B. `python tools/pruefe.py`.

## Tests

| Bereich | Befehl |
| --- | --- |
| Werkzeuge | `python -m pytest -q` (Wurzel) |
| Prüfskript | `python tools/datenverzeichnis.py einrichten --ziel /tmp/d && STOCKMASTER_DATA_DIR=/tmp/d python tools/pruefe.py --historie` |
| Backend | `cd webui/backend && uv run pytest -q` |
| Frontend | `cd webui/frontend && pnpm test` |
| E2E (Browser) | `cd webui/frontend && pnpm build && pnpm e2e` |
| Docker-Stack | `bash webui/deploy/rauchtest.sh` (startet mit leeren Volumes) |

Alle laufen auch in der GitHub Action.
