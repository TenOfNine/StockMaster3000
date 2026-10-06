# Web-UI mit Portainer betreiben

Der Stack `webui/deploy/portainer/stack.yml` ist für Portainer (Docker Standalone/Compose, kein
Swarm) gebaut: Er braucht **keine Dateien auf dem Host außer dem Spiel-Repository**, keinen
`build:`-Schritt und keine Docker Secrets. Die Images baut die GitHub Action
(`.github/workflows/images.yml`) und legt sie in der GitHub Container Registry ab; Geheimnisse
stehen als Umgebungsvariablen im Stack.

| Image | Inhalt |
| --- | --- |
| `ghcr.io/<besitzer>/stockmaster3000-proxy` | Caddy mit der gebauten Web-App |
| `ghcr.io/<besitzer>/stockmaster3000-api` | FastAPI-Backend |
| `ghcr.io/<besitzer>/stockmaster3000-db` | PostgreSQL 16 mit eingebautem Init-Skript |

## 1. Images bereitstellen

Die Action veröffentlicht bei jeder Änderung an `webui/` auf `main` (Tags `latest` und
`sha-<kurz>`). Beim ersten Mal die Action manuell starten (Actions → Images → Run workflow), falls
noch kein Push auf `main` stattfand.

**Privates Repository:** Die Pakete sind dann ebenfalls privat. Portainer braucht Zugangsdaten:

1. GitHub → Settings → Developer settings → Personal access tokens → Token mit Recht
   `read:packages` anlegen.
2. Portainer → Registries → Add registry → *Custom registry*: URL `ghcr.io`, Benutzername =
   GitHub-Benutzer, Passwort = Token.

Alternativ die Pakete unter GitHub → Packages → *Package settings* auf „Public“ stellen (die
Images enthalten keine Geheimnisse und keine Spieldaten).

## 2. Spiel-Repository auf dem Docker-Host

Das Repository, in dem die Sessions laufen, muss auf dem Docker-Host liegen, z. B.:

```bash
git clone https://github.com/<besitzer>/StockMaster3000 /srv/stockmaster/spiel-repo
```

Der Stack bindet den Ordner **nur lesend** ein. Nach einem `git pull` im Ordner ist die Web-UI
sofort aktuell (Änderungen an `tools/` erfordern einen Neustart des Containers `api`).

## 3. Stack anlegen

Portainer → Stacks → Add stack → Name `stockmaster`, dann eine der beiden Methoden:

**Web editor:** Inhalt von `webui/deploy/portainer/stack.yml` einfügen.

**Repository (empfohlen, Updates per Knopfdruck):** Repository URL `https://github.com/<besitzer>/StockMaster3000`,
Reference `refs/heads/main`, Compose path `webui/deploy/portainer/stack.yml`
(bei privatem Repository „Authentication“ mit Token aktivieren). Optional „GitOps updates“.

**Environment variables** (Abschnitt „Advanced mode“ → Inhalt von
`webui/deploy/portainer/stack.env.example` einfügen und ausfüllen):

| Variable | Wert |
| --- | --- |
| `SM_HOSTNAME` | Name im Heimnetz, z. B. `stockmaster.local` |
| `SPIEL_REPO` | absoluter Pfad aus Schritt 2 |
| `POSTGRES_ADMIN_PASSWORD` | beliebiges langes Passwort, z. B. `openssl rand -base64 24` |
| `POSTGRES_APP_PASSWORD` | beliebiges langes Passwort (anderer Wert als der Admin-Wert); Sonderzeichen sind erlaubt |
| `SM_SCHLUESSEL` | `openssl rand -base64 32`, genau so einfügen: 44 Zeichen, das letzte ist ein `=`, ohne Anführungszeichen und Leerzeichen |
| `SM_ZUSAETZLICHE_HOSTS` | optional: weitere Namen oder IP-Adressen, unter denen die Web-UI antwortet (Leerzeichen oder Komma, ohne Port), z. B. die IP des Servers: `192.168.2.187` |
| `SM_IMAGE_PREFIX` | nur bei abweichendem Registry-Pfad, Standard `ghcr.io/tenofnine/stockmaster3000` |

Fehlt eine Pflicht-Variable, verweigert der Stack den Start mit einer klaren Meldung. Auch die Werte
selbst werden beim Start geprüft: Ist `SM_SCHLUESSEL` ungültig, startet die API nicht und nennt den Grund
im Log (Fehlersuche unten); ungültige Angaben in `SM_HOSTNAME` oder `SM_ZUSAETZLICHE_HOSTS` verhindern den
Start des Proxys.
Anschließend *Deploy the stack*. Ports 80/443 sind frei zu halten (sonst `SM_HTTP_PORT` und
`SM_HTTPS_PORT` anpassen, z. B. 8080 und 8443, wenn Portainer oder ein anderer Proxy sie belegt).

> **Schlüssel sichern:** `SM_SCHLUESSEL` verschlüsselt die Zwei-Faktor-Geheimnisse. Wert und
> Datenbank-Volume `stockmaster_pgdata` getrennt sichern (siehe BETRIEB.md, Sicherung).

## 4. Ersten Administrator anlegen

Portainer → Containers → `stockmaster-api-1` → **Console** → Command `/bin/sh` → *Connect*:

```sh
python -m stockmaster admin-anlegen --email du@heimnetz.local --anzeigename "Dein Name"
```

Das Einmalpasswort steht nur in dieser Ausgabe. Der Befehl funktioniert genau einmal. Danach unter
`https://<SM_HOSTNAME>` anmelden; Passwortwechsel und Zwei-Faktor sind Pflicht.

### Aufruf per IP-Adresse

Der Proxy antwortet nur auf die Namen, die er kennt: `SM_HOSTNAME`, `localhost` und die Einträge in
`SM_ZUSAETZLICHE_HOSTS`. Ein Aufruf per nicht eingetragener IP-Adresse (`https://192.168.2.187`) zeigt nach der
Zertifikatswarnung den Hinweis „Unbekannter Name oder unbekannte Adresse in der URL“ (HTTP 421). Ein nicht
eingetragener **Name** scheitert schon im TLS-Handshake (`ERR_SSL_PROTOCOL_ERROR`). Zwei Wege:

1. **Hostnamen verwenden (empfohlen):** Eintrag im Router-DNS oder in der Hosts-Datei des Geräts
   (Windows: `C:\Windows\System32\drivers\etc\hosts`, als Administrator): `192.168.2.187  stockmaster.local`.
2. **IP eintragen:** `SM_ZUSAETZLICHE_HOSTS=192.168.2.187` setzen und den Stack neu deployen. Die IP muss dann
   fest bleiben (DHCP-Reservierung im Router). Bei mehreren IP-Adressen enthält das Zertifikat für Aufrufe ohne
   Namen nur die erste; die übrigen funktionieren nach Bestätigen der Browserwarnung. Die Heimnetz-Schranke
   gilt unverändert auch für diese Adressen.

## 5. Zertifikat im Heimnetz

Die Web-UI nutzt HTTPS mit einer lokalen Zertifizierungsstelle. Im Heimnetz ist das Root-Zertifikat
direkt abrufbar:

```
https://<SM_HOSTNAME>/stockmaster-root.crt
```

(beim ersten Aufruf die Browserwarnung einmalig bestätigen, Datei laden und wie in BETRIEB.md
beschrieben installieren). Es ist das öffentliche Zertifikat; der private Schlüssel verlässt den
Container nie. Der Download ist wie alles andere nur aus privaten Adressbereichen erreichbar.

## Passwörter ändern

`POSTGRES_ADMIN_PASSWORD` und `POSTGRES_APP_PASSWORD` können in den Stack-Variablen geändert werden;
beim Neustart des Containers `db` werden sie in der Datenbank übernommen, das Volume muss nicht
gelöscht werden. Den Stack danach mit *Update the stack* erneut deployen.

## Aktualisieren

1. Auf GitHub unter *Actions → Images* warten, bis der Lauf für den neuesten Commit auf `main` grün ist.
2. Portainer → Stacks → `stockmaster` → **Pull and redeploy** (Repository-Methode) bzw. **Update the
   stack** (Web editor).

Der Stack zieht bei jedem Deploy die Images neu (`pull_policy: always`); ein Schalter „Re-pull image“
ist nicht mehr nötig. Datenbank-Migrationen laufen beim Start der API automatisch, das
Datenbank-Volume bleibt erhalten.

**Prüfen, welche Version läuft:** Portainer → Containers → `stockmaster-api-1` → Logs. Die erste Zeile
lautet `StockMaster API, Version <Commit>`. Fehlt sie, läuft noch ein altes Image: Stack stoppen, unter
*Images* die drei `stockmaster3000-*`-Images löschen und den Stack erneut deployen.

## Hinweise zur Absicherung in Portainer

- Der Zugriff auf Portainer selbst gehört zur Sicherheit des Systems: Zwei-Faktor für Portainer
  aktivieren und Portainer nicht ins Internet stellen. Wer Portainer bedienen darf, kann die
  Umgebungsvariablen (Schlüssel, Passwörter) sehen.
- Die Container laufen mit `cap_drop: ALL`, `no-new-privileges`, schreibgeschütztem Dateisystem
  (Proxy, API), Ressourcenlimits und internen Netzen; nur der Proxy veröffentlicht Ports.
- Portainer-Rollen: Benutzer, die nur ansehen sollen, brauchen in Portainer keinen Zugriff auf
  diese Umgebung.
- Docker Desktop (Windows/macOS) verändert Quelladressen; für die Heimnetz-Schranke einen
  Linux-Host verwenden.

## Fehlersuche

| Symptom | Ursache und Abhilfe |
| --- | --- |
| `required variable … is missing` | Pflicht-Variable fehlt in den Stack-Umgebungsvariablen. |
| `pull access denied` / `unauthorized` / `manifest unknown` | Registry-Zugang in Portainer fehlt (Schritt 1) oder Images noch nicht veröffentlicht. |
| API startet ständig neu, Log: `Konfigurationsfehler: SM_SCHLUESSEL …` | Der Schlüssel fehlt, ist unvollständig oder hat nicht genau 32 Byte. Häufig fehlt beim Kopieren das `=` am Ende oder es wurde der Wert aus der Zeile `-base64 24` genommen. Neu erzeugen mit `openssl rand -base64 32`, vollständig in `SM_SCHLUESSEL` eintragen und den Stack neu deployen. Solange noch kein Zwei-Faktor eingerichtet ist, darf der Schlüssel frei ersetzt werden; danach müssen alle ihren Zwei-Faktor neu einrichten (Administration → Zwei-Faktor zurücksetzen). Ein nur leicht fehlerhafter Wert (fehlendes `=`, Anführungszeichen, Leerraum) wird automatisch korrigiert; das Log warnt dann mit „wurde korrigiert“. |
| Proxy startet ständig neu, Log: `Konfigurationsfehler: SM_HOSTNAME` bzw. `SM_ZUSAETZLICHE_HOSTS` | Ungültige Angabe: erlaubt sind Namen und IP-Adressen ohne Port, Platzhalter und Sonderzeichen, getrennt durch Leerzeichen oder Komma. Das Log nennt die beanstandete Angabe. |
| Browser: Hinweis „Unbekannter Name oder unbekannte Adresse in der URL“ (421) oder `ERR_SSL_PROTOCOL_ERROR` | Name oder IP-Adresse sind dem Proxy nicht bekannt: Hostnamen aus `SM_HOSTNAME` verwenden oder die IP bzw. den Namen in `SM_ZUSAETZLICHE_HOSTS` eintragen (siehe „Aufruf per IP-Adresse“). |
| Container `stockmaster-api-1` ist `unhealthy` | Der Health-Check prüft Schlüssel und Datenbank. Das Log nennt die Ursache (`Health-Check fehlgeschlagen: …`). |
| API startet ständig neu (`restarting`) | Log des Containers ansehen (Portainer → Containers → `stockmaster-api-1` → Logs). Die API wartet bis zu 2 Minuten auf die Datenbank und nennt dort den Grund. Bei „Anmeldung an der Datenbank abgelehnt“: Container `db` neu starten (er gleicht die Passwörter bei jedem Start ab, Log-Zeile `db-abgleich: Passwörter und Anwendungsrolle abgeglichen`). Fehlt diese Zeile oder steht dort `FEHLER`, das `db`-Log schicken. |
| `db`-Log: `role "stockmaster" does not exist` | Die Anwendungsrolle fehlt (z. B. nach einem abgebrochenen ersten Start). Das `db`-Image legt sie beim nächsten Start selbst an; den Stack neu deployen. Das Volume muss nicht gelöscht werden. |
| API-Log: `Permission denied: /repo/...` | Dateien im Spiel-Repository sind für andere Benutzer nicht lesbar: `chmod -R a+rX /srv/stockmaster/spiel-repo`. |
| Seite zeigt „Zugriff nur aus dem Heimnetz“ | Anfrage kommt nicht aus einem privaten Adressbereich (z. B. VPN): Bereich in `SM_ZUSAETZLICHE_NETZE` eintragen. |
| Leere Ansicht „kein Commit“ / Git-Historie fehlt | Der Ordner `SPIEL_REPO` ist kein Git-Repository oder `.git` ist nicht lesbar. |
