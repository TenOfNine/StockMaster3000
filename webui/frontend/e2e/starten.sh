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
from stockmaster.modelle import Auftrag, Benutzer
import json
from datetime import UTC, datetime
with neue_sitzung() as db:
    admin = Benutzer(email="admin@e2e.local", anzeigename="Admin", kennung="a-adm1",
                     passwort_hash=s.passwort_hash("Admin-Passwort-2026!"), ist_admin=True, passwortwechsel_noetig=False)
    db.add(admin)
    db.flush()
    admin.totp_secret_enc = s.totp_verschluesseln("JBSWY3DPEHPK3PXP", admin.id)
    admin.totp_aktiv = True
    db.add(Benutzer(email="kim@e2e.local", anzeigename="Kim", kennung="a-kim1",
                    passwort_hash=s.passwort_hash("Kim-Passwort-2026!"), passwortwechsel_noetig=False))
    ergebnis = """**Ich habe nicht gehandelt und keine Session gestartet.** Es gibt zwei Hindernisse:

1. **Anlagerichtlinien sind offen.** `python tools/richtlinien.py status` meldet: defensiv, ausgewogen.
2. Das Startdatum liegt in der Zukunft. Siehe [Regeln](/regeln.md), [Akte](/entscheidungen/J-20261007-01) und J-20261007-02, <b>roh</b> & [kaputt](/x%zz).

# Überschrift 1
## Überschrift 2 mit J-20261007-03
> Zitat mit [Link J-20261007-04](https://example.org/J-20261007-05) und `J-20261007-06`

| Profil | Stand | Akte |
|---|---|---|
| defensiv | Vorlage | J-20261007-07 |

- [x] erledigt
- [ ] offen
  - verschachtelt[^1]

```python
print("J-20261007-08")
```

---

![Bild](https://example.org/x.png) www.example.org und <https://example.org/a> <!-- Kommentar -->
<details><summary>Mehr</summary>Text</details> [Ref][r] ~~durch~~ \[x\]

[^1]: Fußnote.
[r]: https://example.org/ref "Titel"
"""
    jetzt = datetime.now(UTC)
    db.add(Auftrag(art="trading", status="ok", modell="sonnet", aufwand="medium", auftraggeber="auftraggeber-a",
                   ausloeser="manuell", erstellt=jetzt, begonnen=jetzt, beendet=jetzt, pruefung_ok=True,
                   ergebnis=json.dumps({"result": ergebnis, "is_error": False})))
    db.add(Auftrag(art="trading", status="laeuft", modell="sonnet", aufwand="medium", auftraggeber="auftraggeber-a",
                   ausloeser="zeitplan", erstellt=datetime.now(UTC), begonnen=datetime.now(UTC)))
    db.commit()
from stockmaster import appdaten
import os, pathlib
_sperre = pathlib.Path(os.environ["STOCKMASTER_DATA_DIR"]) / "session.lock"
_sperre.write_text(json.dumps({"person": "auftraggeber-a", "start": datetime.now().astimezone().isoformat(timespec="seconds"), "art": "trading"}))
appdaten.bereich_speichern("zeitplan", {"automatik": True, "zeitzone": "Europe/Berlin", "auftraggeber": "auftraggeber-a",
                                        "termine": [{"wochentage": [0, 1, 2, 3, 4], "uhrzeit": "09:35", "art": "trading"}]})
PY
exec "$UV" run --frozen uvicorn stockmaster.main:app --host 127.0.0.1 --port 8000
