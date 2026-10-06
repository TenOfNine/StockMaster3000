import { Table2 } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { NavDaten, Profil } from "@/lib/api";
import { cn } from "@/lib/cn";
import { datum, datumKompakt, euro, prozent } from "@/lib/format";

import { PROFIL_FARBE, PROFIL_NAME } from "../ui";

const ACHSE = { stroke: "var(--rand)", tickLine: false, axisLine: false } as const;

function TooltipKarte({ titel, zeilen }: { titel: string; zeilen: { name: string; farbe: string; wert: string; gestrichelt?: boolean }[] }) {
  return (
    <div className="min-w-[190px] rounded-xl border border-rand bg-flaeche/95 px-3 py-2.5 shadow-2xl backdrop-blur">
      <div className="mb-1.5 text-[12px] font-medium text-text-3">{titel}</div>
      {zeilen.map((z) => (
        <div key={z.name} className="flex items-center justify-between gap-4 py-0.5 text-[12.5px]">
          <span className="flex items-center gap-2 text-text-2">
            <span
              className="h-0.5 w-3 rounded-full"
              style={z.gestrichelt ? { backgroundImage: `linear-gradient(90deg, ${z.farbe} 50%, transparent 50%)`, backgroundSize: "4px 2px" } : { background: z.farbe }}
            />
            {z.name}
          </span>
          <span className="zahl font-semibold text-text">{z.wert}</span>
        </div>
      ))}
    </div>
  );
}

export function Legende({ eintraege }: { eintraege: { name: string; farbe: string; gestrichelt?: boolean }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5" role="list" aria-label="Legende">
      {eintraege.map((e) => (
        <span key={e.name} role="listitem" className="flex items-center gap-2 text-[12.5px] text-text-2">
          <svg width="18" height="6" aria-hidden>
            <line x1="1" y1="3" x2="17" y2="3" stroke={e.farbe} strokeWidth="2" strokeLinecap="round" strokeDasharray={e.gestrichelt ? "3 3" : undefined} />
          </svg>
          {e.name}
        </span>
      ))}
    </div>
  );
}

/** Wertentwicklung eines Profils gegen seine Benchmark (EUR) oder aller Profile als Rendite (%). */
export function NavDiagramm({ daten, profile, hoehe = 300 }: { daten: NavDaten; profile: Profil[]; hoehe?: number }) {
  const [tabelle, setTabelle] = useState(false);
  const einzel = profile.length === 1;
  const zeilen = useMemo(() => {
    const bench = new Map(daten.benchmark.map((b) => [b.datum, b]));
    const alleDaten = new Set<string>();
    profile.forEach((p) => daten.profile[p]?.forEach((z) => alleDaten.add(z.datum)));
    const navNachDatum = Object.fromEntries(profile.map((p) => [p, new Map((daten.profile[p] ?? []).map((z) => [z.datum, z.portfoliowert]))]));
    return [...alleDaten].sort().map((d) => {
      const zeile: Record<string, number | string | undefined> = { datum: d };
      profile.forEach((p) => {
        const wert = navNachDatum[p].get(d);
        zeile[p] = einzel ? wert : wert != null ? wert / 1000 - 1 : undefined;
        const b = bench.get(d)?.[p];
        zeile[`${p}_bench`] = einzel ? b : b != null ? b / 1000 - 1 : undefined;
      });
      return zeile;
    });
  }, [daten, profile, einzel]);

  if (zeilen.length === 0) return <div className="grid h-[200px] place-items-center text-[13px] text-text-3">Noch keine Tageswerte.</div>;

  const legende = einzel
    ? [
        { name: PROFIL_NAME[profile[0]], farbe: PROFIL_FARBE[profile[0]] },
        { name: "Benchmark", farbe: "var(--benchmark)", gestrichelt: true },
      ]
    : profile.map((p) => ({ name: PROFIL_NAME[p], farbe: PROFIL_FARBE[p] }));
  const fmt = (w: number) => (einzel ? euro(w) : prozent(w, true, 1));

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3 px-1">
        <Legende eintraege={legende} />
        <button
          onClick={() => setTabelle((t) => !t)}
          className={cn("flex items-center gap-1.5 rounded-md px-2 py-1 text-[12px] text-text-3 hover:bg-flaeche-3 hover:text-text", tabelle && "bg-flaeche-3 text-text")}
          aria-pressed={tabelle}
        >
          <Table2 className="size-3.5" /> Tabelle
        </button>
      </div>
      {tabelle ? (
        <div className="max-h-[320px] overflow-auto rounded-lg border border-rand">
          <table className="zahl w-full text-[12.5px]">
            <thead className="sticky top-0 bg-flaeche-2 text-left text-text-3">
              <tr>
                <th className="px-3 py-2 font-medium">Datum</th>
                {profile.map((p) => (
                  <th key={p} className="px-3 py-2 text-right font-medium">{PROFIL_NAME[p]}</th>
                ))}
                {profile.map((p) => (
                  <th key={`${p}b`} className="px-3 py-2 text-right font-medium">Benchmark {einzel ? "" : PROFIL_NAME[p]}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...zeilen].reverse().map((z) => (
                <tr key={z.datum as string} className="border-t border-rand text-text-2">
                  <td className="px-3 py-1.5">{datum(z.datum as string)}</td>
                  {profile.map((p) => (
                    <td key={p} className="px-3 py-1.5 text-right text-text">{z[p] != null ? fmt(z[p] as number) : "–"}</td>
                  ))}
                  {profile.map((p) => (
                    <td key={`${p}b`} className="px-3 py-1.5 text-right">{z[`${p}_bench`] != null ? fmt(z[`${p}_bench`] as number) : "–"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ height: hoehe }} role="img" aria-label={`Wertentwicklung ${legende.map((l) => l.name).join(", ")}`}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={zeilen} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
              <CartesianGrid stroke="var(--raster)" vertical={false} />
              <XAxis dataKey="datum" tickFormatter={datumKompakt} minTickGap={42} {...ACHSE} dy={6} />
              <YAxis
                width={einzel ? 72 : 56}
                tickFormatter={(w: number) => (einzel ? `${Math.round(w)} €` : prozent(w, true, 0))}
                domain={["auto", "auto"]}
                {...ACHSE}
              />
              {!einzel && <ReferenceLine y={0} stroke="var(--rand-stark)" />}
              <Tooltip
                cursor={{ stroke: "var(--rand-stark)", strokeWidth: 1 }}
                content={({ active, payload, label }) =>
                  active && payload?.length ? (
                    <TooltipKarte
                      titel={datum(label as string)}
                      zeilen={payload
                        .filter((p) => p.value != null)
                        .map((p) => {
                          const schluessel = String(p.dataKey);
                          const istBench = schluessel.endsWith("_bench");
                          const profil = schluessel.replace("_bench", "") as Profil;
                          return {
                            name: istBench ? (einzel ? "Benchmark" : `Benchmark ${PROFIL_NAME[profil]}`) : PROFIL_NAME[profil],
                            farbe: istBench ? "var(--benchmark)" : PROFIL_FARBE[profil],
                            gestrichelt: istBench,
                            wert: fmt(p.value as number),
                          };
                        })}
                    />
                  ) : null
                }
              />
              {profile.map((p) =>
                einzel ? (
                  <Line key={`${p}_bench`} type="monotone" dataKey={`${p}_bench`} stroke="var(--benchmark)" strokeWidth={1.5} strokeDasharray="4 4" dot={false} activeDot={false} isAnimationActive={false} />
                ) : null,
              )}
              {profile.map((p) => (
                <Line
                  key={p}
                  type="monotone"
                  dataKey={p}
                  stroke={PROFIL_FARBE[p]}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, stroke: "var(--flaeche)", strokeWidth: 2 }}
                  isAnimationActive={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

/** Drawdown vom Höchststand mit den Schwellen der Drawdown-Bremse. */
export function DrawdownDiagramm({ zeilen, stufe1, stufe2, farbe }: { zeilen: { datum: string; drawdown: number }[]; stufe1: number; stufe2: number; farbe: string }) {
  if (!zeilen.length) return null;
  const minimum = Math.min(stufe2 * 1.1, ...zeilen.map((z) => z.drawdown));
  const schritt = minimum < -0.3 ? 0.1 : 0.05;
  const ticks: number[] = [];
  for (let t = 0; t >= minimum - 1e-9; t -= schritt) ticks.push(Number(t.toFixed(2)));
  return (
    <div style={{ height: 180 }} role="img" aria-label="Drawdown-Verlauf mit Schwellen der Drawdown-Bremse">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={zeilen} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
          <defs>
            <linearGradient id="dd-verlauf" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={farbe} stopOpacity={0.05} />
              <stop offset="100%" stopColor={farbe} stopOpacity={0.35} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--raster)" vertical={false} />
          <XAxis dataKey="datum" tickFormatter={datumKompakt} minTickGap={42} {...ACHSE} dy={6} />
          <YAxis width={56} domain={[ticks[ticks.length - 1], 0]} ticks={ticks} tickFormatter={(w: number) => prozent(w, false, 0)} {...ACHSE} />
          <ReferenceLine y={stufe1} stroke="var(--warnung)" strokeDasharray="4 4" label={{ value: `Stufe 1 (${prozent(stufe1, false, 0)})`, position: "insideBottomRight", fill: "var(--text-3)", fontSize: 11 }} />
          <ReferenceLine y={stufe2} stroke="var(--schlecht)" strokeDasharray="4 4" label={{ value: `Stufe 2 (${prozent(stufe2, false, 0)})`, position: "insideBottomRight", fill: "var(--text-3)", fontSize: 11 }} />
          <Tooltip
            cursor={{ stroke: "var(--rand-stark)" }}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <TooltipKarte titel={datum(label as string)} zeilen={[{ name: "Drawdown", farbe, wert: prozent(payload[0].value as number, false) }]} />
              ) : null
            }
          />
          <Area type="monotone" dataKey="drawdown" stroke={farbe} strokeWidth={2} fill="url(#dd-verlauf)" isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Sparkline({ werte, farbe, hoehe = 44 }: { werte: number[]; farbe: string; hoehe?: number }) {
  if (werte.length < 2) return <div style={{ height: hoehe }} />;
  const min = Math.min(...werte);
  const max = Math.max(...werte);
  const spanne = max - min || 1;
  const punkte = werte.map((w, i) => `${(i / (werte.length - 1)) * 100},${100 - ((w - min) / spanne) * 90 - 5}`).join(" ");
  const id = `spark-${farbe.replace(/[^a-z]/gi, "")}`;
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ height: hoehe }} className="w-full" aria-hidden>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={farbe} stopOpacity="0.28" />
          <stop offset="100%" stopColor={farbe} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,100 ${punkte} 100,100`} fill={`url(#${id})`} />
      <polyline points={punkte} fill="none" stroke={farbe} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  );
}
