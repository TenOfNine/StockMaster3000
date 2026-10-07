#!/usr/bin/env bash
# Legt .env aus .env.example an (einmalig). Geheimnisse gibt es auf dem Host nicht mehr: DB-Passwörter
# und der Master-Schlüssel entstehen beim ersten Start in den Volumes.
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -f .env ] || { cp .env.example .env; echo ".env aus .env.example angelegt – SM_HOSTNAME prüfen."; }
