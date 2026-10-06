# Spielregeln v1.1

Verbindlich für alle Sessions. Änderungen nur durch Patrick und Philip
gemeinsam, per Commit mit Datum, ohne rückwirkende Anwendung. Die
maschinenlesbaren Limits stehen in config/profile.json und müssen mit
Abschnitt 7 übereinstimmen.

## 1. Grundsätze

1. Spielgeld, kein echter Handel, keine Anlageberatung.
2. **Rechnen macht Code, Entscheiden macht Claude.** Kurse, Ausführung,
   Zertifikatswerte, Zinsen, Limits und Kennzahlen kommen ausschließlich
   aus den Werkzeugen in tools/. Claude bearbeitet portfolios/, trades/
   und data/ nie von Hand.
3. **Kein Backdating.** Eine Order gilt ab dem Zeitpunkt ihrer Erfassung.
   Sie wird nie zu einem Kurs ausgeführt, der vor diesem Zeitpunkt lag.
4. Bei widersprüchlichen oder fehlenden Daten gilt die für Claude
   ungünstigere Annahme. Ohne verlässlichen Kurs wird nicht gehandelt.

## 2. Kapital und Zins

- Startkapital: 1.000 EUR je Portfolio (defensiv, ausgewogen, aggressiv).
- Startdatum: erster Handelstag nach Abschluss von Phase 1, festgelegt in
  STATUS.md. Kein festes Enddatum.
- Cash-Zins: 2 % p. a., einfache Tageszinsen (Act/365) auf den
  Cash-Endbestand jedes Kalendertags, täglich gutgeschrieben. Die
  Nachbuchung erfolgt beim nächsten Session-Start.
- Die Portfolios sind strikt getrennt; Cash und Positionen werden nie
  verschoben.

## 3. Instrumente und Universum

**Aktien und ETFs** (nur Long, Bruchstücke erlaubt)
- Börsen: Xetra (Ticker mit .DE), NYSE, NASDAQ.
- Kurs mindestens 1 EUR bzw. 1 USD, Kursdaten über das Kursskript abrufbar.

**Synthetische Zertifikate** (Long oder Short, Abschnitt 4)
- Knock-out-Zertifikate und Faktor-Zertifikate.
- Erlaubte Basiswerte: DAX (^GDAXI), Euro Stoxx 50 (^STOXX50E),
  S&P 500 (^GSPC), Nasdaq 100 (^NDX), Gold (GC=F), Brent (BZ=F) sowie
  Aktien des Universums mit einer Marktkapitalisierung über 10 Mrd.
  EUR bzw. USD.
- Erweiterungen der Liste nur durch die Auftraggeber
  (config/universum.json).

**Nicht erlaubt:** Optionen, Optionsscheine, Futures als Direktinvestment,
CFDs, Kryptowerte, Direkt-Leerverkauf, Kredit.

## 4. Synthetische Zertifikate

Zertifikate werden nicht mit realen Emittentenkursen, sondern nach festen
Formeln aus dem Basiswert berechnet. Das macht sie reproduzierbar und
prüfbar. Werte in Fremdwährung werden über EURUSD=X in EUR umgerechnet.

**Knock-out Long** (Zielhebel L beim Kauf, Basiswertkurs S)
- Basispreis beim Kauf: K = S * (1 - 1/L); Barriere B = K.
- Täglich: K wird mit 4 % p. a. aufgezinst (K * (1 + 0,04/365) je
  Kalendertag).
- Wert je Stück: S - K. Knock-out, sobald das Tagestief B erreicht oder
  unterschreitet; die Position ist dann wertlos.

**Knock-out Short**
- Basispreis beim Kauf: K = S * (1 + 1/L); Barriere B = K.
- K bleibt konstant (Referenzzins 2 % minus Finanzierungsaufschlag 2 %).
- Wert je Stück: K - S. Knock-out, sobald das Tageshoch B erreicht oder
  überschreitet.

**Faktor Long/Short** (Faktor F)
- Tageswert: V_t = V_(t-1) * max(0, 1 + F * R_t - 0,02/365), mit
  R_t = Tagesrendite des Basiswerts (bei Short: -F).
- Am Kauf- und Verkaufstag wird R ab bzw. bis zum Ausführungskurs
  berechnet. Intraday-Resets werden nicht modelliert.

**Gemeinsam**
- Stückzahl = Einsatz / Wert je Stück beim Kauf.
- Hebel eines Knock-outs zu jedem Zeitpunkt: S / (S - K) bzw. S / (K - S).
- Stops und Kursziele werden auf den Basiswert gesetzt.
- Am Kauftag zählt für Barriere und Stop das gesamte Tageshoch und
  Tagestief (konservativ).

## 5. Kurse, Handelszeiten, Kosten

- Alle Kurse kommen aus tools/kurse.py und werden mit Zeitstempel und
  Quelle in data/kurse/ protokolliert. Buchungen nur zu protokollierten
  Kursen. Die Web-Suche dient nur für News und Hintergründe.
- Handelszeiten (deutsche Zeit): Xetra-Werte, DAX, Euro Stoxx 50
  09:00 bis 17:30; US-Werte, S&P 500, Nasdaq 100 zu den Handelszeiten
  der NYSE (09:30 bis 16:00 New Yorker Zeit); Gold und Brent
  Montag bis Freitag 08:00 bis 22:00.
- Market-Order während der Handelszeit: Ausführung zum aktuellen
  protokollierten Kurs. Außerhalb der Handelszeit: Ausführung zum
  Eröffnungskurs des nächsten Handelstags.
- Spread: Aktien und ETFs 0,10 %, Zertifikate 0,20 % (je zur Hälfte auf
  Kauf und Verkauf).
- Gebühr: 1 EUR je ausgeführter Order.
- Mindestorder: 100 EUR Einsatz.

## 6. Orderarten und Nachbuchung

Orderarten: Market, Limit, Stop-Loss, Kursziel (Take-Profit). Stops und
Kursziele gehören zu einer Position.

Beim Session-Start werden alle Handelstage seit der letzten Verarbeitung
in dieser Reihenfolge nachgebucht:
1. Vorgemerkte Market-Orders zum Eröffnungskurs ausführen (Limits werden
   erneut geprüft; bei Verstoß verfällt die Order mit Vermerk).
2. Limit-Orders: Liegt die Eröffnung bereits jenseits des Limits, zum
   Eröffnungskurs; sonst bei Berührung zum Limit.
3. Offene Positionen: Wird Barriere, Stop oder Kursziel schon durch die
   Eröffnung überschritten, gilt der Eröffnungskurs. Werden im Tagesverlauf
   mehrere berührt, gilt das schlechteste Ergebnis (Knock-out vor Stop vor
   Kursziel).
4. Zum Tagesschluss: Basispreise aufzinsen, Faktor-Werte fortschreiben,
   Dividenden und Splits buchen, Cash-Zins buchen, Tageswert speichern.

## 7. Profile und Risikolimits

| Parameter | Defensiv | Ausgewogen | Aggressiv |
| --- | --- | --- | --- |
| Max. Anteil Zertifikate am Portfoliowert | 10 % | 30 % | 70 % |
| Max. Hebel je Zertifikat (beim Kauf) | 3x | 5x | 10x |
| Max. Gesamt-Exposure | 1,2x | 2,0x | 4,0x |
| Max. Einzelposition (Marktwert) | 20 % | 25 % | 35 % |
| Mindest-Cashquote | 10 % | 5 % | 0 % |
| Max. Risiko je Trade | 1 % | 2 % | 5 % |
| Drawdown-Bremse Stufe 1 | -8 % | -12 % | -20 % |
| Drawdown-Bremse Stufe 2 | -15 % | -20 % | -35 % |
| Benchmark | 30 % ETF / 70 % Cash | 60 % / 40 % | 100 % ETF |

Begriffe:
- **Gesamt-Exposure** = Summe aus Positionswert mal Hebel, geteilt durch
  den Portfoliowert (Aktien und ETFs Hebel 1).
- **Risiko je Trade** = Einsatz mal relativer Verlust bis zum Stop plus
  zwei Gebühren plus Spreadkosten, in Prozent des Portfoliowerts. Ohne
  Stop gilt als Verlust: Aktien und ETFs 20 % des Einsatzes, Zertifikate
  100 %.
- **Drawdown** = Rückgang vom bisherigen Höchststand des Portfoliowerts.
  Stufe 1: Risiko je Trade halbiert. Stufe 2: keine neuen Zertifikate,
  Pflicht-Review. Eine Stufe endet, wenn der Drawdown wieder unter der
  Hälfte ihrer Schwelle liegt; Stufe 2 zusätzlich erst nach dem Review.
- Limits gelten bei Erfassung und bei Ausführung einer Order. Spätere
  Überschreitungen durch Kursbewegung erzwingen keinen Verkauf, aber
  neue Käufe müssen das Portfolio wieder Richtung Limit bewegen.

**Portfolio-Stopp:** Fällt ein Portfolio unter 200 EUR, wird es
geschlossen und ausgewertet. Ein Neustart braucht die Zustimmung beider
Auftraggeber; die Historie bleibt erhalten.

## 8. Dividenden, Kapitalmaßnahmen, Währung

- Aktien und ETFs: Bruttodividenden am Ex-Tag gutgeschrieben, Splits
  automatisch angepasst (Daten aus dem Kursskript). Keine Steuern.
- Zertifikate: Dividenden des Basiswerts werden nicht berücksichtigt.
- Fremdwährung: Umrechnung zum protokollierten EURUSD-Kurs, ohne Gebühr.

## 9. Benchmarks

- ETF: iShares Core MSCI World UCITS ETF (EUNL.DE, IE00B4L5Y983).
- Cash-Anteil verzinst mit 2 % p. a. wie in Abschnitt 2.
- Einmalige Aufteilung zum Startdatum, ohne Rebalancing und ohne Kosten.

## 10. Dokumentationspflichten

- Vor jeder Order steht ein Journal-Eintrag mit eindeutiger ID
  (J-JJJJMMTT-NN) in journal/JJJJ-MM-TT_<person>.md. Jede Order
  verweist auf diese ID.
- Ein Eintrag enthält: Portfolio, Instrument, These, Szenarien
  (Bull/Base/Bear mit groben Wahrscheinlichkeiten), Katalysator,
  Zeithorizont, Einstieg, Stop, Kursziel, Positionsgröße mit
  Risikorechnung, Quellen mit URL und Datum.
- Journal und Logbücher werden nur am Ende ergänzt, nie geändert.
  Korrekturen erfolgen als neuer Eintrag mit Verweis.
- Fakten mit Quelle, Einschätzungen als solche markiert, Unsicherheit
  ausdrücklich benannt.

## 11. Strategie, Reviews, Lernen

- Je Portfolio eine Anlagerichtlinie in strategie/<portfolio>.md: Ziel,
  Risikobudget, Horizont, erlaubte Instrumente, Benchmark, aktuelle
  Strategie. Änderungen mit Datum, Anlass und Prüfkriterium.
- Wochenreview: in der ersten Session einer neuen Kalenderwoche für die
  Vorwoche, in reviews/.
- Monatsvergleich der drei Profile, Meta-Review jedes Quartal.
- Erkenntnisse in lessons.md. Eine Erkenntnis aus einem einzelnen Trade
  bleibt Hypothese.

## 12. Sessions

- Eine Session startet ein Auftraggeber. Es läuft nie mehr als eine
  Session gleichzeitig: Sperrdatei session.lock (Person, Startzeit), die
  nach 6 Stunden als verwaist gilt.
- Claude entscheidet autonom innerhalb dieser Regeln. Ideen der
  Auftraggeber prüft Claude kritisch und begründet seine Entscheidung.
- Claude ändert diese Regeln nie und umgeht keine Prüfung. Bei
  Unklarheiten fragt Claude nach und vermerkt die Entscheidung in
  STATUS.md.

## 13. Bekannte Vereinfachungen

- Synthetische Zertifikate statt realer Emittentenprodukte; kein
  Emittentenrisiko, keine Intraday-Resets, keine Dividendenanpassung.
- Tagesdaten statt Intraday-Verlauf für Stops und Barrieren.
- Feste Spreads und Gebühren, unabhängig von Markt und Volumen.
- Kursdaten aus einer frei verfügbaren Quelle, die verzögert oder
  lückenhaft sein kann.
