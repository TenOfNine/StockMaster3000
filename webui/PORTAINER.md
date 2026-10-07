# StockMaster mit Portainer betreiben

Der Stack `webui/deploy/portainer/stack.yml` ist für Portainer (Docker Standalone/Compose, kein Swarm)
gebaut und **autark**: Er braucht keine Dateien auf dem Host, keinen `build:`-Schritt, keine Docker
Secrets und kein Spiel-Repository. Spielstand, Kurse, News, Journal, Reviews und Sessions leben nur in
Volumes; Einstellungen und Secrets (Claude-Token, Kurs-API-Keys) pflegt ein Admin in der App unter
**Einrichtung**. GitHub liefert nur das Framework (Code, Regeln, Vorlagen) als Images; die App pusht nie
Spielstand nach GitHub.

| Dienst | Image | Aufgabe |
| --- | --- | --- |
| `proxy` | `ghcr.io/<besitzer>/stockmaster3000-proxy` | Caddy mit der Web-App, HTTPS, Heimnetz-Schranke |
| `api` | `ghcr.io/<besitzer>/stockmaster3000-api` | FastAPI-Backend (ohne Internetzugang) |
| `worker` | dasselbe api-Image | Hintergrunddienst: Kurse, News, Zeitplan, Claude-Sessions, Verbindungstests |
| `db` | `ghcr.io/<besitzer>/stockmaster3000-db` | PostgreSQL 16 (Benutzer, Sitzungen, Audit-Log, Läufe) |

| Volume | Inhalt |
| --- | --- |
| `stockmaster_daten` → `/data` | Spielstand mit eigenem, lokalem Git (Prüfspur, ohne Remote) |
| `stockmaster_app_daten` → `/data-app` | App-Konfiguration, verschlüsselte Secrets, Master-Schlüssel (0600), Lauf-Logs |
| `stockmaster_geheim` → `/geheim` | vom DB-Container erzeugte Datenbank-Passwörter |
| `stockmaster_pgdata` | Datenbank |
| `stockmaster_caddy_data`, `_config` | lokale Zertifizierungsstelle und Zertifikate |

## 1. Images bereitstellen

Die Action *Images* veröffentlicht bei jeder Änderung auf `main` (Tags `latest` und `sha-<kurz>`).
Beim ersten Mal die Action manuell starten (Actions → Images → Run workflow).

**Privates Repository:** Die Pakete sind dann ebenfalls privat. In GitHub ein Token mit
`read:packages` anlegen und in Portainer → Registries → *Custom registry* (`ghcr.io`, GitHub-Benutzer,
Token) eintragen. Alternativ die Pakete auf „Public“ stellen: Die Images enthalten keine Geheimnisse
und keinen Spielstand.

## 2. Stack anlegen

Portainer → Stacks → Add stack → Name `stockmaster`, dann:

**Repository (empfohlen):** URL `https://github.com/<besitzer>/StockMaster3000`, Reference
`refs/heads/main`, Compose path `webui/deploy/portainer/stack.yml`. Oder **Web editor** mit dem Inhalt
der Datei.

**Environment variables** – minimal ist genau eine:

| Variable | Wert |
| --- | --- |
| `SM_HOSTNAME` | Name im Heimnetz, z. B. `stockmaster.local` (Pflicht) |
| `SM_ZUSAETZLICHE_HOSTS` | optional: weitere Namen oder IP-Adressen, z. B. `192.168.2.187` |
| `SM_HTTPS_PORT`, `SM_HTTP_PORT` | optional, Standard 443 und 80 |
| `SM_ZUSAETZLICHE_NETZE` | optional, z. B. ein VPN-Bereich |
| `TZ` | optional, Standard `Europe/Berlin` |
| `SM_IMAGE_PREFIX`, `SM_IMAGE_TAG` | nur bei abweichender Registry bzw. festem Stand |

*Deploy the stack*. Beim ersten Start mit leeren Volumes richtet sich der Stack selbst ein:

- `db` erzeugt zufällige Datenbank-Passwörter im Volume `geheim` (Log: `db-abgleich: … neu erzeugt`),
- `api` legt das Datenverzeichnis aus der Vorlage an (eigenes Git, erster Commit „aufbau: Datenverzeichnis
  aus Vorlage angelegt“), erzeugt den Master-Schlüssel (`/data-app/master.key`, Rechte 0600) und
  installiert einen Git-Hook, der Commits mit Secrets ablehnt,
- `worker` meldet sich per Herzschlag und beginnt mit Kurs- und News-Abrufen.

## 3. Ersten Administrator anlegen

Portainer → Containers → `stockmaster-api-1` → **Console** → `/bin/sh` → *Connect*:

```sh
python -m stockmaster admin-anlegen --email du@heimnetz.local --anzeigename "Admin"
```

Das Einmalpasswort steht nur in dieser Ausgabe; der Befehl funktioniert genau einmal. Danach unter
`https://<SM_HOSTNAME>` anmelden; Passwortwechsel und Zwei-Faktor sind Pflicht. (Ein Erststart-Assistent
über Variablen ist nicht nötig: Der erste Admin wird nicht über Umgebungsvariablen angelegt.)

## 4. In der App einrichten

Cockpit → Hinweis „Einrichtung noch nicht abgeschlossen“ → führt direkt zum ersten offenen Schritt:

1. **Claude:** *Mit Claude anmelden* → Link öffnen (geht auf jedem Gerät, z. B. am Handy), mit dem Konto
   des Claude-Abos anmelden, den angezeigten Code einfügen, *Verbinden*. Der Container führt dafür selbst
   `claude setup-token` aus und speichert das Token verschlüsselt; danach läuft automatisch der
   Verbindungstest. Alternativ das Token auf einem eigenen Rechner erzeugen und unter „Oder Token manuell
   eintragen“ einfügen. Dann Modell und Aufwand für „Trading-Session“ und „Review/Bericht“ wählen.
2. **Kursdaten:** Anbieter wählen (nur yfinance, Finnhub oder Twelve Data), ggf. API-Key eintragen,
   *Verbindung testen*, *Jetzt abrufen*. „Markt & Kurse“ füllt sich.
3. **News:** Feeds an- oder abschalten, eigene Feeds ergänzen, *Feed testen*.
4. **Sessions & Zeitplan:** Automatik und Zeiten, z. B. werktags 09:35 und 21:30.
5. **Anlagerichtlinien:** Claude-Läufe → *Lauf starten* → „Anlagerichtlinien ausformulieren (AP12)“. Der
   Lauf schreibt strategie/<profil>.md aus; Trading-Läufe sind erst danach (und erst ab dem Startdatum)
   möglich. Vorher bietet sich die Testsession an (Art „Testsession ohne Trades“).
6. **Spielstart:** nach der Freigabe (AP12) einmalig, mit Bestätigung.
7. **Sicherung** und 8. **Systemstatus** (Ampel je Bereich).

## Update einer bestehenden Installation (Migration)

Ältere Stacks hatten `SPIEL_REPO`, `POSTGRES_ADMIN_PASSWORD`, `POSTGRES_APP_PASSWORD` und `SM_SCHLUESSEL`.

1. Auf GitHub warten, bis *Actions → Images* für den neuen Stand grün ist.
2. In Portainer den Stack aktualisieren (*Pull and redeploy* bzw. neuen Inhalt im Web editor), dabei die
   **alten Variablen zunächst stehen lassen**. Sie werden beim ersten Start einmalig übernommen:
   - `POSTGRES_*` → Dateien im Volume `geheim` (Log `db-abgleich: … aus der Umgebungsvariable übernommen`),
   - `SM_SCHLUESSEL` → `/data-app/master.key` (gespeicherte Zwei-Faktor-Geheimnisse bleiben gültig),
   - ein gesetztes `CLAUDE_CODE_OAUTH_TOKEN`, `FINNHUB_API_KEY` oder `TWELVEDATA_API_KEY` → verschlüsselt in
     die App-Konfiguration.
3. Einrichtung öffnen: Der Hinweis „Aus dem Stack entfernbar“ nennt die übernommenen Variablen. Diese
   und `SPIEL_REPO` aus dem Stack löschen und erneut deployen. Ab jetzt gilt die App-Konfiguration.
4. **Spielstand übernehmen** (nur falls im alten Spiel-Repository schon gespielt wurde; vor dem Spielstart
   ist nichts zu tun): den alten Ordner einmalig in den Container `api` einbinden (Stack → Volume
   `/srv/stockmaster/spiel-repo:/alt:ro` ergänzen, deployen) und in der Console ausführen:

   ```sh
   python /app/framework/tools/migriere.py --von /alt
   ```

   Das funktioniert nur in ein leeres bzw. frisch angelegtes Datenverzeichnis. Der erste Commit trägt
   einen Herkunftsvermerk (Ordner und Commit der alten Arbeitskopie). Danach die Einbindung wieder
   entfernen.

> **Wichtig:** `SM_SCHLUESSEL` nicht entfernen, bevor die API einmal mit dem neuen Image gestartet ist.
> Gibt es schon Zwei-Faktor-Geheimnisse, aber weder Schlüsseldatei noch Variable, verweigert die API den
> Start mit einer Erklärung, statt einen neuen Schlüssel zu erzeugen.

## Aktualisieren

Portainer → Stacks → `stockmaster` → **Pull and redeploy**. Die Images werden bei jedem Deploy neu
gezogen (`pull_policy: always`); Volumes und damit Spielstand, Einstellungen und Datenbank bleiben.
Die erste Logzeile der API lautet `StockMaster API, Version <Commit>`.

## Sicherung

In der App: Einrichtung → Sicherung → *Export herunterladen* (tar.gz mit Spielstand und lokalem Git,
ohne Secrets). Mit Secrets nur nach ausdrücklicher Bestätigung und einem eigenen Sicherungspasswort.
Wiederherstellen ebenda (Passwortbestätigung; der vorherige Stand wird automatisch im App-Verzeichnis
gesichert). Per Console:

```sh
python -m stockmaster sicherung-export --datei /data-app/tmp/sicherung.tar.gz
python -m stockmaster sicherung-import --datei /data-app/tmp/sicherung.tar.gz
```

Die Datenbank (Benutzer, Zwei-Faktor, Audit-Log) zusätzlich mit `pg_dump` sichern (BETRIEB.md).

## Hinweise zur Absicherung

- Wer Portainer bedienen darf, kann in die Volumes schauen (auch in `/data-app`). Zwei-Faktor für
  Portainer aktivieren und Portainer nicht ins Internet stellen.
- Nur der `proxy` veröffentlicht Ports. `api` und `db` liegen in internen Netzen ohne Internet; nur der
  `worker` darf nach außen (Kursanbieter, Feeds, Claude).
- Alle Container laufen mit `cap_drop: ALL`, `no-new-privileges`, Ressourcenlimits; `proxy`, `api` und
  `worker` zusätzlich mit schreibgeschütztem Dateisystem.

## Fehlersuche

| Symptom | Ursache und Abhilfe |
| --- | --- |
| `required variable SM_HOSTNAME is missing` | `SM_HOSTNAME` in den Stack-Variablen setzen. |
| `pull access denied` / `manifest unknown` | Registry-Zugang fehlt (Schritt 1) oder Images noch nicht veröffentlicht. |
| API-Log: `Konfigurationsfehler: Es gibt gespeicherte Zwei-Faktor-Geheimnisse, aber keinen Master-Schlüssel` | Update ohne `SM_SCHLUESSEL`: den bisherigen Wert einmalig wieder setzen und deployen. |
| API-Log: `Anmeldung an der Datenbank abgelehnt` | Container `db` neu starten (gleicht die Passwörter aus dem Volume `geheim` ab, Log `db-abgleich`). |
| Systemstatus „Hintergrunddienst“ rot | Container `stockmaster-worker-1` läuft nicht oder ist unhealthy; dessen Log ansehen. |
| „Markt & Kurse“ zeigt „veraltet“ | Keine Quelle lieferte einen aktuellen Kurs; der Grund steht beim Wert. Einrichtung → Kursdaten → *Verbindung testen*. |
| Claude-Test: „Token ungültig oder abgelaufen“ | Einrichtung → Claude → *Neu anmelden* (oder Token manuell neu erzeugen und eintragen). |
| Anmeldung: „Der Code wurde abgelehnt“ | Code abgelaufen, schon benutzt oder unvollständig kopiert; *Neu starten* und den neuen Link verwenden. |
| Anmeldung: „Claude Code hat keinen Anmeldelink ausgegeben“ | Das Ausgabeformat der CLI hat sich geändert; Token manuell erzeugen und eintragen, Fehler melden. |
| Start eines Trading-Laufs: „Anlagerichtlinien fehlen“ oder „Das Spiel beginnt erst am …“ | Zuerst den Lauf „Anlagerichtlinien ausformulieren“ ausführen bzw. das Startdatum abwarten (regeln.md 2 und 11). |
| Lauf endet mit „Kontingent erschöpft“ | Das Pro-Abo-Kontingent ist aufgebraucht; nach dem Zurücksetzen erneut starten. |
| Browser: 421 oder `ERR_SSL_PROTOCOL_ERROR` | Name bzw. IP ist dem Proxy unbekannt: `SM_HOSTNAME` verwenden oder in `SM_ZUSAETZLICHE_HOSTS` eintragen. |
| „Zugriff nur aus dem Heimnetz“ | Anfrage nicht aus privatem Adressbereich: Bereich in `SM_ZUSAETZLICHE_NETZE` eintragen. |
