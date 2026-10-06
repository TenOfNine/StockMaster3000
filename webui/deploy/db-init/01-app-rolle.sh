#!/bin/sh
# Legt die Anwendungsrolle ohne Superuser-Rechte an; sie besitzt nur die eigene Datenbank.
# Das Passwort darf beliebige Zeichen enthalten (psql-Variable, mit %L quotiert).
set -eu
# Docker Secret (docker-compose.yml) oder Umgebungsvariable (Portainer-Stack).
if [ -f /run/secrets/db_app_passwort ]; then
  APP_PASSWORT="$(cat /run/secrets/db_app_passwort)"
else
  APP_PASSWORT="${POSTGRES_APP_PASSWORD:?POSTGRES_APP_PASSWORD fehlt}"
fi
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -v app="$APP_PASSWORT" <<'SQL'
SELECT format('CREATE ROLE stockmaster LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L', :'app') \gexec
CREATE DATABASE stockmaster OWNER stockmaster;
REVOKE ALL ON DATABASE stockmaster FROM PUBLIC;
SQL
