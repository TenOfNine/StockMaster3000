import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Legende } from "@/components/diagramme/NavDiagramm";
import { mitIntervall } from "@/components/Labor";
import { Abzeichen, Fehleranzeige, Karte, KarteKopf, Leer, Seitenkopf, Skelett } from "@/components/ui";
import { api, type LaborBericht, type LaborBerichtKopf, type LaborKennzahlen } from "@/lib/api";
import { cn } from "@/lib/cn";
import { datum, prozent, zahl } from "@/lib/format";

const ZEILEN: { name: string; wert: (k: LaborKennzahlen) => string }[] = [
  { name: "Rendite p. a.", wert: (k) => mitIntervall(k.rendite_pa, "prozent") },
  { name: "Überrendite p. a. gegen Benchmark", wert: (k) => mitIntervall(k.ueberrendite_pa, "prozent", true) },
  { name: "Sharpe Ratio", wert: (k) => mitIntervall(k.sharpe, "zahl") },
  { name: "Information Ratio", wert: (k) => mitIntervall(k.information_ratio, "zahl") },
  { name: "Alpha p. a.", wert: (k) => mitIntervall(k.alpha_pa, "prozent", true) },
  { name: "Beta", wert: (k) => mitIntervall(k.beta, "zahl") },
  { name: "Sortino", wert: (k) => mitIntervall(k.sortino, "zahl") },
  { name: "Calmar", wert: (k) => mitIntervall(k.calmar, "zahl") },
  { name: "Max. Drawdown", wert: (k) => (k.max_drawdown != null ? prozent(k.max_drawdown, false, 1) : "–") },
];

function Kurve({ b }: { b: LaborBericht }) {
  const daten = b.kurve.tage.map((t, i) => ({ t, strategie: b.kurve.strategie[i], benchmark: b.kurve.benchmark[i] }));
  const oos = b.out_of_sample.von;
  return (
    <div>
      <div className="px-4 pb-2">
        <Legende eintraege={[{ name: "Strategie", farbe: "var(--text-2)" }, { name: "Benchmark (Buy & Hold)", farbe: "var(--benchmark)", gestrichelt: true }]} />
      </div>
      <div className="h-[320px] px-2 pb-4" role="img" aria-label="Wertentwicklung der Strategie gegen die Benchmark, In-Sample links und Out-of-Sample rechts der Linie">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={daten} margin={{ top: 12, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--raster)" />
            <XAxis dataKey="t" tickFormatter={(t: string) => t.slice(0, 7)} minTickGap={40} tickLine={false} />
            <YAxis width={44} domain={["auto", "auto"]} tickLine={false} axisLine={false} />
            <Tooltip formatter={(w) => zahl(w as number)} labelFormatter={(t) => datum(String(t))} />
            {oos && <ReferenceLine x={oos} stroke="var(--text-3)" strokeDasharray="4 4" label={{ value: "Out-of-Sample", position: "insideTopRight", fontSize: 11 }} />}
            <Line dataKey="benchmark" name="Benchmark" stroke="var(--benchmark)" strokeDasharray="4 3" dot={false} isAnimationActive={false} />
            <Line dataKey="strategie" name="Strategie" stroke="var(--text-2)" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function Detail({ datei }: { datei: string }) {
  const bericht = useQuery({ queryKey: ["labor-bericht", datei], queryFn: () => api<LaborBericht>(`/api/spiel/labor/berichte/${encodeURIComponent(datei)}`) });
  if (bericht.isError) return <Fehleranzeige fehler={bericht.error} />;
  const b = bericht.data;
  if (!b) return <Skelett className="h-[480px] rounded-2xl" />;
  return (
    <div className="space-y-4">
      <Karte>
        <KarteKopf
          titel={b.strategie}
          untertitel={`${b.beschreibung} · ${datum(b.zeitraum.von)} bis ${datum(b.zeitraum.bis)} (${b.zeitraum.tage} Handelstage), Kapital ${b.kapital} EUR, Benchmark ${b.benchmark_ticker}`}
        />
        <div className="space-y-2 px-5 pb-4">
          <Abzeichen ton={b.urteil.vorschlag ? "gut" : "neutral"}>{b.urteil.text}</Abzeichen>
          {b.urteil.gruende.length > 0 && (
            <ul className="list-disc pl-5 text-[12.5px] text-text-2">
              {b.urteil.gruende.map((g) => (
                <li key={g}>{g}</li>
              ))}
            </ul>
          )}
          <p className="text-[12px] text-text-3">Parameter: {JSON.stringify(b.parameter)}</p>
        </div>
      </Karte>
      <Karte>
        <KarteKopf titel="Wertentwicklung" untertitel={`In-Sample bis ${datum(b.in_sample.bis ?? "")} (${b.in_sample.tage} Tage), Out-of-Sample ab ${datum(b.out_of_sample.von ?? "")} (${b.out_of_sample.tage} Tage)`} />
        <Kurve b={b} />
      </Karte>
      <Karte className="overflow-hidden">
        <KarteKopf titel="Kennzahlen mit 95-%-Intervall" untertitel="In-Sample und Out-of-Sample getrennt: erst die Out-of-Sample-Spalte zählt" />
        <div className="overflow-x-auto">
          <table className="zahl w-full text-[13px]">
            <thead>
              <tr className="border-y border-rand text-[12px] text-text-3">
                <th className="px-5 py-2.5 text-left font-medium">Kennzahl</th>
                {["gesamt", "In-Sample", "Out-of-Sample"].map((s) => (
                  <th key={s} className="px-4 py-2.5 text-right font-medium">{s}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ZEILEN.map((z) => (
                <tr key={z.name} className="border-b border-rand/70 last:border-0">
                  <td className="px-5 py-2.5 text-text-2">{z.name}</td>
                  {[b.gesamt, b.is, b.oos].map((k, i) => (
                    <td key={i} className="px-4 py-2.5 text-right font-medium text-text">{k.genug_daten ? z.wert(k) : "zu wenig Daten"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Karte>
      <Karte>
        <KarteKopf titel="Kosten, Versuche und Grenzen" />
        <div className="space-y-2 px-5 pb-4 text-[12.5px] text-text-2">
          <p>
            Gebühren {b.kosten.gebuehren} EUR, Spreads {b.kosten.spreads} EUR, Umsatz {b.kosten.umsatz} EUR, {b.kosten.orders} Orders; Zinsen {b.kosten.zinsen} EUR, Dividenden {b.kosten.dividenden} EUR; Endwert{" "}
            {b.kosten.endwert} EUR.
          </p>
          <p>
            Getestete Varianten insgesamt: {b.versuche.anzahl}; Deflated Sharpe: {zahl(b.versuche.deflated_sharpe)} (Wahrscheinlichkeit, dass der wahre Sharpe über 0 liegt, nach Korrektur für die Zahl der Versuche).
          </p>
          <ul className="list-disc pl-5 text-text-3">
            {b.grenzen.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </div>
      </Karte>
    </div>
  );
}

export function Labor() {
  const liste = useQuery({ queryKey: ["labor-berichte"], queryFn: () => api<LaborBerichtKopf[]>("/api/spiel/labor/berichte") });
  const suche = useSearch({ strict: false }) as { datei?: string };
  const navigate = useNavigate();
  const gewaehlt = suche.datei ?? liste.data?.[0]?.datei;
  if (liste.isError) return <Fehleranzeige fehler={liste.error} />;
  return (
    <div className="einblenden">
      <Seitenkopf
        titel="Strategie-Labor"
        untertitel="Regelbasierte Strategien im Rückblick auf Tagesdaten, mit den Kosten des Spiels. Kein Handel, keine Buchung. Diskretionäres Trading wird nicht zurückgerechnet (Look-ahead durch das Training)."
      />
      {!liste.data ? (
        <Skelett className="h-[400px] rounded-2xl" />
      ) : !liste.data.length ? (
        <Karte>
          <Leer titel="Noch keine Berichte" text="Ein Lauf der Art „Strategie-Labor“ (Claude-Läufe) oder `python tools/backtest.py ausfuehren` erzeugt Berichte unter labor/." />
        </Karte>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
          <Karte className="overflow-hidden lg:sticky lg:top-20 lg:max-h-[calc(100vh-7rem)] lg:self-start lg:overflow-y-auto">
            {liste.data.map((b) => (
              <button
                key={b.datei}
                onClick={() => void navigate({ to: "/analyse/labor", search: { datei: b.datei } })}
                className={cn("block w-full border-b border-rand/70 px-4 py-3 text-left last:border-0 hover:bg-flaeche-2", gewaehlt === b.datei && "bg-flaeche-2")}
              >
                <div className="text-[13px] font-medium text-text">{b.strategie}</div>
                <div className="text-[12px] text-text-3">{b.erstellt.slice(0, 10)} · {b.urteil.text}</div>
              </button>
            ))}
          </Karte>
          {gewaehlt && <Detail datei={gewaehlt} />}
        </div>
      )}
    </div>
  );
}
