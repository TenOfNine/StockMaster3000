import { useQuery } from "@tanstack/react-query";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Abzeichen, Karte, KarteKopf, Leer, PROFIL_NAME, Skelett } from "@/components/ui";
import { api, PROFILE, type LaborErgebnisse, type MitIntervall, type StatistikProfil } from "@/lib/api";
import { prozent, zahl } from "@/lib/format";

const MIN_AUSSAGE = 30;

/** Kalibrierung der Prognosen (Brier-Score) und Schattenbuch der verworfenen Kandidaten; nur Anzeige gespeicherter Ergebnisse. */
export function LaborKarten() {
  const labor = useQuery({ queryKey: ["labor"], queryFn: () => api<LaborErgebnisse>("/api/spiel/labor") });
  if (!labor.data) return <Skelett className="mt-4 h-[320px] rounded-2xl" />;
  const p = labor.data.prognosen?.gesamt;
  const s = labor.data.schattenbuch;
  return (
    <div className="mt-4 grid gap-4 xl:grid-cols-2">
      <Karte>
        <KarteKopf
          titel="Prognosegüte"
          untertitel={p ? `Brier ${zahl(p.brier, 3)} (Raten 0,667) · Skill ${zahl(p.brier_skill)} · Richtung ${prozent(p.richtung_trefferquote, false, 0)}` : "Kalibrierung der Szenario-Wahrscheinlichkeiten"}
        />
        {!p || !p.ausgewertet ? (
          <Leer titel="Noch keine ausgewertete Prognose" text="Sobald der Horizont einer Prognose vorbei ist, erscheint hier die Kalibrierung." />
        ) : (
          <div className="px-4 pb-4">
            <div className="h-[260px]" role="img" aria-label="Kalibrierung: angegebene Wahrscheinlichkeit gegen Trefferquote">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={p.kalibrierung} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--raster)" />
                  <XAxis dataKey="mittel_p" type="number" domain={[0, 1]} tickFormatter={(w: number) => prozent(w, false, 0)} tickLine={false} />
                  <YAxis type="number" domain={[0, 1]} width={44} tickFormatter={(w: number) => prozent(w, false, 0)} tickLine={false} axisLine={false} />
                  <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="var(--benchmark)" strokeDasharray="4 4" />
                  <Tooltip
                    formatter={(w) => prozent(w as number, false, 0)}
                    labelFormatter={(w) => `angegeben ${prozent(w as number, false, 0)}`}
                  />
                  <Line dataKey="trefferquote" name="Trefferquote" stroke="var(--text-2)" strokeWidth={2} dot isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-[12px] text-text-3">
              Gestrichelt: perfekte Kalibrierung. {p.ausgewertet} von {p.anzahl} Prognosen ausgewertet, {p.offen} offen.
              {!p.belastbar && ` Unter ${MIN_AUSSAGE} ausgewerteten Prognosen kaum belastbar.`}
            </p>
          </div>
        )}
      </Karte>
      <Karte>
        <KarteKopf titel="Schattenbuch" untertitel="Verworfene Kandidaten gegen gekaufte Werte, Nettorendite nach Kosten" />
        {!s || !(s.vergleich.verworfen[String(s.horizonte[0])]?.n || s.vergleich.gekauft[String(s.horizonte[0])]?.n) ? (
          <Leer titel="Noch keine bewerteten Kandidaten" text="Die Zeile „Verworfen“ im Session-Eintrag füllt das Schattenbuch." />
        ) : (
          <div className="overflow-x-auto pb-3">
            <table className="zahl w-full text-[13px]">
              <thead>
                <tr className="border-y border-rand text-[12px] text-text-3">
                  <th className="px-5 py-2.5 text-left font-medium">Horizont</th>
                  <th className="px-3 py-2.5 text-right font-medium">verworfen n</th>
                  <th className="px-3 py-2.5 text-right font-medium">Ø</th>
                  <th className="px-3 py-2.5 text-right font-medium">gekauft n</th>
                  <th className="px-3 py-2.5 text-right font-medium">Ø</th>
                </tr>
              </thead>
              <tbody>
                {s.horizonte.map((h) => {
                  const v = s.vergleich.verworfen[String(h)];
                  const k = s.vergleich.gekauft[String(h)];
                  return (
                    <tr key={h} className="border-b border-rand/70 last:border-0">
                      <td className="px-5 py-2.5 text-text-2">{h} Handelstage</td>
                      <td className="px-3 py-2.5 text-right">{v?.n ?? 0}</td>
                      <td className="px-3 py-2.5 text-right font-medium text-text">{prozent(v?.mittel, true, 1)}</td>
                      <td className="px-3 py-2.5 text-right">{k?.n ?? 0}</td>
                      <td className="px-3 py-2.5 text-right font-medium text-text">{prozent(k?.mittel, true, 1)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="px-5 pt-2 text-[12px] text-text-3">Kleine Stichproben schwanken stark; ein Unterschied ist erst mit vielen Fällen belastbar. {s.ohne_kurs ? `${s.ohne_kurs} ohne protokollierten Kurs.` : ""}</p>
          </div>
        )}
      </Karte>
    </div>
  );
}

/** Wert mit 95-%-Intervall, z. B. „+2,1 % [−3,0 %; +7,2 %]“. */
export function mitIntervall(k: MitIntervall | undefined, art: "prozent" | "zahl", vorzeichen = false): string {
  if (!k || k.wert == null) return "–";
  const f = (w: number) => (art === "prozent" ? prozent(w, vorzeichen, 1) : zahl(w));
  return k.ci ? `${f(k.wert)} [${f(k.ci[0])}; ${f(k.ci[1])}]` : f(k.wert);
}

export const NICHT_UNTERSCHEIDBAR = "noch nicht vom Benchmark unterscheidbar";

const STATISTIK_ZEILEN: { name: string; wert: (k: StatistikProfil) => string }[] = [
  { name: "Rendite p. a.", wert: (k) => mitIntervall(k.rendite_pa, "prozent") },
  { name: "Überrendite p. a. gegen Benchmark", wert: (k) => mitIntervall(k.ueberrendite_pa, "prozent", true) },
  { name: "Sharpe Ratio", wert: (k) => mitIntervall(k.sharpe, "zahl") },
  { name: "Information Ratio", wert: (k) => mitIntervall(k.information_ratio, "zahl") },
  { name: "Alpha p. a. gegen MSCI World", wert: (k) => mitIntervall(k.alpha_pa, "prozent", true) },
  { name: "Überrendite gegen beta-angepasste Benchmark", wert: (k) => mitIntervall(k.ueberrendite_beta_pa, "prozent", true) },
  { name: "Überrendite gegen Benchmark mit gleicher Schwankung", wert: (k) => mitIntervall(k.ueberrendite_vola_pa, "prozent", true) },
  { name: "Beta gegen MSCI World", wert: (k) => mitIntervall(k.beta, "zahl") },
  { name: "Sortino", wert: (k) => mitIntervall(k.sortino, "zahl") },
  { name: "Calmar", wert: (k) => mitIntervall(k.calmar, "zahl") },
];

/** Kennzahlen mit Konfidenzintervall (tools/statistik.py): Rendite allein ist kein Rangkriterium. */
export function StatistikKarte() {
  const labor = useQuery({ queryKey: ["labor"], queryFn: () => api<LaborErgebnisse>("/api/spiel/labor") });
  if (!labor.data) return <Skelett className="mt-4 h-[260px] rounded-2xl" />;
  const s = labor.data.statistik;
  const profile = PROFILE.filter((p) => s?.profile[p]?.genug_daten);
  return (
    <Karte className="mt-4 overflow-hidden">
      <KarteKopf titel="Kennzahlen mit Unsicherheit" untertitel="95-%-Intervall (Block-Bootstrap), Rangfolge nach Information Ratio statt nach Rohrendite" />
      {!s || !profile.length ? (
        <Leer titel="Noch zu wenige Handelstage" text="Kennzahlen mit Intervall erscheinen nach rund 20 Handelstagen; belastbar werden sie erst nach Monaten." />
      ) : (
        <div className="overflow-x-auto">
          <table className="zahl w-full text-[13px]">
            <thead>
              <tr className="border-y border-rand text-[12px] text-text-3">
                <th className="px-5 py-2.5 text-left font-medium">Kennzahl</th>
                {profile.map((p) => (
                  <th key={p} className="px-4 py-2.5 text-right font-medium">{PROFIL_NAME[p]}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {STATISTIK_ZEILEN.map((z) => (
                <tr key={z.name} className="border-b border-rand/70">
                  <td className="px-5 py-2.5 text-text-2">{z.name}</td>
                  {profile.map((p) => (
                    <td key={p} className="px-4 py-2.5 text-right font-medium text-text">{z.wert(s.profile[p])}</td>
                  ))}
                </tr>
              ))}
              <tr>
                <td className="px-5 py-2.5 text-text-2">Einordnung</td>
                {profile.map((p) => (
                  <td key={p} className="px-4 py-2.5 text-right">
                    {s.profile[p].hinweis ? <Abzeichen>{NICHT_UNTERSCHEIDBAR}</Abzeichen> : <Abzeichen ton={s.profile[p].abstand === "besser" ? "gut" : "schlecht"}>vom Benchmark unterscheidbar ({s.profile[p].abstand})</Abzeichen>}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
          {s.rang_information_ratio.length > 0 && (
            <p className="px-5 pt-3 text-[12px] text-text-3">Rang nach Information Ratio: {s.rang_information_ratio.map((p) => PROFIL_NAME[p as keyof typeof PROFIL_NAME] ?? p).join(" > ")}</p>
          )}
          {(s.rang_beta_angepasst?.length ?? 0) > 0 && (
            <p className="px-5 py-3 text-[12px] text-text-3">
              Rang nach Überrendite gegen die beta-angepasste Benchmark (Marktrisiko zählt nicht als Leistung):{" "}
              {s.rang_beta_angepasst!.map((p) => PROFIL_NAME[p as keyof typeof PROFIL_NAME] ?? p).join(" > ")}
            </p>
          )}
        </div>
      )}
    </Karte>
  );
}
