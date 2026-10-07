# Anlagerichtlinie Defensiv

Stand: {datum} (Standard-Richtlinie aus config/richtlinien/defensiv.md, im Auftrag der Auftraggeber
von Claude ausformuliert; Änderungen mit Datum, Anlass und Prüfkriterium, regeln.md 11).

## Ziel
Kapitalerhalt vor Rendite. Das Portfolio soll Schwankungen des Aktienmarkts deutlich dämpfen und
auf Sicht von mehreren Quartalen den Benchmark (30 % MSCI-World-ETF, 70 % verzinstes Cash) auf
risikoadjustierter Basis (Sharpe-Ratio, maximaler Drawdown) übertreffen; ein Mehrertrag in
absoluten Zahlen ist nachrangig. Rolle im Experiment: Referenz dafür, wie viel ein vorsichtiger
Ansatz gegenüber den riskanteren Profilen leistet.

## Risikobudget (regeln.md Abschnitt 7, verbindlich)
- Max. Anteil Zertifikate am Portfoliowert: {max_anteil_zertifikate}
- Max. Hebel je Zertifikat beim Kauf: {max_hebel}
- Max. Gesamt-Exposure: {max_exposure}
- Max. Einzelposition: {max_einzelposition}
- Mindest-Cashquote: {min_cashquote}
- Max. Risiko je Trade: {max_risiko_trade}
- Drawdown-Bremse: Stufe 1 bei {drawdown_stufe1}, Stufe 2 bei {drawdown_stufe2}

## Horizont
Mittel- bis langfristig: typische Haltedauer Wochen bis Monate, Kernpositionen auch länger.
Session-Rhythmus: nach Zeitplan; an Tagen ohne neue These bleibt Nichtstun die Regel, kein
Handlungszwang. Zertifikate nur kurzfristig und nur als taktische Beimischung, nie als Kern.

## Erlaubte Instrumente
- Kern: breit gestreute ETFs (Welt, Europa, USA) und Aktien großer, liquider Qualitätsunternehmen
  (hohe Marktkapitalisierung, stabile Gewinne, Dividenden) auf Xetra, NYSE und NASDAQ.
- Zertifikate: nur Faktor-Zertifikate mit niedrigem Hebel auf Indizes (DAX, Euro Stoxx 50, S&P 500,
  Nasdaq 100) und nur mit klarem Stop; Knock-outs nur mit Barriere weit vom Kurs (Puffer mindestens
  das Doppelte der erwarteten Schwankung bis zum Zeithorizont). Keine Zertifikate auf Einzelaktien.
- Nicht erlaubt: alles, was regeln.md Abschnitt 3 ausschließt.

## Ausgangsstrategie
1. **Kern-Satellit.** Zielgewicht grob: 40 bis 60 % breite ETFs, 15 bis 30 % Einzelwerte, Rest Cash
   über der Mindestquote. Cash wird mit 2 % p. a. verzinst und ist damit keine Verschwendung, sondern
   die Gegenposition zum Marktrisiko.
2. **Einstieg gestaffelt.** Positionen werden in zwei bis drei Schritten über mehrere Sessions
   aufgebaut; kein Einstieg ohne Stop und Szenarien (Bull/Base/Bear) im Journal.
3. **Risiko vor Rendite.** Positionsgröße folgt dem Risikobudget (maximales Risiko je Trade, Verlust
   bis zum Stop), nie der Überzeugung. Bei Drawdown-Stufe 1 gilt das halbierte Risiko je Trade, bei
   Stufe 2 keine neuen Zertifikate und das Pflicht-Review.
4. **Streuung.** Keine zwei Einzelwerte aus demselben Sektor und derselben Region mit zusammen mehr
   als dem Limit für Einzelpositionen; ETFs bilden den Kern.
5. **Kein Nachlegen in Verluste** ohne neue, dokumentierte These; keine Rache-Trades.
6. **Stops nur nachziehen**, nie weiter weg setzen.

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
