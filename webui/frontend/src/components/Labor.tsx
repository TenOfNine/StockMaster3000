import { useQuery } from "@tanstack/react-query";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Karte, KarteKopf, Leer, Skelett } from "@/components/ui";
import { api, type LaborErgebnisse } from "@/lib/api";
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
