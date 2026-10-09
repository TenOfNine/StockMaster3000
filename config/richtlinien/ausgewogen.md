# Anlagerichtlinie Ausgewogen

Stand: {datum} (Standard-Richtlinie v{version} aus config/richtlinien/ausgewogen.md, im Auftrag der Auftraggeber
von Claude ausformuliert; Änderungen mit Datum, Anlass und Prüfkriterium, regeln.md 11).

## Ziel
Solide Mehrrendite gegenüber dem Benchmark (60 % MSCI-World-ETF, 40 % verzinstes Cash) bei
kontrolliertem Risiko: ein höheres Ergebnis als beim defensiven Profil, aber mit klar begrenzten
Verlusten. Rolle im Experiment: Mitte der drei Profile; prüft, ob moderate, taktische Zusatzrisiken
(Einzelwerte, Faktor-Zertifikate) über dem Kern nach Kosten einen Mehrwert bringen.

## Risikobudget (regeln.md Abschnitt 7, verbindlich)
- Max. Anteil Zertifikate am Portfoliowert: {max_anteil_zertifikate}
- Max. Hebel je Zertifikat beim Kauf: {max_hebel}
- Max. Gesamt-Exposure: {max_exposure}
- Max. Einzelposition: {max_einzelposition}
- Mindest-Cashquote: {min_cashquote}
- Max. Risiko je Trade: {max_risiko_trade}
- Drawdown-Bremse: Stufe 1 bei {drawdown_stufe1}, Stufe 2 bei {drawdown_stufe2}

## Horizont
Mittelfristig: typische Haltedauer Tage bis Monate für Einzelwerte, Wochen bis Monate für
ETF-Positionen; Zertifikate taktisch über Tage bis wenige Wochen. Session-Rhythmus: nach Zeitplan;
Handeln ist der Normalfall; Cash ist die Ausnahme, die im Session-Eintrag belegt wird.

## Erlaubte Instrumente
- ETFs und Aktien aus dem erlaubten Universum (Xetra, NYSE, NASDAQ) als Kern und Satelliten.
- Zertifikate: Faktor-Zertifikate und Knock-outs auf Indizes, Gold, Brent und liquide Großwerte
  (Marktkapitalisierung über 10 Mrd.), Hebel im Rahmen des Limits, bevorzugt unter dem Maximum;
  Knock-out-Barrieren mit angemessenem Puffer, immer mit Stop.
- Nicht erlaubt: alles, was regeln.md Abschnitt 3 ausschließt.

## Ausgangsstrategie
1. **Kern und Satelliten.** Rund die Hälfte in breite ETFs als Kern, der Rest in Einzelwerte mit
   klarer These und in begrenzte, taktische Zertifikatspositionen. Das Zertifikatslimit ist eine
   Obergrenze, kein Ziel.
2. **Investiert bleiben.** Zielgewicht: Cashquote nahe der Mindestquote (5 %); höhere Cashquote nur mit Grund.
   Auf eine Order wird nur verzichtet, wenn keine Order alle Limits einhält und nach Kosten einen positiven
   Erwartungswert hat, bei Drawdown-Stufe 2 oder Portfolio-Stopp und ohne verlässlichen Kurs (regeln.md 12).
3. **These vor Position.** Jede Order hat Katalysator, Zeithorizont, Szenarien, Stop und Kursziel im
   Journal; ohne Stop und Risikorechnung wird nicht gekauft.
4. **Risiko je Trade** nach Risikobudget; Positionen nur so groß, dass Risiko je Trade und
   Gesamt-Exposure unter dem Limit bleiben. Bei Drawdown-Stufe 1 wird kleiner gehandelt, bei Stufe 2
   gibt es keine neuen Zertifikate.
5. **Streuung.** Nicht mehr als zwei Satelliten mit demselben Marktfaktor (z. B. zwei Halbleiterwerte
   plus ein Nasdaq-Zertifikat); die Korrelation wird im Journal benannt.
6. **Kosten beachten.** Spreads und Gebühren sind Teil der These: kein Trade, dessen erwarteter
   Gewinn nach Kosten kleiner als das Doppelte der Kosten ist.
7. **Kein Nachlegen in Verluste** ohne neue, dokumentierte These; keine Rache-Trades.

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
| {datum} | Spielstart | Standard-Richtlinie v{version} übernommen | Quartals-Review: Rendite und Risiko gegen den Benchmark, Einhaltung dieser Richtlinie |
