#!/bin/sh
# Wrapper um den Standard-Entrypoint von PostgreSQL: Gleicht bei JEDEM Start die Passwörter der
# Rollen mit den Umgebungsvariablen ab und legt die Anwendungsrolle und -datenbank an, falls sie
# fehlen. PostgreSQL selbst schreibt POSTGRES_PASSWORD nur beim allerersten Start; ohne Abgleich
# passt ein geändertes Passwort (z. B. beim erneuten Deploy in Portainer) nicht mehr zum Volume.
set -eu

abgleichen() {
  # Warten, bis der endgültige Server per TCP erreichbar ist (nicht der temporäre Init-Server).
  i=0
  until pg_isready -q -h 127.0.0.1 -U postgres; do
    i=$((i + 1)); [ "$i" -gt 120 ] && { echo "db-abgleich: Server nicht erreichbar, Abgleich übersprungen" >&2; return 0; }
    sleep 1
  done
  APP="${POSTGRES_APP_PASSWORD:-}"
  [ -n "$APP" ] || { echo "db-abgleich: POSTGRES_APP_PASSWORD nicht gesetzt, Abgleich übersprungen" >&2; return 0; }
  # Lokale Socket-Verbindung im Container (vertrauenswürdig); Passwörter über psql-Variablen quotiert.
  PGPASSWORD="" psql -v ON_ERROR_STOP=1 -U postgres -d postgres -v app="$APP" -v admin="${POSTGRES_PASSWORD:-}" <<'SQL' \
    && echo "db-abgleich: Passwörter und Anwendungsrolle abgeglichen" \
    || echo "db-abgleich: FEHLER beim Abgleich" >&2
SELECT format('CREATE ROLE stockmaster LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L', :'app')
  WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'stockmaster') \gexec
SELECT format('ALTER ROLE stockmaster PASSWORD %L', :'app') \gexec
SELECT CASE WHEN :'admin' <> '' THEN format('ALTER ROLE postgres PASSWORD %L', :'admin') END \gexec
SELECT 'CREATE DATABASE stockmaster OWNER stockmaster'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'stockmaster') \gexec
SELECT 'REVOKE ALL ON DATABASE stockmaster FROM PUBLIC' \gexec
SQL
}

# Nur beim eigentlichen Serverstart abgleichen (nicht bei anderen Befehlen wie "psql" oder "pg_dump").
if [ "${1:-}" = "postgres" ]; then
  abgleichen &
fi
exec docker-entrypoint.sh "$@"
