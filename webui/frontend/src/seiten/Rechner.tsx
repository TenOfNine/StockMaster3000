import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Legende } from "@/components/diagramme/NavDiagramm";
import { Abzeichen, Eingabe, Feld, Karte, KarteKopf, Kennzahl, Seitenkopf, Skelett } from "@/components/ui";
import { api, ApiFehler } from "@/lib/api";
import { cn } from "@/lib/cn";
import { faktor, prozent, zahl } from "@/lib/format";

interface KoErgebnis {
  basispreis: number;
  barriere: number;
  wert: number;
  hebel: number;
  abstand_barriere: number;
  aufzinsung_30_tage: number;
  szenarien: { bewegung: number; basiswert: number; wert: number; veraenderung: number | null; ausgeknockt: boolean }[];
}

function Umschalter({ wert, setWert }: { wert: "long" | "short"; setWert: (w: "long" | "short") => void }) {
  return (
    <div className="flex rounded-lg border border-rand bg-flaeche-2 p-0.5" role="radiogroup" aria-label="Richtung">
      {(["long", "short"] as const).map((r) => (
        <button
          key={r}
          role="radio"
          aria-checked={wert === r}
          onClick={() => setWert(r)}
          className={cn("flex-1 rounded-md px-4 py-1.5 text-[13px] font-medium capitalize", wert === r ? "bg-flaeche-3 text-text shadow-sm" : "text-text-3 hover:text-text")}
        >
          {r}
        </button>
      ))}
    </div>
  );
}

export function Rechner() {
  return (
    <div className="einblenden">
      <Seitenkopf
        titel="Zertifikatsrechner"
        untertitel="Synthetische Knock-out- und Faktor-Zertifikate exakt nach regeln.md Abschnitt 4. Gerechnet wird in tools/produkte.py; die Anzeige bucht nichts."
      />
      <div className="grid gap-4 xl:grid-cols-2">
        <KnockOut />
        <Faktor />
      </div>
    </div>
  );
}

function KnockOut() {
  const [richtung, setRichtung] = useState<"long" | "short">("long");
  const [kurs, setKurs] = useState("24000");
  const [hebel, setHebel] = useState("5");
  const parameter = useDeferredValue(`richtung=${richtung}&kurs=${encodeURIComponent(kurs)}&hebel=${encodeURIComponent(hebel)}`);
  const abfrage = useQuery({ queryKey: ["ko", parameter], queryFn: () => api<KoErgebnis>(`/api/spiel/rechner/ko?${parameter}`), retry: false, placeholderData: (alt) => alt });
  const e = abfrage.data;
  return (
    <Karte>
      <KarteKopf titel="Knock-out" untertitel="Basispreis = Barriere; Long wird täglich mit 4 % p. a. aufgezinst, Short bleibt konstant." />
      <div className="grid gap-4 px-5 pb-5 sm:grid-cols-3">
        <div className="sm:col-span-3">
          <Umschalter wert={richtung} setWert={setRichtung} />
        </div>
        <Feld id="ko-kurs" label="Basiswertkurs">
          <Eingabe id="ko-kurs" inputMode="decimal" value={kurs} onChange={(ev) => setKurs(ev.target.value)} />
        </Feld>
        <Feld id="ko-hebel" label="Zielhebel">
          <Eingabe id="ko-hebel" inputMode="decimal" value={hebel} onChange={(ev) => setHebel(ev.target.value)} />
        </Feld>
        <div className="flex items-end">
          {abfrage.isError && <p className="text-[12.5px] text-schlecht">{abfrage.error instanceof ApiFehler ? abfrage.error.message : "Ungültige Eingabe"}</p>}
        </div>
      </div>
      {e ? (
        <>
          <div className="grid grid-cols-2 gap-4 border-y border-rand bg-flaeche-2 px-5 py-4 sm:grid-cols-4">
            <Kennzahl label="Basispreis / Barriere" wert={zahl(e.basispreis)} />
            <Kennzahl label="Wert je Stück" wert={zahl(e.wert)} />
            <Kennzahl label="Hebel" wert={faktor(e.hebel)} />
            <Kennzahl label="Abstand Barriere" wert={prozent(e.abstand_barriere, false, 1)} zusatz={`nach 30 Tagen ${zahl(e.aufzinsung_30_tage)}`} />
          </div>
          <div className="overflow-x-auto px-2 py-3">
            <table className="zahl w-full text-[13px]">
              <thead>
                <tr className="text-[12px] text-text-3">
                  <th className="px-3 py-2 text-left font-medium">Basiswert</th>
                  <th className="px-3 py-2 text-right font-medium">Kurs</th>
                  <th className="px-3 py-2 text-right font-medium">Wert</th>
                  <th className="px-3 py-2 text-left font-medium">Veränderung Zertifikat</th>
                </tr>
              </thead>
              <tbody>
                {e.szenarien.map((s) => (
                  <tr key={s.bewegung} className={cn("border-t border-rand", s.bewegung === 0 && "bg-flaeche-2")}>
                    <td className="px-3 py-1.5 text-text-2">{s.bewegung > 0 ? "+" : ""}{s.bewegung} %</td>
                    <td className="px-3 py-1.5 text-right text-text-2">{zahl(s.basiswert)}</td>
                    <td className="px-3 py-1.5 text-right text-text">{zahl(s.wert)}</td>
                    <td className="px-3 py-1.5">
                      {s.ausgeknockt ? (
                        <Abzeichen ton="schlecht">Knock-out</Abzeichen>
                      ) : (
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-28 overflow-hidden rounded-full bg-flaeche-3">
                            <div
                              className={cn("h-full rounded-full", (s.veraenderung ?? 0) >= 0 ? "bg-gut" : "bg-schlecht")}
                              style={{ width: `${Math.min(100, Math.abs((s.veraenderung ?? 0) * 100))}%` }}
                            />
                          </div>
                          <span className={cn("w-16 text-right", (s.veraenderung ?? 0) > 0 ? "text-gut" : (s.veraenderung ?? 0) < 0 ? "text-schlecht" : "text-text-2")}>{prozent(s.veraenderung, true, 0)}</span>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <Skelett className="mx-5 mb-5 h-56" />
      )}
    </Karte>
  );
}

const BEISPIEL = "100;104;99;103;98;102;97;101;100;104;100";

function Faktor() {
  const [richtung, setRichtung] = useState<"long" | "short">("long");
  const [f, setF] = useState("3");
  const [reihe, setReihe] = useState(BEISPIEL);
  const parameter = useDeferredValue(`richtung=${richtung}&faktor=${encodeURIComponent(f)}&kurse=${encodeURIComponent(reihe.replace(/\s+/g, ""))}`);
  const abfrage = useQuery({
    queryKey: ["faktor", parameter],
    queryFn: () => api<{ werte: number[]; basiswert_index: number[] }>(`/api/spiel/rechner/faktor?${parameter}`),
    retry: false,
    placeholderData: (alt) => alt,
  });
  const daten = abfrage.data?.werte.map((w, i) => ({ tag: i, faktor: w, basiswert: abfrage.data!.basiswert_index[i] })) ?? [];
  const letzter = daten[daten.length - 1];
  return (
    <Karte>
      <KarteKopf titel="Faktor-Zertifikat" untertitel="V_t = V_(t−1) · max(0; 1 + F · R_t − 0,02/365). Seitwärtsphasen kosten Wert (Faktor-Effekt)." />
      <div className="grid gap-4 px-5 pb-4 sm:grid-cols-[1fr_120px]">
        <div className="sm:col-span-2">
          <Umschalter wert={richtung} setWert={setRichtung} />
        </div>
        <Feld id="f-kurse" label="Schlusskurse des Basiswerts" hinweis="Mit Semikolon getrennt, 2 bis 120 Werte.">
          <Eingabe id="f-kurse" value={reihe} onChange={(e) => setReihe(e.target.value)} className="font-mono text-[12.5px]" />
        </Feld>
        <Feld id="f-faktor" label="Faktor">
          <Eingabe id="f-faktor" inputMode="decimal" value={f} onChange={(e) => setF(e.target.value)} />
        </Feld>
      </div>
      {abfrage.isError && <p className="px-5 pb-3 text-[12.5px] text-schlecht">{abfrage.error instanceof ApiFehler ? abfrage.error.message : "Ungültige Eingabe"}</p>}
      {letzter && (
        <div className="grid grid-cols-2 gap-4 border-y border-rand bg-flaeche-2 px-5 py-4">
          <Kennzahl label="Basiswert (Index)" wert={zahl(letzter.basiswert)} zusatz={prozent(letzter.basiswert / 100 - 1, true)} />
          <Kennzahl label="Faktor-Zertifikat" wert={zahl(letzter.faktor)} zusatz={prozent(letzter.faktor / 100 - 1, true)} />
        </div>
      )}
      <div className="px-4 pt-3 pb-1">
        <Legende eintraege={[{ name: "Basiswert (Index 100)", farbe: "var(--benchmark)", gestrichelt: true }, { name: `Faktor ${f}x ${richtung}`, farbe: "var(--akzent)" }]} />
      </div>
      <div className="h-[260px] px-2 pb-4" role="img" aria-label="Verlauf Basiswert und Faktor-Zertifikat">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={daten} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--raster)" vertical={false} />
            <XAxis dataKey="tag" tickLine={false} axisLine={false} />
            <YAxis width={44} domain={["auto", "auto"]} tickLine={false} axisLine={false} />
            <ReferenceLine y={100} stroke="var(--rand-stark)" />
            <Tooltip
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <div className="rounded-xl border border-rand bg-flaeche px-3 py-2 text-[12.5px] shadow-2xl">
                    <div className="mb-1 text-text-3">Tag {label}</div>
                    <div className="text-text-2">Basiswert: <span className="zahl text-text">{zahl(payload[0].value as number)}</span></div>
                    <div className="text-text-2">Faktor: <span className="zahl text-text">{zahl(payload[1]?.value as number)}</span></div>
                  </div>
                ) : null
              }
            />
            <Line dataKey="basiswert" stroke="var(--benchmark)" strokeDasharray="4 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Line dataKey="faktor" stroke="var(--akzent)" strokeWidth={2} dot={{ r: 2.5, strokeWidth: 0, fill: "var(--akzent)" }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Karte>
  );
}
