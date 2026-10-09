# Anlagerichtlinie Overnight

Stand: {datum} (Standard-Richtlinie v{version} aus config/richtlinien/overnight.md, im Auftrag der Auftraggeber
von Claude ausformuliert; Änderungen mit Datum, Anlass und Prüfkriterium, regeln.md 11).

## Ziel
Testen, ob sich die Rendite zwischen Handelsschluss und nächster Eröffnung nach Kosten abschöpfen lässt:
Kauf zum Schlusskurs, Verkauf zum Eröffnungskurs des nächsten Handelstags, tagsüber Cash. Benchmark ist der
MSCI-World-ETF (100 %). Das Profil ist ein Experiment mit einer ehrlichen Ausgangshypothese (unten): Es soll
zeigen, ob die Nacht-Rendite die festen Kosten trägt, und darf das Ergebnis auch verneinen.

## Risikobudget (regeln.md Abschnitt 7, verbindlich)
- Max. Anteil Zertifikate am Portfoliowert: {max_anteil_zertifikate}
- Max. Hebel je Zertifikat beim Kauf: {max_hebel}
- Max. Gesamt-Exposure: {max_exposure}
- Max. Einzelposition: {max_einzelposition}
- Mindest-Cashquote: {min_cashquote}
- Max. Risiko je Trade: {max_risiko_trade}
- Drawdown-Bremse: Stufe 1 bei {drawdown_stufe1}, Stufe 2 bei {drawdown_stufe2}

## Mechanik: Daueranweisung statt Session-Handel
Claude handelt hier nicht jede Nacht, sondern setzt in einer Session eine **Daueranweisung** (`python
tools/daueranweisung.py setzen ...`, mit Journal-ID wie bei jeder Order): Instrumente und Gewichte, Einsatz,
Gültigkeit, Aussetzkriterien. Der Hintergrunddienst führt sie ohne Claude-Lauf aus (regeln.md 5 und 6): Kauf
zum Schlusskurs der Börse, Verkauf zum Eröffnungskurs des nächsten Handelstags, solange die Anweisung gültig und
nicht ausgesetzt ist; ohne gültige Anweisung geschieht nichts. Wochenenden und Feiertage folgen dem Börsenkalender.
Kurse, Kosten und Limits sind dieselben wie in den anderen Portfolios, die Kosten werden nie gesenkt.

## Erlaubte Instrumente
- Breite, liquide Index-ETFs (S&P 500, Nasdaq-100, MSCI World, DAX) an Xetra, NYSE und NASDAQ; wenige,
  konzentrierte Positionen (am günstigsten eine, siehe Kosten).
- Knock-out-Zertifikate nur mit mäßigem Hebel (bis zum Limit {max_hebel}) und Barriere mit Puffer von mindestens
  dem Dreifachen der 5-%-Quantil-Lücke des Basiswerts (`python tools/overnight.py ergebnis`). Faktor-Zertifikate
  sind für Daueranweisungen nicht vorgesehen.
- Nicht erlaubt: alles, was regeln.md Abschnitt 3 ausschließt.

## Ausgangshypothese und Kostenrechnung (zu prüfen, nicht vorausgesetzt)
**Kosten je Nacht** (regeln.md 5: 1 EUR je Order, Spread ETF 0,10 %, Zertifikat 0,20 % je Kauf und Verkauf zusammen)
bei 1.000 EUR: eine ETF-Position (970 EUR) kostet 2 EUR Gebühr plus rund 1 EUR Spread, also **0,31 %** des Einsatzes
pro Nacht; zwei Positionen 0,51 %; ein Knock-out-Zertifikat mit Hebel 3 auf 300 EUR 0,89 % des Einsatzes, was auf
den Basiswert umgerechnet ebenfalls **0,30 %** pro Nacht bedeutet (die festen Gebühren fressen den Hebel). `python tools/overnight.py kosten` rechnet es für jede Variante vor.

**Hypothese H-OVERNIGHT-1:** Die durchschnittliche Rendite breiter Indizes zwischen Schluss und Eröffnung liegt
nach allgemeiner Erwartung (nicht in diesem Spiel überprüft) bei wenigen hundertstel Prozent pro Nacht, also eine
Größenordnung unter den rund 0,3 % Kosten. Dann ist jede Daueranweisung nach Kosten im Erwartungswert negativ.
Prüfkriterium: `python tools/overnight.py ergebnis` (Rückblick über ein Jahr aus config/beobachtung.json, Kosten
des Spiels, Train/Test-Aufteilung) zeigt für das Instrument eine mittlere **Netto**-Rendite je Nacht über null
sowohl im Trainings- als auch im Testzeitraum und ein 5-%-Quantil, das der Drawdown-Bremse standhält.

## Ausgangsstrategie
1. **Erst messen, dann setzen.** Vor jeder Daueranweisung `python tools/overnight.py ergebnis` lesen und die
   Zahlen im Journal nennen. Zeigt kein Instrument im Testzeitraum einen positiven Erwartungswert nach Kosten, gilt
   Ausnahme (a) aus regeln.md 12: keine Anweisung, belegt mit den Zahlen (Netto-Rendite je Nacht, Kosten je Nacht,
   Verlust bis Stop gegen Limit, geprüfte Instrumente). Das ist ein gültiges Ergebnis des Experiments.
2. **Günstigste Variante zuerst.** Eine Position (Gebühr 2 EUR je Nacht statt 4), breites ETF, Einsatz bis zur
   Mindest-Cashquote; wenn die Messung es stützt, nur lange Nächte (Wochenende, Feiertag: `nur_lange_naechte`),
   weil dieselben Kosten dann mehr Nacht-Rendite einfangen.
3. **Aussetzen ist Pflicht.** Jede Anweisung trägt Aussetzkriterien (Drawdown-Stufe, Verlustserie, Portfoliowert
   unten); nach dem Aussetzen gibt es nur mit neuer, dokumentierter These eine neue Anweisung.
4. **Lücken-Risiko ernst nehmen.** Nachts gibt es keinen Stop; das 5-%-Quantil der Eröffnungslücke ist das
   Risiko je Nacht. Knock-outs nur, wenn die Barriere weit außerhalb davon liegt.
5. **Kein Nachlegen in Verluste** ohne neue, dokumentierte These; keine Schlüsse aus einzelnen Nächten.

## Benchmark
{benchmark}

## Marktsicht
Keine Prognose in dieser Richtlinie: Die Marktsicht entsteht in jeder Session aus Kursen (tools/kurse.py), dem
News-Speicher und der Web-Suche und steht mit Quelle (URL, Datum) im Session-Eintrag. Fakten und Einschätzungen
bleiben getrennt.

## Änderungshistorie
| Datum | Anlass | Änderung | Prüfkriterium |
| --- | --- | --- | --- |
| {datum} | Spielstart | Standard-Richtlinie v{version} übernommen | Quartals-Review: Netto-Rendite je Nacht gegen die Kosten, Einhaltung dieser Richtlinie |
