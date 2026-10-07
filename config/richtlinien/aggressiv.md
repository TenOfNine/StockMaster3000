# Anlagerichtlinie Aggressiv

Stand: {datum} (Standard-Richtlinie aus config/richtlinien/aggressiv.md, im Auftrag der Auftraggeber
von Claude ausformuliert; Änderungen mit Datum, Anlass und Prüfkriterium, regeln.md 11).

## Ziel
Maximale Rendite gegenüber dem Benchmark (100 % MSCI-World-ETF) innerhalb der harten Limits. Das
Profil nimmt bewusst hohe Schwankungen und Verlustphasen in Kauf, um zu prüfen, ob Hebel und
konzentrierte Positionen nach Kosten einen Mehrwert bringen. Kapitalerhalt bleibt Nebenbedingung:
Drawdown-Bremse und Risiko je Trade sind keine Verhandlungsmasse.

## Risikobudget (regeln.md Abschnitt 7, verbindlich)
- Max. Anteil Zertifikate am Portfoliowert: {max_anteil_zertifikate}
- Max. Hebel je Zertifikat beim Kauf: {max_hebel}
- Max. Gesamt-Exposure: {max_exposure}
- Max. Einzelposition: {max_einzelposition}
- Mindest-Cashquote: {min_cashquote}
- Max. Risiko je Trade: {max_risiko_trade}
- Drawdown-Bremse: Stufe 1 bei {drawdown_stufe1}, Stufe 2 bei {drawdown_stufe2}

## Horizont
Kurz- bis mittelfristig: Zertifikate über Tage bis wenige Wochen, Einzelwerte über Wochen bis
Monate. Session-Rhythmus: nach Zeitplan; schnelles Handeln bei klarem Katalysator, aber kein
Aktionismus ohne neue Information.

## Erlaubte Instrumente
- Aktien und ETFs (Xetra, NYSE, NASDAQ) mit Schwerpunkt auf Wachstum und thematischen Chancen.
- Zertifikate: Knock-out- und Faktor-Zertifikate long und short auf Indizes, Gold, Brent und
  Großwerte (Marktkapitalisierung über 10 Mrd.), Hebel bis zum Limit; jeder Hebel braucht eine
  Begründung im Journal. Knock-outs nur mit Barriere außerhalb der erwarteten Schwankung bis zum
  Zeithorizont.
- Nicht erlaubt: alles, was regeln.md Abschnitt 3 ausschließt.

## Ausgangsstrategie
1. **Überzeugung mit Risikobudget.** Konzentrierte Positionen sind erlaubt, aber das Risiko je Trade
   (Verlust bis Stop plus Kosten) bleibt unter dem Limit; die Positionsgröße folgt der Risikorechnung,
   nie der Überzeugung.
2. **Hebel gezielt.** Hohe Hebel nur bei kurzem Zeithorizont, klarem Katalysator und engem Stop;
   mittelfristige Thesen bevorzugt mit niedrigem Hebel oder als Aktie.
3. **Long und Short.** Short-Zertifikate sind erlaubt, wenn die These begründet ist (Bärenmarkt,
   überhitzte Bewertung, Katalysator); Short-Positionen gelten als Satelliten mit kurzer Haltedauer.
4. **Drawdown-Disziplin.** Bei Stufe 1 wird das Risiko je Trade halbiert, bei Stufe 2 gibt es keine
   neuen Zertifikate bis zum Pflicht-Review; die Stufen werden nicht umgangen.
5. **Kosten und Barrieren.** Knock-out-Abstand und Zinsaufschlag (Aufzinsung) gehören in die
   Risikorechnung; ein Knock-out ist ein Totalverlust des Einsatzes und wird so geplant.
6. **Kein Nachlegen in Verluste** ohne neue, dokumentierte These; keine Rache-Trades; keine Schlüsse
   aus einzelnen Trades (Glück ist kein Können).

## Benchmark
{benchmark}

## Marktsicht
Keine Prognose in dieser Richtlinie: Die aktuelle Marktsicht entsteht in jeder Session aus Kursen
(tools/kurse.py), dem News-Speicher und der Web-Suche und steht mit Quelle (URL, Datum) im
Session-Eintrag. Fakten und Einschätzungen bleiben getrennt; eine Erkenntnis aus einem einzelnen
Trade ist nur eine Hypothese (regeln.md 11).

## Änderungshistorie
| Datum | Anlass | Änderung | Prüfkriterium |
| --- | --- | --- | --- |
| {datum} | Spielstart | Standard-Richtlinie übernommen | Quartals-Review: Rendite und Risiko gegen den Benchmark, Einhaltung dieser Richtlinie |
