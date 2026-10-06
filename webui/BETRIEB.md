# Web-UI: Betrieb

Stufe 1 der Web-UI aus AUFTRAG_WEBUI.md: **lesend**. Sie zeigt das
Spiel-Repository (Portfolios, Kennzahlen, Trade-Akten, Sessions, Reviews,
Regeln, Status, Git-Historie) und führt nur lesende Werkzeuge aus
(`tools/pruefe.py`, Zertifikatsrechner). Orders und Claude-Läufe gibt es in
Stufe 1 nicht; Sessions laufen weiter über Claude Code.

> **Portainer:** Betrieb ohne Kommandozeile und ohne lokale Dateien: siehe [PORTAINER.md](PORTAINER.md).

## Aufbau

| Dienst | Aufgabe | Netz |
| --- | --- | --- |
| `proxy` | Caddy: HTTPS mit lokaler CA, Heimnetz-Schranke, Sicherheits-Header, liefert die React-App aus | `edge` (veröffentlicht), `app` |
| `api` | FastAPI: Anmeldung, Sitzungen, Benutzer, lesende Spiel-API; bindet das Spiel-Repository **nur lesend** ein | `app`, `data` (beide intern) |
| `db` | PostgreSQL 16 mit eigener Anwendungsrolle ohne Superuser-Rechte | `data` (intern) |

Nur der Proxy veröffentlicht Ports. Alle Container laufen mit
`cap_drop: ALL`, `no-new-privileges`, Ressourcenlimits und Healthchecks;
`proxy` und `api` zusätzlich mit schreibgeschütztem Dateisystem und als
eigener Benutzer. Geheimnisse liegen nur als Docker Secrets in `./secrets/`
(nie im Image, nie im Repository).

## Erster Start

Voraussetzungen: Docker mit Compose v2, `openssl`, `python3` (nur für den
Rauchtest bzw. Demo-Daten).

```bash
bash webui/deploy/einrichten.sh     # erzeugt ./secrets/* und .env
nano .env                           # SM_HOSTNAME und SPIEL_REPO prüfen
docker compose up -d --build
docker compose exec api python -m stockmaster admin-anlegen --email du@heimnetz.local --anzeigename "Dein Name"
```

Der letzte Befehl gibt **einmalig** ein Einmalpasswort aus. Er verweigert
die Ausführung, sobald ein Administrator existiert. Bei der ersten Anmeldung
sind Passwortwechsel und Zwei-Faktor (TOTP, z. B. Aegis, 2FAS, Google
Authenticator) Pflicht. Weitere Benutzer legt der Administrator in der UI an
(Administration → Benutzer anlegen); auch sie erhalten ein Einmalpasswort.

Die Web-UI ist danach unter `https://<SM_HOSTNAME>` erreichbar. Der Name
muss im Heimnetz auflösbar sein (Router-DNS oder `/etc/hosts`, z. B.
`192.168.1.20 stockmaster.local`).

### Root-Zertifikat im Heimnetz

Caddy erzeugt eine eigene Zertifizierungsstelle. Damit Browser der
Verbindung vertrauen, das Root-Zertifikat einmal auf jedem Gerät
installieren:

Im Heimnetz direkt im Browser: `https://<SM_HOSTNAME>/stockmaster-root.crt` (Browserwarnung beim
ersten Aufruf einmalig bestätigen). Alternativ per Kommandozeile:

```bash
docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt ./stockmaster-root.crt
```

- Windows: Doppelklick → Zertifikat installieren → „Vertrauenswürdige Stammzertifizierungsstellen“.
- macOS: Schlüsselbundverwaltung → System → Datei importieren → „Immer vertrauen“.
- Android: Einstellungen → Sicherheit → Verschlüsselung → CA-Zertifikat installieren.
- iOS: Datei öffnen → Profil installieren → Einstellungen → Allgemein → Info → Zertifikatsvertrauenseinstellungen.
- Linux/Firefox: Einstellungen → Zertifikate → Importieren.

## Erreichbarkeit

Standard ist **nur Heimnetz**: Caddy beantwortet Anfragen aus
nicht-privaten Adressbereichen mit 403, die API prüft dasselbe noch einmal
(zweite Schranke). Am Router **keinen** Port freigeben. Für einen VPN-Bereich
(z. B. Tailscale `100.64.0.0/10`) diesen in `.env` unter
`SM_ZUSAETZLICHE_NETZE` ergänzen. Zugriff aus dem Internet ist nicht Teil
von Stufe 1 (W17).

Hinweis: Docker Desktop (macOS/Windows) übersetzt Quelladressen teilweise in
die interne Gateway-Adresse; dort ist die Heimnetz-Schranke von Caddy nicht
verlässlich. Für den Betrieb einen Linux-Rechner (z. B. Mini-PC, NAS) nutzen.

## Spiel-Repository

`SPIEL_REPO` in `.env` zeigt auf das Repository, in dem Claude Code die
Sessions ausführt (Standard: dieses Verzeichnis). Es wird nur lesend
eingebunden; die UI zeigt immer den aktuellen Stand der Dateien. Nach einem
`git pull` im Spiel-Repository ist nichts weiter zu tun. Ändern sich die
Werkzeuge in `tools/`, die API neu starten: `docker compose restart api`.

## Aktualisieren

```bash
git pull
docker compose up -d --build
```

Datenbank-Migrationen laufen beim Start des API-Containers automatisch.

## Sicherung und Wiederherstellung

Spieldaten liegen im Git-Repository (dort sichern bzw. pushen). Die
Datenbank enthält nur Benutzer, Sitzungen und das Audit-Log.

```bash
# Sicherung
docker compose exec -T db pg_dump -U postgres -Fc stockmaster > stockmaster-$(date +%F).dump
cp -r secrets secrets-sicherung-$(date +%F)     # sicher und getrennt aufbewahren

# Wiederherstellung
docker compose exec -T db pg_restore -U postgres -d stockmaster --clean < stockmaster-JJJJ-MM-TT.dump
```

## Schlüssel und Passwörter

- `secrets/sm_schluessel` verschlüsselt die TOTP-Geheimnisse (AES-256-GCM).
  Geht er verloren, müssen alle Benutzer Zwei-Faktor neu einrichten
  (Administration → Zwei-Faktor zurücksetzen). Eine automatische Rotation
  folgt mit Stufe 2.
- Datenbankpasswörter ändern: neue Werte in `secrets/` schreiben, in der
  Datenbank `ALTER ROLE ... PASSWORD ...` ausführen, `docker compose up -d`.
- Ausgesperrter Administrator: zweiter Admin setzt Passwort bzw. Zwei-Faktor
  zurück. Gibt es keinen: Konto in der Datenbank löschen und
  `admin-anlegen` erneut ausführen.

## Registry-Spiegel

Drosselt Docker Hub die Basis-Images (HTTP 429), in `.env`
`REGISTRY=mirror.gcr.io/library` setzen. Die Images sind per Digest
gepinnt; der Spiegel liefert dieselben Inhalte.

## Entwicklung ohne Docker

```bash
# Demo-Daten (simulierte Kurse, eigenes Git-Repository)
python3 webui/demo/demo_daten.py --ziel /tmp/stockmaster-demo --tage 100

# Backend
cd webui/backend && uv sync
SM_REPO_PFAD=/tmp/stockmaster-demo SM_COOKIE_SICHER=false SM_ENTWICKLUNG=1 \
  SM_DATENBANK_URL=sqlite:///./entwicklung.db uv run python -m stockmaster migrieren
SM_REPO_PFAD=/tmp/stockmaster-demo SM_COOKIE_SICHER=false SM_ENTWICKLUNG=1 \
  SM_DATENBANK_URL=sqlite:///./entwicklung.db uv run uvicorn stockmaster.main:app --reload

# Frontend (zweites Terminal), Proxy auf 127.0.0.1:8000
cd webui/frontend && pnpm install && pnpm dev
```

`SM_ENTWICKLUNG=1` erlaubt einen festen Entwicklungsschlüssel und ist nur
für die lokale Entwicklung gedacht.

## Tests

| Bereich | Befehl |
| --- | --- |
| Werkzeuge | `python -m pytest -q` (Wurzel) |
| Backend | `cd webui/backend && uv run pytest -q` |
| Frontend | `cd webui/frontend && pnpm test` |
| E2E (Browser) | `cd webui/frontend && pnpm build && pnpm e2e` |
| Docker-Stack | `bash webui/deploy/rauchtest.sh` |

Alle laufen auch in der GitHub Action.
