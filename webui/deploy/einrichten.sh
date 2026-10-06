#!/usr/bin/env bash
# Erzeugt die Docker Secrets mit Zufallswerten (einmalig vor dem ersten Start).
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p secrets
chmod 700 secrets
erzeugen() { [ -s "secrets/$1" ] || { printf '%s' "$2" > "secrets/$1"; echo "secrets/$1 angelegt"; }; }
erzeugen db_admin_passwort "$(openssl rand -hex 24)"
erzeugen db_app_passwort "$(openssl rand -hex 24)"
erzeugen sm_schluessel "$(openssl rand -base64 32)"
erzeugen datenbank_url "postgresql+psycopg://stockmaster:$(cat secrets/db_app_passwort)@db:5432/stockmaster"
# Die Container lesen die Dateien als eigener Benutzer; das Verzeichnis bleibt 0700.
chmod 644 secrets/*
[ -f .env ] || { cp .env.example .env; echo ".env aus .env.example angelegt – SM_HOSTNAME und SPIEL_REPO prüfen."; }
