"""Gemeinsame Test-Fixtures: isoliertes Projektverzeichnis, feste Uhr, Kursquelle ohne Netzwerk."""

import shutil
import sys
from datetime import datetime
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "tools"))

import gemeinsam  # noqa: E402


@pytest.fixture
def projekt(tmp_path, monkeypatch):
    """Leeres Projektverzeichnis mit echter Konfiguration und Regeln."""
    shutil.copytree(WURZEL / "config", tmp_path / "config")
    for name in ("regeln.md", "STATUS.md"):
        shutil.copy(WURZEL / name, tmp_path / name)
    for ordner in ("portfolios", "trades", "journal", "data/kurse", "data/historie",
                   "data/nav", "data/limits", "strategie", "reviews"):
        (tmp_path / ordner).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BOERSE_ROOT", str(tmp_path))
    return tmp_path


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
