#!/bin/sh
# Legt die Anwendungsrolle ohne Superuser-Rechte an; sie besitzt nur die eigene Datenbank.
set -eu
APP_PASSWORT="$(cat /run/secrets/db_app_passwort)"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE stockmaster LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '${APP_PASSWORT}';
CREATE DATABASE stockmaster OWNER stockmaster;
REVOKE ALL ON DATABASE stockmaster FROM PUBLIC;
SQL
