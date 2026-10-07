"""Freigabe-Regeln: Was ein Mensch freigeben darf, und was nie (Spielstand bleibt schreibgeschützt)."""

from pathlib import Path

import pytest

from stockmaster.freigabe_regeln import MAX_ZEICHEN, bewerten

DATEN, FRAMEWORK = Path("/data"), Path("/app")


def pruefen(befehl: str):
    return bewerten("Bash", {"command": befehl}, DATEN, FRAMEWORK)


# Der Befehl aus dem Testlauf, der mangels Freigabe-Oberfläche abgelehnt wurde.
KURSE_SCHLEIFE = ("for t in ^GSPC ^GDAXI EUNL.DE GC=F BZ=F; do echo \"== $t\"; python tools/kurse.py historie "
                  "--von 2026-07-01 --bis 2026-10-07 $t 2>/dev/null | awk 'NR<=2 || NR%5==0'; done")


@pytest.mark.parametrize("befehl", [
    KURSE_SCHLEIFE,
    "awk 'BEGIN{print 1+1}'",
    "awk -F, -v n=3 '$2 == n {print $1}' /data/data/kurse.csv",
    "head -n 5 journal/2026-10-12.md",
    "cat /data/lessons.md",
    "wc -l /data/trades/*.csv",
    "sort -u /data/news/2026-10.jsonl | head -20",
    "python tools/news.py liste --tage 3 | head -20",
    "python3 tools/kurse.py markt 2>&1",
    "echo \"a b\" | tr a-z A-Z",
    "grep -c Gold /data/news/2026-10.jsonl",
    "ls -la /app/config && date",
    "for a in 1 2 3; do for b in x y; do echo $a$b; done; done",
    "cat /data/lessons.md >/dev/null 2>&1",
    "sort -t, -k2,2n -u /data/data/kurse.csv | uniq -c | tail -n 3",
    "date +%Y-%m-%d && tail -n 5 /data/news/2026-10.jsonl",
])
def test_lesende_befehle_sind_freigebbar(befehl):
    bewertung = pruefen(befehl)
    assert bewertung.freigebbar, bewertung.grund


@pytest.mark.parametrize("befehl, grund", [
    # Schreiben in den Spielstand und anderswo: bleibt gesperrt
    ("echo x > /data/portfolios/defensiv/cash.csv", "Umleitung"),
    ("echo x >> notiz.txt", "Umleitung"),
    ("echo x>notiz.txt", "Umleitung"),
    ("cat a | tee b", "tee"),
    ("sed -i s/a/b/ /data/lessons.md", "sed"),
    ("rm -rf /data/trades", "rm"),
    ("cp a /data/trades/b", "cp"),
    ("mv a b", "mv"),
    ("python tools/buchen.py > /data/trades/x.csv", "Umleitung"),
    # Programme starten und Geheimnisse lesen
    ("curl http://example.org", "curl"),
    ("bash -c 'echo hi'", "bash"),
    ("sh -c ls", "sh"),
    ("env", "env"),
    ("python -c \"print(1)\"", "Python"),
    ("python -m pytest", "Python"),
    ("python tools/../x.py", ".."),
    ("python /tmp/x.py", "Python"),
    ("find /data -delete", "find"),
    ("xargs rm", "xargs"),
    ("FOO=1 echo x", "FOO"),
    ("cat /data-app/geheimnisse.json", "außerhalb"),
    ("cat /proc/self/environ", "außerhalb"),
    ("cat /etc/passwd", "außerhalb"),
    ("cat /d*ta-app/geheimnisse.json", "außerhalb"),
    ("cat /data/../data-app/geheimnisse.json", ".."),
    ("cat ../geheimnisse.json", ".."),
    ("cat ~/.claude/settings.json", "~"),
    ("cat --file=/etc/passwd", "außerhalb"),
    ("echo $HOME", "Variable"),
    ("echo $CLAUDE_CODE_OAUTH_TOKEN", "Variable"),
    ("echo ${HOME}", "$"),
    ("echo $(whoami)", "$"),
    ("echo `id`", "Befehlsersetzung"),
    ("echo \"$(id)\"", "$"),
    ("echo \"`id`\"", "Backticks"),
    ("cat <(echo a)", "Eingabeumleitung"),
    ("cat < /etc/passwd", "Eingabeumleitung"),
    ("cat <<EOF\nx\nEOF", "Eingabeumleitung"),
    ("(echo a)", "Unterschalen"),
    ("{ echo a; }", "Unterschalen"),
    ("echo a & echo b", "Hintergrund"),
    ("echo a \\\n b", "Backslash"),
    ("echo a # kommentar", "Kommentar"),
    # awk, sort, uniq, tail, date: lesende Werkzeuge mit schreibenden oder ausführenden Optionen
    ("awk 'BEGIN{system(\"id\")}'", "awk"),
    ("awk '{print > \"f\"}' x", "awk"),
    ("awk '{print $1 | \"sh\"}' x", "awk"),
    ("awk 'BEGIN{\"id\" | getline x; print x}'", "awk"),
    ("awk 'BEGIN{print ENVIRON[\"HOME\"]}'", "awk"),
    ("awk -f programm.awk x", "awk"),
    ("awk -i inplace '{print}' x", "awk"),
    ("awk", "awk"),
    ("sort -o ausgabe.txt eingabe.txt", "sort"),
    ("sort --output=ausgabe.txt eingabe.txt", "sort"),
    ("sort -uo ausgabe.txt eingabe.txt", "sort"),
    ("sort -nro ausgabe.txt eingabe.txt", "sort"),
    ("sort -T /data/trades eingabe.txt", "sort"),
    ("sort --compress-program=sh eingabe.txt", "sort"),
    ("uniq eingabe.txt ausgabe.txt", "uniq"),
    ("tail -fn5 /data/news/2026-10.jsonl", "tail"),
    ("tail --follow=name x", "tail"),
    ("date -us 2020-01-01", "date"),
    ("date --set=2020-01-01", "date"),
    ("tail -f /data/news/2026-10.jsonl", "tail"),
    ("date -s 2020-01-01", "date"),
    # Schleifen nur in einfacher Form
    ("for t in a b; echo $t; done", "do"),
    ("for t in a b; do echo $t", "Schleife"),
    ("do echo a; done", "do"),
    ("echo a; done", "Schleife"),
    ("for 1x in a; do echo; done", "Schleifen der Form"),
    ("while true; do echo; done", "while"),
    ("for t in $x; do echo; done", "Variable"),
    ("for t in a; do $t; done", "$t"),
    # Form
    ("echo 'offen", "Anführungszeichen"),
    ("echo \"a\\nb\"", "Backslash"),
])
def test_gesperrt_mit_grund(befehl, grund):
    bewertung = pruefen(befehl)
    assert not bewertung.freigebbar, f"fälschlich freigebbar: {befehl!r}"
    assert grund in (bewertung.grund or ""), bewertung.grund


def test_nur_bash_ist_freigebbar():
    for werkzeug in ("Write", "Edit", "NotebookEdit", "WebFetch", "mcp__x__y"):
        bewertung = bewerten(werkzeug, {"file_path": "/data/portfolios/x"}, DATEN, FRAMEWORK)
        assert not bewertung.freigebbar and "Nur Shell-Befehle" in bewertung.grund


def test_ungueltige_eingaben():
    assert not bewerten("Bash", {}, DATEN, FRAMEWORK).freigebbar
    assert not bewerten("Bash", {"command": "   "}, DATEN, FRAMEWORK).freigebbar
    assert not bewerten("Bash", {"command": 5}, DATEN, FRAMEWORK).freigebbar
    assert not pruefen("echo " + "a" * MAX_ZEICHEN).freigebbar
    assert not pruefen("echo a\0b").freigebbar
    for versteckt in ("echo a\u202eb", "echo a\u200bb", "echo a\x1bb", "echo a\rb"):  # Umkehr, Breite null, ESC, CR
        bewertung = pruefen(versteckt)
        assert not bewertung.freigebbar and "Steuerzeichen" in bewertung.grund, versteckt


def test_pfade_nur_in_den_wurzeln():
    assert pruefen("cat /data/lessons.md").freigebbar and pruefen("cat /app/CLAUDE.md").freigebbar
    assert not pruefen("cat /database/x").freigebbar  # Präfix allein genügt nicht
    assert not pruefen("cat /datax").freigebbar
    assert pruefen("cat /dev/null").freigebbar
