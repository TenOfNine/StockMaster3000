# Spielregeln v1.4

Verbindlich für alle Sessions. Änderungen nur durch die Auftraggeber
(config/projekt.json) gemeinsam, per Commit mit Datum, ohne rückwirkende
Anwendung. Die
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
- Spielbeginn: Das Spiel beginnt in dem Moment, in dem es gestartet wird:
  durch den ersten Trading-Lauf oder von Hand (tools/init.py, in der App
  Einrichtung → Spielstart). Der Starttag ist der heutige Kalendertag; ein
  vorab festgelegtes Start- oder Enddatum gibt es nicht. Die Freigabe nach
  AP12 gibt der Auftraggeber, der den Lauf startet. Das gespeicherte
  Startdatum (spiel.json) ist nur der Bezugspunkt der Auswertung. Feste
  Termine gibt es ausschließlich im Zeitplan geplanter Claude-Läufe
  (Einrichtung → Zeitplan); sie wirken nicht auf Bewertung, Benchmark,
  Reviews oder Limits. Ein noch unberührtes Startdatum (keine Buchung,
  Order, Position, Nachbuchung oder Bewertung) darf auf heute vorgezogen
  werden, nie in die Vergangenheit.
- Ein Arbeitsbereich ist eine eigenständige Spielinstanz mit eigenem
  Repository, eigenen drei Portfolios und eigenen Auftraggebern. Diese
  Regeln gelten je Arbeitsbereich; Arbeitsbereiche sind strikt getrennt.
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

**Schwerpunkt je Arbeitsbereich** (optional)
- Die Auftraggeber können das Universum eines Arbeitsbereichs in
  config/schwerpunkt.json weiter einschränken, nie erweitern: Region
  (Firmensitz), Handelsplatz, Sektor, erlaubte Basiswerte für
  Zertifikate, erlaubte ETFs.
- Durchsetzung "verbindlich": Käufe, die nicht passen, werden bei
  Erfassung und Ausführung von tools/limits.py abgelehnt; fehlende oder
  unbekannte Stammdaten gelten als nicht passend. Durchsetzung
  "Leitlinie": keine Ablehnung, Claude begründet jede Abweichung im
  Journal.
- Anlagestil und Themen sind Leitlinien für Claude, keine prüfbaren
  Limits.
- Ohne config/schwerpunkt.json gilt keine zusätzliche Einschränkung.
- Änderungen mit Datum und ohne Rückwirkung; bestehende Positionen
  müssen nicht verkauft werden, neue Käufe müssen passen.

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
  protokollierten Kurs. Außerhalb der Handelszeit: Vormerkung und
  Ausführung bei der nächsten Gelegenheit, ohne dass ein Claude-Lauf
  nötig ist: Der Hintergrunddienst führt sie zum ersten protokollierten
  Kurs nach der Eröffnung aus (Kurszeit der Quelle nach Eröffnung und
  höchstens 30 Minuten danach). Liegt kein solcher Kurs vor, führt die
  Nachbuchung (Abschnitt 6) sie zum Eröffnungskurs des Handelstags aus.
- Ausführung ohne Claude-Lauf: tools/ausfuehrung.py läuft im Takt von
  5 Minuten bei offenem Markt sowie kurz nach Öffnung und kurz vor
  Schluss jeder Börse (Zeitzone, Sommerzeit, Feiertage und verkürzte
  Handelstage laut config/universum.json). Die Order gilt erst ab ihrer
  Erfassung (Grundsatz 3). Ohne verlässlichen Kurs (Grundsatz 4, Kursalter
  höchstens 30 Minuten) wird nicht ausgeführt; der nächste Durchlauf
  versucht es erneut.
- Spread: Aktien und ETFs 0,10 %, Zertifikate 0,20 % (je zur Hälfte auf
  Kauf und Verkauf).
- Gebühr: 1 EUR je ausgeführter Order.
- Mindestorder: 100 EUR Einsatz.

## 6. Orderarten und Nachbuchung

Orderarten: Market, Limit, Stop-Loss, Kursziel (Take-Profit). Stops und
Kursziele gehören zu einer Position.

**Tagsüber (Ausführung ohne Claude-Lauf).** Je Durchlauf von
tools/ausfuehrung.py, jeweils zum protokollierten Kurs des Durchlaufs:
1. Vorgemerkte Market-Orders (Abschnitt 5), Limit-Orders bei Kurs auf oder
   besser als das Limit; älteste Order zuerst.
2. Offene Positionen: Knock-out (Kurs auf oder jenseits der Barriere) vor
   Stop vor Kursziel. Ein Stop wird so nie besser als der Stop
   ausgeführt, ein Kursziel nie schlechter als das Kursziel. Stop und
   Kursziel einer Position schließen sich aus (wer zuerst auslöst, schließt
   die Position).
Vor jeder Ausführung prüft der Code die Limits erneut (Verstoß: die Order
verfällt mit Vermerk). Jede Buchung trägt die ursprüngliche Journal-ID und
in der Bemerkung "automatisch (Auslöser: ...)". Ein ganzer Buchungsvorgang
läuft unter der Buchungssperre (.buchungssperre, unabhängig von der
Session-Sperre; auch buchen.py und die Nachbuchung nehmen sie), und eine
Order wird höchstens einmal ausgeführt. Solange Tage der Nachbuchung
ausstehen, führt der Hintergrunddienst nicht aus, damit die Reihenfolge der
Tage stimmt.

**Nachbuchung als Abgleich.** Beim Session-Start und nachts um 00:30 Uhr
werden alle Handelstage seit der letzten Verarbeitung in dieser
Reihenfolge nachgebucht (nur, was kein Durchlauf erfasst hat; vorhandene
Buchungen ändert sie nie). Weichen die Tageskerzen von einer automatischen
Ausführung ab (Kurs außerhalb von Tageshoch und -tief), meldet sie das.
Zwischen zwei Durchläufen berührte Barrieren, Stops und Kursziele holt sie
mit der ungünstigeren Annahme nach:
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
geschlossen und ausgewertet. Ein Neustart braucht die Zustimmung aller
Auftraggeber; die Historie bleibt erhalten.

## 8. Dividenden, Kapitalmaßnahmen, Währung

- Aktien und ETFs: Bruttodividenden am Ex-Tag gutgeschrieben, Splits
  automatisch angepasst (Daten aus dem Kursskript). Keine Steuern.
- Zertifikate: Dividenden des Basiswerts werden nicht berücksichtigt.
- Fremdwährung: Umrechnung zum protokollierten EURUSD-Kurs, ohne Gebühr.

## 9. Benchmarks

- ETF: iShares Core MSCI World UCITS ETF (EUNL.DE, IE00B4L5Y983).
- Cash-Anteil verzinst mit 2 % p. a. wie in Abschnitt 2.
- Einmalige Aufteilung zum ersten Schlusskurs ab dem Starttag, ohne
  Rebalancing und ohne Kosten.

## 10. Dokumentationspflichten

- Vor jeder Order steht ein Journal-Eintrag mit eindeutiger ID
  (J-JJJJMMTT-NN) in journal/JJJJ-MM-TT_<kennung>.md. Jede Order
  verweist auf diese ID.
- Ein Eintrag enthält: Portfolio, Instrument, These, Szenarien
  (Bull/Base/Bear mit groben Wahrscheinlichkeiten), Katalysator,
  Zeithorizont, Einstieg, Stop, Kursziel, Positionsgröße mit
  Risikorechnung, Quellen mit URL und Datum.
- Journal und Logbücher werden nur am Ende ergänzt, nie geändert.
  Korrekturen erfolgen als neuer Eintrag mit Verweis.
- Fakten mit Quelle, Einschätzungen als solche markiert, Unsicherheit
  ausdrücklich benannt.
- Jede Session endet mit einem Session-Eintrag (S-JJJJMMTT-NN) im
  Journal: je Portfolio die Entscheidung, erwogene und verworfene
  Alternativen und die Begründung, dazu je Portfolio die Order (Journal-ID)
  oder die belegte Ausnahme nach Abschnitt 12 (Pflichtzeile "Handlung oder
  Ausnahme").
- Im Repository stehen keine Namen oder personenbezogenen Daten.
  Personen erscheinen nur als neutrale Kennung (config/projekt.json).

## 11. Strategie, Reviews, Lernen

- Je Portfolio eine Anlagerichtlinie in strategie/<portfolio>.md: Ziel,
  Risikobudget, Horizont, erlaubte Instrumente, Benchmark, aktuelle
  Strategie. Änderungen mit Datum, Anlass und Prüfkriterium.
- Reviews richten sich nach der Spielzeit, nicht nach dem Kalender. Ab
  dem Starttag zählen Zeiträume zu je 7 Tagen. Wochenreview: in der
  ersten Session nach Ablauf eines 7-Tage-Zeitraums, in reviews/.
  Monatsvergleich der drei Profile nach je 4 Wochen (28 Tage),
  Meta-Review nach je 13 Wochen (91 Tage).
- Erkenntnisse in lessons.md. Eine Erkenntnis aus einem einzelnen Trade
  bleibt Hypothese.

## 12. Sessions

- Eine Session startet ein Auftraggeber oder ein Mitglied mit
  Vollzugriff auf den Arbeitsbereich; Sperre und Journal tragen die
  Kennung des Auftraggebers. Es läuft nie mehr als eine
  Session gleichzeitig: Sperrdatei session.lock (Kennung, Startzeit), die
  nach 6 Stunden als verwaist gilt.
- Eine Session ist an kein Datum, keinen Wochentag, keine Uhrzeit und kein
  Startdatum gebunden: Manuell und geplant startet sie jederzeit, und der
  Lauf macht seine Trades bzw. plant die Strategie. Ein geplanter Lauf wird
  nie übersprungen; ist gerade eine Session aktiv, wartet er sichtbar und
  startet danach. Orders außerhalb der Handelszeit werden vorgemerkt und bei
  nächster Gelegenheit ausgeführt (Abschnitt 5 und 6).
- Claude entscheidet autonom innerhalb dieser Regeln. Ideen der
  Auftraggeber prüft Claude kritisch und begründet seine Entscheidung.
- **Handeln hat Vorrang.** Handeln ist der Normalfall, Cash die Ausnahme;
  Nichthandeln ist nicht neutral, denn Cash bringt nur 2 % Zins p. a.
  (Abschnitt 2). Die harten Limits (Abschnitt 7, config/profile.json) sind
  die Risikoleitplanken, kein Grund zu verzichten.
- **Verzicht auf eine Order** ist je Session und Portfolio nur zulässig,
  wenn (a) keine Order existiert, die alle harten Limits einhält und deren
  Szenario-Erwartungswert nach Kosten positiv ist, (b) das Portfolio in
  Drawdown-Stufe 2 oder gestoppt ist (Abschnitt 7) oder (c) kein verlässlicher
  Kurs vorliegt (Abschnitt 1, Grundsatz 4). Andere Gründe tragen nicht.
- **Beweislast:** Je Session und Portfolio steht im Session-Eintrag
  mindestens eine konkrete Order (Journal-ID) oder die belegte Ausnahme mit
  Zahlen: Verlust bis Stop gegen das Limit, Erwartungswert nach Kosten und
  die geprüften Screener-Kandidaten. Eine Ausnahme ohne Zahlen zählt nicht.
  Zielwert für die Cashquote ist die Mindest-Cashquote des Profils; höher
  nur mit Grund im Session-Eintrag. pruefe.py und das Cockpit warnen (kein
  Fehler) bei dauerhaft hoher Cashquote und bei einer Session ohne Order und
  ohne belegte Ausnahme (nur für Sessions ab dem Stichtag in
  config/projekt.json, keine Rückwirkung).
- **Kosten** (Abschnitt 5: 1 EUR je Order, Spreads, Mindestorder 100 EUR)
  bleiben Teil der Abwägung. Es wird nicht gehandelt, um zu handeln:
  Churning ist kein Ziel.
- Claude ändert diese Regeln nur im ausdrücklichen Auftrag der
  Auftraggeber und umgeht keine Prüfung. Bei Unklarheiten entscheidet
  Claude nach bestem Wissen im Sinne des größten Nutzens im Spiel, ohne
  Integrität und Prüfspur zu lockern, und vermerkt Frage und Entscheidung in
  STATUS.md; die Auftraggeber können jede Entscheidung später ändern.

## 13. Bekannte Vereinfachungen

- Synthetische Zertifikate statt realer Emittentenprodukte; kein
  Emittentenrisiko, keine Intraday-Resets, keine Dividendenanpassung.
- Tagesdaten statt Intraday-Verlauf für Stops und Barrieren.
- Feste Spreads und Gebühren, unabhängig von Markt und Volumen.
- Kursdaten aus einer frei verfügbaren Quelle, die verzögert oder
  lückenhaft sein kann.

## 14. Änderungshistorie

- v1.1: Ausgangsfassung nach Konzept-Review.
- v1.2 (2026-10-06): Auftraggeber als neutrale Kennungen; Startdatum erst
  nach Freigabe von AP12; Arbeitsbereiche und Schwerpunkt je
  Arbeitsbereich; Session-Start durch Mitglieder mit Vollzugriff;
  Session-Eintrag und Datenschutz in der Dokumentation. Einmalig von
  Claude im Auftrag der Auftraggeber geändert (STATUS.md, Entscheidung 10).
- v1.3 (2026-10-07): Kein fester Start- oder Endtermin des Spiels (Start
  beim Spielstart, Starttag ist heute); feste Termine nur noch für den
  Zeitplan geplanter Läufe; Reviews nach Spielzeit (7, 28 und 91 Tage)
  statt nach Kalender; Claude entscheidet Unklarheiten selbst und
  dokumentiert sie. Im Auftrag der Auftraggeber von Claude geändert
  (STATUS.md, Entscheidung 34).
- v1.4 (2026-10-09, Umbau v2, im Auftrag der Auftraggeber von Claude
  geändert, STATUS.md Entscheidungen 40 bis 45): Sessions sind an kein
  Datum, keinen Wochentag und keine Uhrzeit gebunden, geplante Läufe werden
  nie übersprungen, der erste Trading-Lauf startet das Spiel (Abschnitte 2
  und 12); Handeln hat Vorrang vor Cash mit enger Definition des Verzichts
  und umgekehrter Beweislast (Abschnitte 10 und 12; ersetzt "Kapitalerhalt
  vor Rendite" und "Nichtstun ist gültig"); Ausführung vorgemerkter Orders,
  Limits, Stops, Kursziele und Barrieren ohne Claude-Lauf durch den
  Hintergrunddienst, Nachbuchung als Abgleich (Abschnitte 5 und 6).
