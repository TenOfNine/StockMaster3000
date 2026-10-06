#!/bin/sh
# Legt die Anwendungsrolle ohne Superuser-Rechte an; sie besitzt nur die eigene Datenbank.
set -eu
# Docker Secret (docker-compose.yml) oder Umgebungsvariable (Portainer-Stack).
if [ -f /run/secrets/db_app_passwort ]; then
  APP_PASSWORT="$(cat /run/secrets/db_app_passwort)"
else
  APP_PASSWORT="${POSTGRES_APP_PASSWORD:?POSTGRES_APP_PASSWORD fehlt}"
fi
case "$APP_PASSWORT" in
  *[!A-Za-z0-9]*) echo "Das Anwendungspasswort darf nur Buchstaben und Ziffern enthalten (z. B. openssl rand -hex 24)." >&2; exit 1 ;;
esac
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE stockmaster LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '${APP_PASSWORT}';
CREATE DATABASE stockmaster OWNER stockmaster;
REVOKE ALL ON DATABASE stockmaster FROM PUBLIC;
SQL
