import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { BookOpenText, CandlestickChart, Lightbulb } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Kerzendiagramm } from "@/components/diagramme/Kerzendiagramm";
import { Legende, NavDiagramm } from "@/components/diagramme/NavDiagramm";
import { useUeberblick } from "@/components/layout/AppRahmen";
import { Markdown } from "@/components/Markdown";
import { Abzeichen, Delta, Fehleranzeige, Karte, KarteKopf, Leer, PROFIL_FARBE, PROFIL_NAME, Seitenkopf, Skelett } from "@/components/ui";
import { api, PROFILE, type Dokument, type Kennzahlen, type Kerze, type Lesson, type NavDaten, type Review } from "@/lib/api";
import { cn } from "@/lib/cn";
import { datum, euro, faktor, prozent, zahl } from "@/lib/format";

// --------------------------------------------------------------------------
// Ranking

const ZEILEN: { name: string; wert: (k: Kennzahlen) => React.ReactNode; hilfe?: string }[] = [
  { name: "Portfoliowert", wert: (k) => euro(k.wert) },
  { name: "Rendite", wert: (k) => <Delta wert={k.rendite} /> },
  { name: "Benchmark-Rendite", wert: (k) => prozent(k.bench_rendite, true) },
  { name: "Rendite gegen Benchmark", wert: (k) => <Delta wert={k.gegen_bench} /> },
  { name: "Max. Drawdown", wert: (k) => prozent(k.max_dd, false) },
  {
    name: "Sharpe Ratio",
    wert: (k) => (k.handelstage >= k.min_tage && k.sharpe != null ? zahl(k.sharpe) : <span className="text-text-3">zu wenig Daten ({k.handelstage}/{k.min_tage})</span>),
  },
  { name: "Abgeschlossene Trades", wert: (k) => String(k.geschlossen) },
  { name: "Trefferquote", wert: (k) => prozent(k.trefferquote, false, 1) },
  { name: "Payoff-Ratio", wert: (k) => (k.payoff != null ? zahl(k.payoff) : "–") },
  { name: "Kostenquote", wert: (k) => prozent(k.kostenquote, false, 1) },
  { name: "Exposure", wert: (k) => faktor(k.exposure) },
  { name: "Cashquote", wert: (k) => prozent(k.cashquote, false, 1) },
  { name: "Drawdown-Stufe", wert: (k) => String(k.stufe) },
  { name: "Status", wert: (k) => k.status },
];

export function Ranking() {
  const ueberblick = useUeberblick();
  const nav = useQuery({ queryKey: ["nav"], queryFn: () => api<NavDaten>("/api/spiel/nav") });
  const profile = PROFILE.filter((p) => ueberblick.data?.profile[p]);
  const balken = profile.map((p) => {
    const k = ueberblick.data!.profile[p]!;
    return { profil: p, name: PROFIL_NAME[p], rendite: k.rendite, benchmark: k.bench_rendite ?? 0 };
  });
  if (ueberblick.isError) return <Fehleranzeige fehler={ueberblick.error} />;
  return (
    <div className="einblenden">
      <Seitenkopf
        titel="Ranking & Benchmark"
        untertitel="Kennzahlen aus tools/bewertung.py. Belastbare Aussagen frühestens nach etwa drei Monaten und einer zweistelligen Zahl abgeschlossener Trades je Portfolio – Glück ist kein Können."
      />
      {!ueberblick.data ? (
        <Skelett className="h-[400px] rounded-2xl" />
      ) : !profile.length ? (
        <Karte>
          <Leer titel="Noch keine Portfolios" />
        </Karte>
      ) : (
        <>
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
            <Karte className="overflow-hidden">
              <KarteKopf titel="Vergleich der Profile" untertitel={`Stand ${datum(ueberblick.data.profile[profile[0]]?.stand)}`} />
              <div className="overflow-x-auto">
                <table className="zahl w-full text-[13px]">
                  <thead>
                    <tr className="border-y border-rand text-[12px] text-text-3">
                      <th className="px-5 py-2.5 text-left font-medium">Kennzahl</th>
                      {profile.map((p) => (
                        <th key={p} className="px-5 py-2.5 text-right font-medium">
                          <span className="inline-flex items-center gap-1.5">
                            <span className="size-2 rounded-full" style={{ background: PROFIL_FARBE[p] }} />
                            {PROFIL_NAME[p]}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {ZEILEN.map((z) => (
                      <tr key={z.name} className="border-b border-rand/70 last:border-0">
                        <td className="px-5 py-2.5 text-text-2">{z.name}</td>
                        {profile.map((p) => (
                          <td key={p} className="px-5 py-2.5 text-right font-medium text-text">
                            {z.wert(ueberblick.data.profile[p]!)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Karte>
            <Karte className="flex flex-col">
              <KarteKopf titel="Rendite gegen Benchmark" untertitel="Je Profil: Portfolio (Farbe) und Benchmark (grau)" />
              <div className="px-4 pb-2">
                <Legende eintraege={[{ name: "Portfolio", farbe: "var(--text-2)" }, { name: "Benchmark", farbe: "var(--benchmark)" }]} />
              </div>
              <div className="min-h-[300px] flex-1 px-2 pb-4" role="img" aria-label="Balkendiagramm Rendite und Benchmark-Rendite je Profil">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={balken} barGap={2} margin={{ top: 16, right: 12, left: 4, bottom: 0 }}>
                    <CartesianGrid stroke="var(--raster)" vertical={false} />
                    <XAxis dataKey="name" tickLine={false} axisLine={false} />
                    <YAxis width={52} tickFormatter={(w: number) => prozent(w, true, 0)} tickLine={false} axisLine={false} />
                    <Tooltip
                      cursor={{ fill: "var(--flaeche-2)" }}
                      content={({ active, payload, label }) =>
                        active && payload?.length ? (
                          <div className="rounded-xl border border-rand bg-flaeche px-3 py-2 text-[12.5px] shadow-2xl">
                            <div className="mb-1 font-medium text-text">{label}</div>
                            <div className="text-text-2">Portfolio: <span className="zahl text-text">{prozent(payload[0].value as number, true)}</span></div>
                            <div className="text-text-2">Benchmark: <span className="zahl text-text">{prozent(payload[1]?.value as number, true)}</span></div>
                          </div>
                        ) : null
                      }
                    />
                    <Bar dataKey="rendite" radius={[4, 4, 4, 4]} maxBarSize={36} isAnimationActive={false}>
                      {balken.map((b) => (
                        <Cell key={b.profil} fill={PROFIL_FARBE[b.profil]} />
                      ))}
                    </Bar>
                    <Bar dataKey="benchmark" fill="var(--benchmark)" radius={[4, 4, 4, 4]} maxBarSize={36} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Karte>
          </div>
          <Karte className="mt-4">
            <KarteKopf titel="Rendite seit Start" untertitel="Alle Profile im Vergleich" />
            <div className="px-4 pb-4">{nav.data ? <NavDiagramm daten={nav.data} profile={profile} hoehe={320} /> : <Skelett className="h-[320px]" />}</div>
          </Karte>
        </>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
// Reviews & Lessons

const ART_TEXT: Record<string, string> = { woche: "Woche", monat: "Monat", quartal: "Quartal", stufe2: "Drawdown-Stufe 2", sonstige: "Sonstige" };

export function ReviewsLessons() {
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: () => api<Review[]>("/api/spiel/reviews") });
  const lessons = useQuery({ queryKey: ["lessons"], queryFn: () => api<Lesson[]>("/api/spiel/lessons") });
  const suche = useSearch({ strict: false }) as { datei?: string };
  const navigate = useNavigate();
  const gewaehlt = suche.datei ?? reviews.data?.[0]?.pfad;
  const dokument = useQuery({
    queryKey: ["dokument", gewaehlt],
    queryFn: () => api<Dokument>(`/api/spiel/dokument?pfad=${encodeURIComponent(gewaehlt!)}`),
    enabled: !!gewaehlt,
  });
  const [art, setArt] = useState("alle");
  const arten = [...new Set((reviews.data ?? []).map((r) => r.art))];

  return (
    <div className="einblenden">
      <Seitenkopf titel="Reviews & Lessons" untertitel="Wochen-, Monats- und Quartalsreviews sowie das Erkenntnisregister. Eine Erkenntnis aus einem einzelnen Trade bleibt Hypothese." />
      <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        <Karte className="overflow-hidden lg:sticky lg:top-20 lg:max-h-[calc(100vh-7rem)] lg:self-start lg:overflow-y-auto">
          <div className="flex flex-wrap gap-1 border-b border-rand p-3">
            {["alle", ...arten].map((a) => (
              <button
                key={a}
                onClick={() => setArt(a)}
                className={cn("rounded-full px-2.5 py-1 text-[12px] font-medium", art === a ? "bg-text text-bg" : "text-text-2 hover:bg-flaeche-3")}
              >
                {a === "alle" ? "Alle" : ART_TEXT[a] ?? a}
              </button>
            ))}
          </div>
          {reviews.isPending ? (
            <Skelett className="m-3 h-40" />
          ) : !reviews.data?.length ? (
            <Leer titel="Noch keine Reviews" />
          ) : (
            <ul className="p-1.5">
              {reviews.data
                .filter((r) => art === "alle" || r.art === art)
                .map((r) => (
                  <li key={r.pfad}>
                    <button
                      onClick={() => void navigate({ to: "/analyse/reviews", search: { datei: r.pfad } })}
                      className={cn("flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-[13px]", gewaehlt === r.pfad ? "bg-flaeche-3 text-text" : "text-text-2 hover:bg-flaeche-2")}
                    >
                      <span className="min-w-0">
                        <span className="block font-medium">{r.zeitraum}</span>
                        <span className="block truncate text-[11.5px] text-text-3">{r.titel.replace(/\s*\(Demo\)$/, "")}</span>
                      </span>
                      <Abzeichen className="shrink-0">{ART_TEXT[r.art] ?? r.art}</Abzeichen>
                    </button>
                  </li>
                ))}
            </ul>
          )}
        </Karte>
        <div className="space-y-4">
          <Karte className="min-h-[300px] p-6 sm:p-8">
            {dokument.data ? <Markdown text={dokument.data.inhalt} /> : gewaehlt ? <Skelett className="h-60" /> : <Leer icon={<BookOpenText className="size-5" />} titel="Kein Review ausgewählt" />}
          </Karte>
          <Karte>
            <KarteKopf titel="Erkenntnisregister" icon={<Lightbulb className="size-4" />} untertitel="lessons.md" />
            <div className="grid gap-3 px-5 pb-5 md:grid-cols-2">
              {lessons.data?.length ? (
                lessons.data.map((l) => (
                  <div key={l.id} className="rounded-xl border border-rand bg-flaeche-2 p-4">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[13.5px] font-semibold text-text">
                        {l.id} {l.titel}
                      </span>
                      <Abzeichen ton={l.felder.status?.startsWith("bestätigt") ? "gut" : l.felder.status?.startsWith("verworfen") ? "schlecht" : "warnung"}>
                        {l.felder.status?.split(" ")[0] ?? "Hypothese"}
                      </Abzeichen>
                    </div>
                    <p className="mt-2 text-[13px] text-text-2">{l.felder.schlussfolgerung ?? l.felder.beobachtung}</p>
                    {l.felder["prüfkriterium"] && <p className="mt-1.5 text-[12px] text-text-3">Prüfkriterium: {l.felder["prüfkriterium"]}</p>}
                  </div>
                ))
              ) : (
                <p className="text-[13px] text-text-3">Noch keine Einträge im Erkenntnisregister.</p>
              )}
            </div>
          </Karte>
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Markt & Kurse

export function Kurse() {
  const liste = useQuery({ queryKey: ["kurse"], queryFn: () => api<{ ticker: string; name: string | null; bis: string | null }[]>("/api/spiel/kurse") });
  const [ticker, setTicker] = useState<string | null>(null);
  useEffect(() => {
    if (!ticker && liste.data?.length) setTicker(liste.data.find((t) => t.ticker === "^GDAXI")?.ticker ?? liste.data[0].ticker);
  }, [liste.data, ticker]);
  const kerzen = useQuery({ queryKey: ["kerzen", ticker], queryFn: () => api<Kerze[]>(`/api/spiel/kurse/${encodeURIComponent(ticker!)}`), enabled: !!ticker });
  const statistik = useMemo(() => {
    const k = kerzen.data ?? [];
    if (k.length < 2) return null;
    const letzte = k[k.length - 1];
    const vorher = k[k.length - 2];
    const hoch = Math.max(...k.map((x) => x.high));
    const tief = Math.min(...k.map((x) => x.low));
    return { letzte, tag: letzte.close / vorher.close - 1, gesamt: letzte.close / k[0].close - 1, hoch, tief };
  }, [kerzen.data]);

  return (
    <div className="einblenden">
      <Seitenkopf titel="Markt & Kurse" untertitel="Gespeicherte Tagesdaten aus data/historie/ (Kursquelle tools/kurse.py). Die Web-UI ruft selbst keine Kurse ab." />
      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <Karte className="overflow-hidden lg:self-start">
          {liste.isPending ? (
            <Skelett className="m-3 h-60" />
          ) : !liste.data?.length ? (
            <Leer titel="Keine gespeicherten Kurse" />
          ) : (
            <ul className="p-1.5">
              {liste.data.map((t) => (
                <li key={t.ticker}>
                  <button
                    onClick={() => setTicker(t.ticker)}
                    className={cn("flex w-full flex-col rounded-lg px-3 py-2 text-left", ticker === t.ticker ? "bg-flaeche-3" : "hover:bg-flaeche-2")}
                  >
                    <span className="font-mono text-[12.5px] text-text">{t.ticker}</span>
                    <span className="truncate text-[12px] text-text-3">{t.name ?? `bis ${datum(t.bis)}`}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Karte>
        <Karte>
          <KarteKopf titel={<span className="font-mono">{ticker ?? "–"}</span>} icon={<CandlestickChart className="size-4" />} untertitel={statistik ? `Letzter Schluss ${datum(statistik.letzte.datum)}` : undefined} />
          {statistik && (
            <div className="grid grid-cols-2 gap-4 px-5 pb-3 sm:grid-cols-4">
              <div>
                <div className="text-[12px] text-text-3">Schluss</div>
                <div className="zahl text-[18px] font-semibold text-text">{zahl(statistik.letzte.close)}</div>
              </div>
              <div>
                <div className="text-[12px] text-text-3">Tag</div>
                <Delta wert={statistik.tag} gross />
              </div>
              <div>
                <div className="text-[12px] text-text-3">Zeitraum</div>
                <Delta wert={statistik.gesamt} gross />
              </div>
              <div>
                <div className="text-[12px] text-text-3">Spanne</div>
                <div className="zahl text-[14px] font-medium text-text">
                  {zahl(statistik.tief)} – {zahl(statistik.hoch)}
                </div>
              </div>
            </div>
          )}
          <div className="px-3 pb-4">{kerzen.data ? <Kerzendiagramm kerzen={kerzen.data} hoehe={420} /> : <Skelett className="h-[420px]" />}</div>
        </Karte>
      </div>
    </div>
  );
}

