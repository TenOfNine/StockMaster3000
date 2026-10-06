# Entwicklungsauftrag Phase 1: Aufbau

## Ziel
Ein lauffähiges, getestetes Werkzeugset im Repository, mit dem Claude
Trading-Sessions nach regeln.md durchführen kann. Leitprinzip: **Rechnen
macht Code, Entscheiden macht Claude.** Am Ende steht eine Testsession
ohne Trades und der Übergang zu Phase 2.

## Technik
- Python 3.11 oder neuer; Abhängigkeiten: pandas, yfinance, pytest.
  Weitere nur mit Begründung in STATUS.md.
- Kommandozeilenwerkzeuge mit argparse, Hilfetexte auf Deutsch.
- Geldbeträge als Decimal, auf Cent gerundet; Stückzahlen bis 6
  Nachkommastellen.
- Zeiten in Europe/Berlin, gespeichert im ISO-Format mit Zeitzone.
- Schreibvorgänge atomar (temporäre Datei, dann umbenennen).
- Tests laufen ohne Netzwerk (Kursdaten gemockt).

## Zielstruktur

    CLAUDE.md, README.md, KONZEPT.md, regeln.md, STATUS.md, lessons.md
    requirements.txt, .gitignore
    config/
      profile.json        Limits je Profil (= regeln.md Abschnitt 7)
      universum.json      Börsen, Handelszeiten, erlaubte Basiswerte
      kosten.json         Spreads, Gebühr, Mindestorder, Zinssätze
    portfolios/<profil>.json
    trades/<profil>.csv
    strategie/<profil>.md
    journal/              JJJJ-MM-TT_<person>.md
    reviews/
    data/kurse/           Protokoll aller abgefragten Kurse (CSV je Tag)
    data/historie/        Tagesdaten je Ticker (OHLC, Dividenden, Splits)
    data/nav/<profil>.csv tägliche Portfoliowerte
    data/benchmark.csv
    ranking.md
    session.lock          nur während einer Session
    tools/  kurse.py produkte.py limits.py buchen.py bewertung.py
            pruefe.py session.py init.py
    tests/
    .github/workflows/pruefung.yml

## Datenmodell

**portfolios/<profil>.json**

    {
      "profil": "ausgewogen",
      "startdatum": "JJJJ-MM-TT",
      "cash": "1000.00",
      "verarbeitet_bis": "JJJJ-MM-TT",
      "hoechststand": "1000.00",
      "drawdown_stufe": 0,
      "status": "aktiv",
      "positionen": [
        {"id": "P-0001", "typ": "aktie|etf|ko|faktor",
         "richtung": "long|short", "ticker": "...", "basiswert": "...",
         "stueck": "1.234567", "einstand": "...", "eroeffnet": "...",
         "parameter": {"basispreis": "...", "barriere": "...",
                       "faktor": 3, "wert_je_stueck": "..."},
         "stop": "...", "kursziel": "...", "journal_id": "J-..."}
      ],
      "offene_orders": [
        {"id": "O-0001", "art": "market|limit", "...": "...",
         "erfasst": "...", "journal_id": "J-..."}
      ]
    }

**trades/<profil>.csv** (nur anhängen)

    trade_id,zeit,order_id,position_id,aktion,typ,richtung,ticker,
    basiswert,stueck,kurs,kurs_basiswert,hebel,spread_eur,gebuehr_eur,
    betrag_eur,cash_danach,kursquelle,kurs_zeit,journal_id,grund

`grund` unterscheidet: order, stop, kursziel, knockout, verfall,
dividende, split, zins (Zinsen können auch nur in data/nav stehen).

**data/kurse/JJJJ-MM-TT.csv**

    zeit,ticker,kurs,waehrung,quelle,markt_offen

## Arbeitspakete

### AP1 Grundgerüst und Konfiguration
Struktur anlegen, requirements.txt, .gitignore, config-Dateien gemäß
regeln.md.
Abnahme: config-Werte entsprechen regeln.md; ein Test liest alle
config-Dateien und prüft Vollständigkeit.

### AP2 Kursdaten: tools/kurse.py
- `kurse.py aktuell <ticker...>`: aktueller Kurs, protokolliert in
  data/kurse/; erkennt geschlossene Märkte anhand config/universum.json.
- `kurse.py historie <ticker> --von --bis`: Tagesdaten mit Dividenden
  und Splits, zwischengespeichert in data/historie/.
- Währungsumrechnung über EURUSD=X.
Abnahme: Tests mit gemockten Daten für Protokollierung, Marktstatus,
Umrechnung; verständliche Fehlermeldung, wenn keine Daten kommen.

### AP3 Synthetische Zertifikate: tools/produkte.py
Knock-out Long/Short und Faktor Long/Short exakt nach regeln.md
Abschnitt 4: Ausgabe, Tagesfortschreibung, Bewertung, Knock-out-Prüfung.
Abnahme: Tests für Basispreisberechnung, Aufzinsung über Wochenenden,
Knock-out durch Tagestief bzw. -hoch, Faktor-Wert nie negativ,
Hebelberechnung.

### AP4 Limitprüfung: tools/limits.py
Prüft eine geplante Order gegen alle Limits aus regeln.md Abschnitt 7:
Mindestorder, Einzelposition, Zertifikate-Anteil, Hebel, Gesamt-Exposure,
Cashquote, Risiko je Trade inklusive Kosten, Drawdown-Stufe.
Abnahme: je Regel ein Test für Annahme und Ablehnung; die Ablehnung
nennt Regel, Grenzwert und Istwert.

### AP5 Orders und Buchung: tools/buchen.py
- `buchen.py kaufen --profil --typ --richtung --ticker|--basiswert
  --einsatz --hebel|--faktor --stop --kursziel [--limit] --journal-id`
- `buchen.py verkaufen --profil --position-id [--anteil] --journal-id`
- `buchen.py aendern --profil --position-id --stop --kursziel --journal-id`
- `buchen.py storno --profil --order-id --journal-id`
- Prüft: Journal-ID existiert, Session-Sperre gehört zur aktuellen
  Person, Limits (AP4). Markt offen und Market-Order: sofortige
  Ausführung zum protokollierten Kurs inklusive Spread und Gebühr;
  sonst vormerken.
Abnahme: Tests für sofortige Ausführung, Vormerkung außerhalb der
Handelszeit, Ablehnung ohne Journal-ID, korrekte Cash- und
Positionsfortschreibung.

### AP6 Nachbuchung und Bewertung: tools/bewertung.py
- `bewertung.py nachbuchen`: verarbeitet alle Tage seit
  `verarbeitet_bis` exakt nach regeln.md Abschnitt 6 (Reihenfolge,
  ungünstigste Annahme, Zinsen je Kalendertag, Dividenden, Splits,
  Drawdown-Stufen, Portfolio-Stopp).
- `bewertung.py bericht`: schreibt data/nav/, data/benchmark.csv und
  ranking.md mit: Portfoliowert, Rendite, Rendite gegen Benchmark,
  maximaler Drawdown, Sharpe Ratio (erst ab 60 Handelstagen, sonst
  "zu wenig Daten"), Trefferquote, Payoff-Ratio, Kostenquote,
  Exposure, Cashquote, Drawdown-Stufe.
Abnahme: Szenario-Tests aus AP9; zweimaliges Ausführen ist idempotent.

### AP7 Prüfskript: tools/pruefe.py
Unabhängige Kontrolle, Rückgabewert ungleich 0 bei Fehlern:
- Cash und Positionen lassen sich aus trades/ vollständig nachrechnen.
- Jede Order verweist auf einen Journal-Eintrag, der vor ihr erfasst
  wurde.
- Jeder Kurs in trades/ findet sich in data/kurse/ bzw. data/historie/.
- Bisherige Zeilen in trades/ und bisheriger Inhalt in journal/ sind
  gegenüber dem letzten Commit unverändert (nur Anhängen erlaubt).
- Limits waren bei jeder Ausführung eingehalten.
- config/profile.json stimmt mit der Tabelle in regeln.md überein.
- Warnung bei verwaister Session-Sperre.
Abnahme: je Prüfung ein Test, der einen manipulierten Zustand erkennt.

### AP8 Session-Sperre: tools/session.py
`session.py start --person <name>` legt session.lock an, committet und
pusht sie; `session.py ende` entfernt sie. Fremde Sperre jünger als
6 Stunden: Abbruch mit Hinweis.
Abnahme: Tests für freie, eigene, fremde und verwaiste Sperre.

### AP9 Szenario-Tests
Mindestens diese Fälle mit gemockten Tagesdaten:
1. Knock-out Long durch Kurslücke bei der Eröffnung.
2. Stop und Kursziel am selben Tag berührt: Stop gilt.
3. Market-Order am Abend, Ausführung zum nächsten Eröffnungskurs.
4. Cash-Zins über ein Wochenende (drei Kalendertage).
5. Order verletzt Exposure-Limit: abgelehnt.
6. Nachträglich geänderte Zeile in trades/: von pruefe.py erkannt.
7. Drawdown-Stufe 2: neue Zertifikate abgelehnt, Aktien erlaubt.
8. Dividende und Split auf eine Aktienposition.
9. Faktor-Zertifikat über eine Seitwärtsphase (Faktor-Effekt sichtbar).
10. Portfolio fällt unter 200 EUR: Status geschlossen.

### AP10 GitHub Action
.github/workflows/pruefung.yml führt bei jedem Push pytest und
tools/pruefe.py aus.
Abnahme: grüner Lauf auf GitHub.

### AP11 Initialisierung: tools/init.py
`init.py --startdatum JJJJ-MM-TT`: nur wenn AP1 bis AP10 abgeschlossen
sind und das Datum heute oder in der Zukunft liegt. Legt die drei
Portfolios mit 1.000 EUR an, setzt den Benchmark auf den ersten
Schlusskurs ab Startdatum, erzeugt leere Logbücher und
Anlagerichtlinien-Vorlagen in strategie/.
Abnahme: Test für Ablehnung eines Datums in der Vergangenheit.

### AP12 Testsession und Übergang
Hinweis (2026-10-06): AP12 wurde nach Phase 2 verschoben; Phase 1 gilt
mit AP1 bis AP11 als abgeschlossen (STATUS.md, Entscheidung 5).

1. Trading-Session nach CLAUDE.md vollständig durchspielen, aber ohne
   Order (Nachbuchen, Prüfen, Marktüberblick, Bericht).
2. Anlagerichtlinien in strategie/<profil>.md ausformulieren: Ziel,
   Risikobudget, Horizont, Instrumente, Benchmark, Ausgangsstrategie mit
   Begründung und aktueller Marktsicht (mit Quellen).
3. Die Auftraggeber um Freigabe bitten. Nach Freigabe: `init.py` mit
   dem Startdatum, STATUS.md auf Phase 2 setzen.
Abnahme: Freigabe der Auftraggeber in STATUS.md vermerkt.

## Nicht Teil von Phase 1
Automatischer Session-Start, Weboberfläche, Anbindung echter Broker,
reale Zertifikatskurse.

## Definition of Done
Alle Arbeitspakete in STATUS.md abgehakt, alle Tests grün, GitHub
Action grün, Testsession dokumentiert, Freigabe vorhanden.
