#!/usr/bin/env bash
# Rauchtest des Docker-Stacks: baut, startet mit einem Demo-Repository und prüft
# Erreichbarkeit, HTTPS, Sicherheits-Header, Admin-Erstanlage und die Heimnetz-Schranke.
set -euo pipefail
cd "$(dirname "$0")/../.."
ARBEIT="$(mktemp -d)"
export COMPOSE_PROJECT_NAME=stockmaster-rauchtest
export SPIEL_REPO="$ARBEIT/repo" SM_HTTPS_PORT=18443 SM_HTTP_PORT=18080 SM_HOSTNAME=stockmaster.local
aufraeumen() {
  docker network disconnect extern-rauchtest "${COMPOSE_PROJECT_NAME}-proxy-1" >/dev/null 2>&1 || true
  docker network rm extern-rauchtest >/dev/null 2>&1 || true
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap aufraeumen EXIT

python3 webui/demo/demo_daten.py --ziel "$SPIEL_REPO" --tage 40 --ende 2026-09-30 >/dev/null
[ -d secrets ] || bash webui/deploy/einrichten.sh
if [ -n "${RAUCHTEST_OHNE_BUILD:-}" ]; then docker compose up -d --no-build --wait --wait-timeout 300; else docker compose up -d --build --wait --wait-timeout 300; fi

curl() { command curl --silent --show-error --insecure --noproxy '*' "$@"; }
pruefe() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FEHL $1: erwartet '$3', erhalten '$2'"; exit 1; fi; }

pruefe "SPA erreichbar" "$(curl -o /dev/null -w '%{http_code}' https://localhost:18443/)" 200
pruefe "API-Health" "$(curl https://localhost:18443/api/health)" '{"ok":true}'
pruefe "HTTP leitet auf HTTPS um" "$(curl -o /dev/null -w '%{http_code}' http://localhost:18080/)" 308
pruefe "Ohne Anmeldung gesperrt" "$(curl -o /dev/null -w '%{http_code}' https://localhost:18443/api/spiel/ueberblick)" 401
KOPF="$(curl -I https://localhost:18443/)"
grep -qi "content-security-policy: default-src 'self'" <<<"$KOPF" && echo "ok   CSP" || { echo "FEHL CSP"; exit 1; }
grep -qi "strict-transport-security" <<<"$KOPF" && echo "ok   HSTS" || { echo "FEHL HSTS"; exit 1; }
docker compose exec -T api python -m stockmaster admin-anlegen --email admin@rauchtest.local >/dev/null && echo "ok   Admin-Erstanlage"
if docker compose exec -T api python -m stockmaster admin-anlegen --email zweiter@rauchtest.local >/dev/null 2>&1; then
  echo "FEHL zweite Admin-Erstanlage wurde nicht abgelehnt"; exit 1
else
  echo "ok   zweite Admin-Erstanlage abgelehnt"
fi

# Anfrage aus einem öffentlichen Adressbereich (Dokumentationsnetz 198.51.100.0/24) -> 403 von Caddy
docker network create --subnet 198.51.100.0/24 extern-rauchtest >/dev/null
docker network connect extern-rauchtest "${COMPOSE_PROJECT_NAME}-proxy-1"
IP="$(docker inspect -f '{{(index .NetworkSettings.Networks "extern-rauchtest").IPAddress}}' "${COMPOSE_PROJECT_NAME}-proxy-1")"
ANTWORT="$(docker run --rm --network extern-rauchtest --entrypoint python stockmaster-api:lokal -c "
import socket, ssl
ctx = ssl._create_unverified_context()
s = ctx.wrap_socket(socket.create_connection(('$IP', 8443)), server_hostname='stockmaster.local')
s.sendall(b'GET /api/health HTTP/1.1\r\nHost: stockmaster.local\r\nConnection: close\r\n\r\n')
daten = b''
while teil := s.recv(4096): daten += teil
print(daten.decode().split('\r\n')[0])")"
pruefe "Öffentliche Adresse gesperrt" "$ANTWORT" "HTTP/1.1 403 Forbidden"
echo "Rauchtest bestanden."
