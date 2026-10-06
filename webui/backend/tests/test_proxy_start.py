"""Startskript des Proxys: Namen aus der Umgebung werden streng geprüft, bevor sie in die Caddyfile gelangen."""

import os
import subprocess
from pathlib import Path

import pytest

SKRIPT = Path(__file__).resolve().parents[3] / "webui" / "deploy" / "proxy-start.sh"


def laufen(**umgebung) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ["PATH"]}
    env.update(umgebung)
    return subprocess.run(["sh", str(SKRIPT), "--nur-pruefen"], env=env, capture_output=True, text=True, timeout=20)


def ergebnis(**umgebung) -> dict[str, str]:
    prozess = laufen(**umgebung)
    assert prozess.returncode == 0, prozess.stderr
    return dict(zeile.split("=", 1) for zeile in prozess.stdout.splitlines())


def test_skript_ist_ausfuehrbar():
    assert os.access(SKRIPT, os.X_OK)


def test_standard_ohne_angaben():
    assert ergebnis() == {"hosts": "stockmaster.local localhost", "sni": "stockmaster.local"}


def test_hauptname_wird_uebernommen_und_kleingeschrieben():
    assert ergebnis(SM_HOSTNAME="Boerse.Heimnetz.LOCAL") == {"hosts": "boerse.heimnetz.local localhost",
                                                              "sni": "boerse.heimnetz.local"}


def test_ip_adresse_als_zusaetzlicher_host_bestimmt_das_zertifikat_ohne_servernamen():
    assert ergebnis(SM_ZUSAETZLICHE_HOSTS="192.168.2.187") == {
        "hosts": "stockmaster.local localhost 192.168.2.187", "sni": "192.168.2.187"}


def test_mehrere_hosts_mit_komma_und_leerzeichen_die_erste_ip_gewinnt():
    r = ergebnis(SM_ZUSAETZLICHE_HOSTS="nas.local, 192.168.2.187 ,10.0.0.5;[fd00::1]")
    assert r["hosts"] == "stockmaster.local localhost nas.local 192.168.2.187 10.0.0.5 [fd00::1]"
    assert r["sni"] == "192.168.2.187"


def test_nur_namen_dann_gilt_der_hauptname_fuer_clients_ohne_servernamen():
    r = ergebnis(SM_ZUSAETZLICHE_HOSTS="nas.local")
    assert r == {"hosts": "stockmaster.local localhost nas.local", "sni": "stockmaster.local"}


def test_ipv6_ohne_klammern_im_zertifikatsnamen():
    assert ergebnis(SM_ZUSAETZLICHE_HOSTS="[fd00::1]")["sni"] == "fd00::1"


def test_doppelte_werden_weggelassen():
    r = ergebnis(SM_ZUSAETZLICHE_HOSTS="STOCKMASTER.local localhost 10.0.0.5 10.0.0.5")
    assert r["hosts"] == "stockmaster.local localhost 10.0.0.5"


@pytest.mark.parametrize("wert", [
    "evil.local}",                      # schließt den Block
    "} respond 200 {",                  # eigene Anweisung
    "a.local:8443",                     # Port
    "*.local",                          # Platzhalter
    "a/b", "a\\b", "a;b{", "$(id)", "`id`", "a\"b", "a'b",
    "-a.local", "a-.local", ".a.local", "a.local.", "a..local",
    "[zz]", "[]", "[1.2.3.4]", "[fd00::1", "fd00::1]",
    "ä.local",
    "a" * 254,
])
def test_ungueltige_zusaetzliche_hosts_werden_abgelehnt(wert):
    prozess = laufen(SM_ZUSAETZLICHE_HOSTS=wert)
    assert prozess.returncode == 1
    assert "SM_ZUSAETZLICHE_HOSTS" in prozess.stderr
    assert prozess.stdout == ""


def test_eine_ungueltige_angabe_in_der_liste_lehnt_alles_ab():
    prozess = laufen(SM_ZUSAETZLICHE_HOSTS="nas.local 192.168.2.187 a.local:443")
    assert prozess.returncode == 1 and "a.local:443" in prozess.stderr


@pytest.mark.parametrize("wert", ["stock master", "ok.local\n} respond 200 {", "a.local:8443", "*", "", "[::1"])
def test_ungueltiger_hauptname_wird_abgelehnt(wert):
    prozess = laufen(SM_HOSTNAME=wert)
    # Ein leerer Wert gilt wie nicht gesetzt (Standardname); alles andere ist ein Konfigurationsfehler.
    if wert == "":
        assert prozess.returncode == 0
    else:
        assert prozess.returncode == 1 and "SM_HOSTNAME" in prozess.stderr


def test_zeilenumbruch_in_der_liste_trennt_nur_und_schleust_nichts_ein():
    r = ergebnis(SM_ZUSAETZLICHE_HOSTS="a.local\nb.local")
    assert r["hosts"] == "stockmaster.local localhost a.local b.local"
    assert laufen(SM_ZUSAETZLICHE_HOSTS="a.local\n} respond 200 {").returncode == 1
