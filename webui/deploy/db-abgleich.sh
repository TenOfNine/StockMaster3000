#!/bin/sh
# Wrapper um den Standard-Entrypoint von PostgreSQL.
#
# 1. Passwörter: Beim ersten Start erzeugt der Container zufällige Passwörter im Volume /geheim
#    (db_admin_passwort nur für postgres lesbar, db_app_passwort zusätzlich für die API). Sind noch
#    POSTGRES_PASSWORD bzw. POSTGRES_APP_PASSWORD gesetzt (Installationen vor der App-Konfiguration),
#    werden sie einmalig übernommen. Danach gelten die Dateien; die Variablen können entfallen.
# 2. Abgleich: Bei JEDEM Start werden die Rollen auf diese Passwörter gesetzt und die Anwendungsrolle
#    und -datenbank angelegt, falls sie fehlen (PostgreSQL wertet die Variablen nur beim ersten Start aus).
set -eu
GEHEIM=/geheim

passwort_datei() {
  # $1 Datei, $2 Wert aus der Umgebung (optional), $3 Besitzer, $4 Rechte
  ziel="$GEHEIM/$1"
  if [ ! -s "$ziel" ]; then
    if [ -n "$2" ]; then
      printf '%s' "$2" > "$ziel.neu"
      echo "db-abgleich: $1 aus der Umgebungsvariable übernommen (die Variable kann danach entfallen)"
    else
      head -c 48 /dev/urandom | base64 | tr -d '\n/+=' | head -c 40 > "$ziel.neu"
      echo "db-abgleich: $1 neu erzeugt"
    fi
    mv "$ziel.neu" "$ziel"
  elif [ -n "$2" ] && [ "$2" != "$(cat "$ziel")" ]; then
    echo "db-abgleich: Hinweis: Umgebungsvariable für $1 weicht ab und wird ignoriert; sie kann aus dem Stack entfernt werden"
  fi
  chown "$3" "$ziel"
  chmod "$4" "$ziel"
}

abgleichen() {
  # Warten, bis der endgültige Server per TCP erreichbar ist (nicht der temporäre Init-Server).
  i=0
  until pg_isready -q -h 127.0.0.1 -U postgres; do
    i=$((i + 1)); [ "$i" -gt 120 ] && { echo "db-abgleich: Server nicht erreichbar, Abgleich übersprungen" >&2; return 0; }
    sleep 1
  done
  # Lokale Socket-Verbindung im Container (vertrauenswürdig); Passwörter über psql-Variablen quotiert.
  PGPASSWORD="" psql -v ON_ERROR_STOP=1 -U postgres -d postgres -v app="$POSTGRES_APP_PASSWORD" -v admin="$POSTGRES_PASSWORD" <<'SQL' \
    && echo "db-abgleich: Passwörter und Anwendungsrolle abgeglichen" \
    || echo "db-abgleich: FEHLER beim Abgleich" >&2
SELECT format('CREATE ROLE stockmaster LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L', :'app')
  WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'stockmaster') \gexec
SELECT format('ALTER ROLE stockmaster PASSWORD %L', :'app') \gexec
SELECT format('ALTER ROLE postgres PASSWORD %L', :'admin') \gexec
SELECT 'CREATE DATABASE stockmaster OWNER stockmaster'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'stockmaster') \gexec
SELECT 'REVOKE ALL ON DATABASE stockmaster FROM PUBLIC' \gexec
SQL
}

# Nur beim eigentlichen Serverstart (nicht bei anderen Befehlen wie "psql" oder "pg_dump").
if [ "${1:-}" = "postgres" ]; then
  mkdir -p "$GEHEIM"
  chmod 0755 "$GEHEIM"
  # postgres (uid 70) liest das Admin-Passwort; die API (uid 10001) nur das Passwort der Anwendungsrolle.
  passwort_datei db_admin_passwort "${POSTGRES_PASSWORD:-}" 70:70 0400
  passwort_datei db_app_passwort "${POSTGRES_APP_PASSWORD:-}" 10001:70 0440
  POSTGRES_PASSWORD="$(cat "$GEHEIM/db_admin_passwort")"
  POSTGRES_APP_PASSWORD="$(cat "$GEHEIM/db_app_passwort")"
  export POSTGRES_PASSWORD POSTGRES_APP_PASSWORD
  abgleichen &
fi
exec docker-entrypoint.sh "$@"
