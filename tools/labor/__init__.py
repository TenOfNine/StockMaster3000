"""Strategie-Labor (L4): deterministischer Rückblick auf Tagesdaten, ohne Orders und ohne Spielstand zu ändern.

- `daten`: Tageskerzen mit eigenem Zwischenspeicher (labor/daten/), damit Ergebnisse reproduzierbar bleiben.
- `engine`: Wiedergabe (Replay) mit den Kosten des Spiels (config/kosten.json über buchen.kauf_rechnung und
  verkauf_rechnung, produkte.py für Knock-outs) und festen Ausführungsregeln gegen Look-ahead.
- `strategien`: deklarative Strategien (Buy & Hold, 60/40, Trendfolge, Momentum, Volatilitätsziel, Overnight).
- `bericht`: Kennzahlen mit Intervall (statistik.py), In-/Out-of-Sample, Deflated Sharpe, JSON und Markdown.

Nicht getestet wird diskretionäres Claude-Trading: Das Modell kennt die Vergangenheit aus dem Training, ein
Rückblick wäre durch Look-ahead verzerrt. Die Aufgabenteilung: Claude formuliert Hypothesen, der Code prüft sie, nur
Überlebende werden Vorschläge an die Auftraggeber.
"""
