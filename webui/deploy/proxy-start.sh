#!/bin/sh
# Startskript des Proxys: prüft die Namen aus der Umgebung und startet Caddy.
#
#   SM_HOSTNAME             Hauptname der Web-UI (Standard: stockmaster.local)
#   SM_ZUSAETZLICHE_HOSTS   weitere Namen oder IP-Adressen, durch Leerzeichen oder Komma getrennt, ohne Port
#                           (z. B. die IP des Servers, damit https://192.168.2.187 funktioniert)
#
# Die Werte landen in der Caddyfile. Deshalb wird jeder einzeln streng geprüft, damit sich über die
# Umgebung nichts in die Konfiguration einschleusen lässt (Platzhalter, Ports, Klammern, Zeilenumbrüche).
#
# Clients, die ohne Servernamen (SNI) verbinden, etwa ein Browser bei einer IP-Adresse in der URL, bekommen
# das Zertifikat der ersten IP-Adresse aus der Liste, sonst das des Hauptnamens. Hinter Docker sieht Caddy
# als lokale Adresse die des Containers, nicht die getippte; ohne diese Vorgabe scheitert der TLS-Handshake.
#
# Mit --nur-pruefen wird nur geprüft und das Ergebnis ausgegeben (für Tests).
set -eu
set -f   # keine Dateinamen-Erweiterung beim Aufteilen der Liste

fehler() {
  echo "Konfigurationsfehler: $1" >&2
  exit 1
}

# Hostname (Buchstaben, Ziffern, '-', '.'; schließt IPv4 ein) oder IPv6-Adresse in eckigen Klammern.
host_gueltig() {
  h=$1
  [ -n "$h" ] && [ "${#h}" -le 253 ] || return 1
  case $h in
    \[*\])
      i=${h#\[}
      i=${i%\]}
      case $i in "" | *[!0-9A-Fa-f:.]*) return 1 ;; esac
      case $i in *:*) return 0 ;; esac
      return 1
      ;;
    *[!A-Za-z0-9.-]* | .* | *. | -* | *- | *..* | *-.* | *.-*) return 1 ;;  # auch je Label: kein '-' am Rand
  esac
  return 0
}

ist_ip() {
  case $1 in
    \[*\]) return 0 ;;
    "" | *[!0-9.]*) return 1 ;;
    *.*.*.*) return 0 ;;
  esac
  return 1
}

klein() { printf '%s' "$1" | tr 'A-Z' 'a-z'; }

haupt=${SM_HOSTNAME:-stockmaster.local}
host_gueltig "$haupt" ||
  fehler "SM_HOSTNAME ist kein gültiger Name und keine gültige IP-Adresse (erlaubt: Buchstaben, Ziffern, '.', '-'; ohne Port und Platzhalter)."
haupt=$(klein "$haupt")

zusatz=""
sni=""
liste=$(printf '%s' "${SM_ZUSAETZLICHE_HOSTS:-}" | tr ',;' '  ')
for h in $liste; do
  host_gueltig "$h" ||
    fehler "SM_ZUSAETZLICHE_HOSTS: '$(printf '%.60s' "$h")' ist ungültig. Erlaubt sind Namen und IP-Adressen ohne Port und Platzhalter, getrennt durch Leerzeichen oder Komma."
  h=$(klein "$h")
  case " $haupt localhost$zusatz " in *" $h "*) continue ;; esac # Doppelte weglassen
  zusatz="$zusatz $h"
  if [ -z "$sni" ] && ist_ip "$h"; then sni=$h; fi
done
zusatz=${zusatz# }

[ -n "$sni" ] || sni=$haupt
sni=${sni#\[}
sni=${sni%\]}

export SM_HOSTNAME="$haupt" SM_HOSTS_ZUSATZ="$zusatz" SM_SNI_STANDARD="$sni"

if [ "${1:-}" = "--nur-pruefen" ]; then
  echo "hosts=$haupt localhost${zusatz:+ $zusatz}"
  echo "sni=$sni"
  exit 0
fi

echo "Proxy antwortet auf: $haupt localhost${zusatz:+ $zusatz} (Zertifikat ohne Servernamen: $sni)"
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
