#!/usr/bin/env bash
# Startet das Backend für die E2E-Tests mit einem frisch erzeugten Demo-Datenverzeichnis.
set -euo pipefail
WURZEL="$(cd "$(dirname "$0")/../../.." && pwd)"
ARBEIT="${E2E_VERZEICHNIS:-$(mktemp -d)}"
python3 "$WURZEL/webui/demo/demo_daten.py" --ziel "$ARBEIT/daten" --tage 80 --ende 2026-09-30 --seed 5 >/dev/null
export STOCKMASTER_DATA_DIR="$ARBEIT/daten"
export STOCKMASTER_APP_DIR="$ARBEIT/app"
export STOCKMASTER_FRAMEWORK_DIR="$WURZEL"
export SM_AUFTRAG_WARTEN_SEKUNDEN=1
export SM_DATENBANK_URL="sqlite:///$ARBEIT/e2e.db"
export SM_COOKIE_SICHER=false
export SM_SCHLUESSEL="$(python3 -c 'import base64,os;print(base64.b64encode(os.urandom(32)).decode())')"
cd "$WURZEL/webui/backend"
UV="${UV:-uv}"
"$UV" run --frozen python -m stockmaster migrieren >/dev/null
"$UV" run --frozen python - <<'PY'
from stockmaster import sicherheit as s
from stockmaster.db import neue_sitzung
from stockmaster.modelle import Benutzer
with neue_sitzung() as db:
    admin = Benutzer(email="admin@e2e.local", anzeigename="Admin", kennung="a-adm1",
                     passwort_hash=s.passwort_hash("Admin-Passwort-2026!"), ist_admin=True, passwortwechsel_noetig=False)
    db.add(admin)
    db.flush()
    admin.totp_secret_enc = s.totp_verschluesseln("JBSWY3DPEHPK3PXP", admin.id)
    admin.totp_aktiv = True
    db.add(Benutzer(email="kim@e2e.local", anzeigename="Kim", kennung="a-kim1",
                    passwort_hash=s.passwort_hash("Kim-Passwort-2026!"), passwortwechsel_noetig=False))
    db.commit()
PY
exec "$UV" run --frozen uvicorn stockmaster.main:app --host 127.0.0.1 --port 8000
