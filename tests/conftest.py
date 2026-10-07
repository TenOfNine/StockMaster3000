"""Gemeinsame Test-Fixtures: getrenntes Framework und Datenverzeichnis, feste Uhr, Kursquelle ohne Netzwerk."""

import shutil
import sys
from datetime import datetime
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "tools"))

import gemeinsam  # noqa: E402


@pytest.fixture
def framework(tmp_path, monkeypatch):
    """Framework-Kopie (config/, regeln.md, STATUS.md, Vorlagen), damit Tests sie ändern dürfen."""
    ziel = tmp_path / "framework"
    shutil.copytree(WURZEL / "config", ziel / "config")
    shutil.copytree(WURZEL / "vorlagen", ziel / "vorlagen")
    for name in ("regeln.md", "STATUS.md"):
        shutil.copy(WURZEL / name, ziel / name)
    monkeypatch.setenv("STOCKMASTER_FRAMEWORK_DIR", str(ziel))
    return ziel


@pytest.fixture
def projekt(tmp_path, monkeypatch, framework):
    """Leeres Datenverzeichnis (Spielstand), getrennt vom Framework."""
    daten = tmp_path / "daten"
    for ordner in ("portfolios", "trades", "journal", "data/kurse", "data/historie",
                   "data/nav", "data/limits", "strategie", "reviews", "news"):
        (daten / ordner).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("STOCKMASTER_DATA_DIR", str(daten))
    return daten


@pytest.fixture
def uhr(monkeypatch):
    """Steuerbare Uhr: uhr.stellen('2026-10-12T10:00')."""

    class Uhr:
        def __init__(self):
            self.zeit = datetime(2026, 10, 12, 10, 0, tzinfo=gemeinsam.TZ)

        def stellen(self, text):
            self.zeit = datetime.fromisoformat(text).replace(tzinfo=gemeinsam.TZ)

        def __call__(self):
            return self.zeit

    instanz = Uhr()
    monkeypatch.setattr(gemeinsam, "jetzt", instanz)
    return instanz


@pytest.fixture
def quelle(monkeypatch, uhr):
    """Kursquelle mit vorgegebenen Daten statt Netzwerk."""
    import kurse
    from attrappe import AttrappenQuelle

    attrappe = AttrappenQuelle(uhr)
    monkeypatch.setattr(kurse, "QUELLE", attrappe)
    return attrappe
