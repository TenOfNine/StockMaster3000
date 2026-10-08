import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { AlertTriangle, BookOpenText, CandlestickChart, Clock, Lightbulb, ListFilter, Newspaper } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Kerzendiagramm } from "@/components/diagramme/Kerzendiagramm";
import { Legende, NavDiagramm } from "@/components/diagramme/NavDiagramm";
import { useUeberblick } from "@/components/layout/AppRahmen";
import { Markdown } from "@/components/Markdown";
import { NewsListe } from "@/components/News";
import { Abzeichen, Delta, Fehleranzeige, Karte, KarteKopf, Leer, PROFIL_FARBE, PROFIL_NAME, Reiter, ReiterInhalt, ReiterKnopf, ReiterLeiste, Seitenkopf, Skelett } from "@/components/ui";
import { api, PROFILE, type Dokument, type Kennzahlen, type Kerze, type Lesson, type Markt, type MarktEintrag, type NavDaten, type NewsMeldung, type Review } from "@/lib/api";
import { cn } from "@/lib/cn";
import { datum, euro, faktor, prozent, relativ, zahl, zeit } from "@/lib/format";

import { Beobachtungsliste } from "./Beobachtungsliste";

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

const GRUPPEN_MARKT: { titel: string; passt: (e: MarktEintrag) => boolean }[] = [
  { titel: "Benchmark und Devisen", passt: (e) => e.ticker === "EUNL.DE" || e.ticker === "EURUSD=X" },
  { titel: "Indizes und Rohstoffe", passt: (e) => /[\^=]/.test(e.ticker) && e.ticker !== "EURUSD=X" },
  { titel: "Werte in den Portfolios", passt: (e) => !/[\^=]/.test(e.ticker) && e.ticker !== "EUNL.DE" },
];

function Marktzeile({ e, aktiv, waehlen }: { e: MarktEintrag; aktiv: boolean; waehlen: () => void }) {
  return (
    <tr onClick={waehlen} className={cn("cursor-pointer border-t border-rand", aktiv ? "bg-flaeche-3" : "hover:bg-flaeche-2")}>
      <td className="px-4 py-2.5">
        <button type="button" onClick={waehlen} className="text-left">
          <div className="font-mono text-[12.5px] text-text">{e.ticker}</div>
          <div className="truncate text-[12px] text-text-3">{e.name ?? e.boerse}</div>
        </button>
      </td>
      <td className="zahl px-3 py-2.5 text-right text-[13.5px] font-semibold text-text">
        {zahl(e.kurs, e.ticker === "EURUSD=X" ? 4 : 2)} {e.ticker !== "EURUSD=X" && <span className="text-[11.5px] font-normal text-text-3">{e.waehrung}</span>}
      </td>
      <td className="px-3 py-2.5 text-right">
        <Delta wert={e.veraenderung} />
      </td>
      <td className="px-3 py-2.5 text-[12px] text-text-3">
        <div title={zeit(e.kurs_zeit)}>{e.kurs_zeit ? zeit(e.kurs_zeit) : "–"}</div>
        <div>{e.verzoegerung_minuten != null ? `${e.verzoegerung_minuten} Min. Verzögerung` : e.markt_offen ? "Markt offen" : "Markt geschlossen"}</div>
      </td>
      <td className="px-4 py-2.5 text-[12px]">
        {e.veraltet ? (
          <Abzeichen ton="warnung" icon={<AlertTriangle className="size-3" />}>
            veraltet
          </Abzeichen>
        ) : (
          <Abzeichen>{e.quelle}</Abzeichen>
        )}
        {e.veraltet && e.quelle && <div className="mt-1 max-w-[220px] truncate text-text-3" title={e.grund ?? undefined}>{e.quelle}</div>}
      </td>
    </tr>
  );
}

export function Kurse() {
  const markt = useQuery({ queryKey: ["markt"], queryFn: () => api<Markt>("/api/spiel/markt"), refetchInterval: 60_000 });
  const liste = useQuery({ queryKey: ["kurse"], queryFn: () => api<{ ticker: string; name: string | null; bis: string | null }[]>("/api/spiel/kurse") });
  const [ticker, setTicker] = useState<string | null>(null);
  useEffect(() => {
    if (ticker) return;
    const erster = markt.data?.eintraege.find((e) => e.ticker === "^GDAXI")?.ticker ?? markt.data?.eintraege[0]?.ticker ?? liste.data?.[0]?.ticker;
    if (erster) setTicker(erster);
  }, [markt.data, liste.data, ticker]);
  const hatHistorie = !!ticker && !!liste.data?.some((t) => t.ticker === ticker);
  const kerzen = useQuery({ queryKey: ["kerzen", ticker], queryFn: () => api<Kerze[]>(`/api/spiel/kurse/${encodeURIComponent(ticker!)}`), enabled: hatHistorie });
  const news = useQuery({ queryKey: ["news", ticker], queryFn: () => api<{ meldungen: NewsMeldung[] }>(`/api/spiel/news?ticker=${encodeURIComponent(ticker!)}&anzahl=15`), enabled: !!ticker });
  const statistik = useMemo(() => {
    const k = kerzen.data ?? [];
    if (k.length < 2) return null;
    const letzte = k[k.length - 1];
    const hoch = Math.max(...k.map((x) => x.high));
    const tief = Math.min(...k.map((x) => x.low));
    return { letzte, gesamt: letzte.close / k[0].close - 1, hoch, tief };
  }, [kerzen.data]);
  const eintraege = markt.data?.eintraege ?? [];
  const gewaehlt = eintraege.find((e) => e.ticker === ticker);
  const zusaetzlich = (liste.data ?? []).filter((t) => !eintraege.some((e) => e.ticker === t.ticker));

  return (
    <div className="einblenden">
      <Seitenkopf
        titel="Markt & Kurse"
        untertitel="Kurse aus tools/kurse.py, abgerufen vom Hintergrunddienst (5 Minuten bei offenem Markt, sonst stündlich). Die Web-UI rechnet nicht selbst. Fällt jede Quelle aus, steht dort der letzte bekannte Kurs mit Kennzeichnung – gebucht wird nur zu protokollierten Kursen."
        aktionen={
          markt.data?.zeit ? (
            <span className="inline-flex items-center gap-1.5 text-[12.5px] text-text-3">
              <Clock className="size-3.5" /> Stand {relativ(markt.data.zeit)} · {markt.data.erfolgreich}/{markt.data.anzahl} aktuell
            </span>
          ) : undefined
        }
      />
      <Reiter defaultValue="uebersicht">
        <ReiterLeiste>
          <ReiterKnopf value="uebersicht">
            <CandlestickChart className="size-4" />
            Übersicht
          </ReiterKnopf>
          <ReiterKnopf value="beobachtung">
            <ListFilter className="size-4" />
            Beobachtungsliste
          </ReiterKnopf>
        </ReiterLeiste>
        <ReiterInhalt value="uebersicht">
          <Karte className="mb-4 overflow-hidden">
            {markt.isPending ? (
              <Skelett className="m-4 h-48" />
            ) : !eintraege.length ? (
              <Leer
                icon={<CandlestickChart className="size-5" />}
                titel="Noch keine Marktübersicht"
                text="Der Hintergrunddienst hat noch keine Kurse abgerufen. In der Einrichtung unter Kursdaten eine Quelle wählen und „Jetzt abrufen“ drücken; der Systemstatus zeigt, ob der Dienst läuft."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px]">
                  <thead>
                    <tr className="text-left text-[11.5px] font-medium tracking-wide text-text-3 uppercase">
                      <th className="px-4 py-2.5 font-medium">Wert</th>
                      <th className="px-3 py-2.5 text-right font-medium">Kurs</th>
                      <th className="px-3 py-2.5 text-right font-medium">ggü. Vortag</th>
                      <th className="px-3 py-2.5 font-medium">Zeitstempel</th>
                      <th className="px-4 py-2.5 font-medium">Quelle</th>
                    </tr>
                  </thead>
                  {GRUPPEN_MARKT.map((g) => {
                    const zeilen = eintraege.filter(g.passt);
                    if (!zeilen.length) return null;
                    return (
                      <tbody key={g.titel}>
                        <tr>
                          <td colSpan={5} className="bg-flaeche-2 px-4 py-1.5 text-[11.5px] font-semibold text-text-3">
                            {g.titel}
                          </td>
                        </tr>
                        {zeilen.map((e) => (
                          <Marktzeile key={e.ticker} e={e} aktiv={e.ticker === ticker} waehlen={() => setTicker(e.ticker)} />
                        ))}
                      </tbody>
                    );
                  })}
                </table>
              </div>
            )}
          </Karte>
          {zusaetzlich.length > 0 && (
            <div className="mb-4 flex flex-wrap gap-1.5">
              <span className="self-center text-[12px] text-text-3">Weitere gespeicherte Tagesdaten:</span>
              {zusaetzlich.map((t) => (
                <button key={t.ticker} onClick={() => setTicker(t.ticker)} className={cn("rounded-md border px-2 py-1 font-mono text-[12px]", ticker === t.ticker ? "border-akzent text-text" : "border-rand text-text-2 hover:border-rand-stark")}>
                  {t.ticker}
                </button>
              ))}
            </div>
          )}
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
            <Karte>
              <KarteKopf
                titel={<span className="font-mono">{ticker ?? "–"}</span>}
                icon={<CandlestickChart className="size-4" />}
                untertitel={gewaehlt?.name ?? (statistik ? `Letzter Schluss ${datum(statistik.letzte.datum)}` : undefined)}
              />
              {gewaehlt?.veraltet && gewaehlt.grund && (
                <p className="mx-5 mb-3 rounded-lg border border-warnung/30 bg-warnung-flaeche px-3 py-2 text-[12.5px] text-text-2">
                  <span className="font-medium text-text">Kein aktueller Kurs: </span>
                  {gewaehlt.grund}
                </p>
              )}
              {statistik && (
                <div className="grid grid-cols-2 gap-4 px-5 pb-3 sm:grid-cols-3">
                  <div>
                    <div className="text-[12px] text-text-3">Letzter Schluss</div>
                    <div className="zahl text-[18px] font-semibold text-text">{zahl(statistik.letzte.close)}</div>
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
              <div className="px-3 pb-4">
                {!hatHistorie ? (
                  <Leer titel="Noch keine Tagesdaten" text="Tagesdaten (400 Tage) holt der Hintergrunddienst beim ersten Abruf und danach täglich nach US-Börsenschluss." />
                ) : kerzen.data ? (
                  <Kerzendiagramm kerzen={kerzen.data} hoehe={420} />
                ) : (
                  <Skelett className="h-[420px]" />
                )}
              </div>
            </Karte>
            <Karte className="xl:self-start">
              <KarteKopf titel="Meldungen zu diesem Wert" icon={<Newspaper className="size-4" />} untertitel="News-Speicher, Zuordnung über Feed oder Schlagwort" />
              <div className="px-2 pb-2">{news.data ? <NewsListe meldungen={news.data.meldungen} leerText="Zu diesem Wert gibt es noch keine Meldungen." /> : <Skelett className="m-3 h-40" />}</div>
            </Karte>
          </div>
        </ReiterInhalt>
        <ReiterInhalt value="beobachtung">
          <Beobachtungsliste />
        </ReiterInhalt>
      </Reiter>
    </div>
  );
}

