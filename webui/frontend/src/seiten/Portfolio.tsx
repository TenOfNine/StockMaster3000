import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { ArrowRight, BookMarked, Gauge, Layers, ListOrdered, ReceiptText, ShieldHalf } from "lucide-react";
import { useMemo, useState } from "react";

import { Ergebnis } from "@/components/Bausteine";
import { DrawdownDiagramm, NavDiagramm } from "@/components/diagramme/NavDiagramm";
import { Markdown } from "@/components/Markdown";
import { VorgabenKarte } from "@/components/Vorgaben";
import {
  Abzeichen,
  Auslastungsbalken,
  Delta,
  Eingabe,
  Fehleranzeige,
  Karte,
  KarteKopf,
  Kennzahl,
  Leer,
  Mono,
  PROFIL_FARBE,
  PROFIL_NAME,
  Reiter,
  ReiterInhalt,
  ReiterKnopf,
  ReiterLeiste,
  Seitenkopf,
  Skelett,
  StufenAbzeichen,
} from "@/components/ui";
import { api, type NavDaten, type PortfolioDetail, type Position, type Profil, type Trade } from "@/lib/api";
import { cn } from "@/lib/cn";
import { automatischAusloeser, datum, euro, faktor, frei, prozent, zahl, zeit } from "@/lib/format";

export function Portfolio() {
  const { profil } = useParams({ strict: false }) as { profil: Profil };
  const detail = useQuery({ queryKey: ["portfolio", profil], queryFn: () => api<PortfolioDetail>(`/api/spiel/portfolios/${profil}`) });
  const nav = useQuery({ queryKey: ["nav"], queryFn: () => api<NavDaten>("/api/spiel/nav") });

  if (detail.isError)
    return detail.error && "status" in detail.error && detail.error.status === 404 ? (
      <Karte>
        <Leer titel={`Portfolio ${PROFIL_NAME[profil] ?? profil} existiert noch nicht`} text="Die Portfolios entstehen mit tools/init.py beim Spielstart." />
      </Karte>
    ) : (
      <Fehleranzeige fehler={detail.error} erneut={() => void detail.refetch()} />
    );
  const d = detail.data;
  const k = d?.kennzahlen;

  return (
    <div className="einblenden" key={profil}>
      <Seitenkopf
        vorne={
          <div className="mb-2 flex items-center gap-2 text-[12.5px] font-medium text-text-3">
            <span className="h-3 w-1 rounded-full" style={{ background: PROFIL_FARBE[profil] }} />
            Portfolio
          </div>
        }
        titel={
          <span className="flex flex-wrap items-center gap-3">
            {PROFIL_NAME[profil]}
            {k && (k.status !== "aktiv" ? <Abzeichen ton="schlecht">{k.status}</Abzeichen> : <StufenAbzeichen stufe={k.stufe} />)}
          </span>
        }
        untertitel={k ? `Seit ${datum(k.startdatum)} · bewertet bis ${datum(k.verarbeitet_bis)} · Benchmark ${prozent(d!.grenzen.benchmark_etf_anteil, false, 0)} MSCI World / ${prozent(1 - d!.grenzen.benchmark_etf_anteil, false, 0)} Cash` : undefined}
      />

      {!d || !k ? (
        <Skelett className="h-[120px] rounded-2xl" />
      ) : (
        <Karte className="relative overflow-hidden">
          <div className="absolute inset-y-0 left-0 w-[3px]" style={{ background: PROFIL_FARBE[profil] }} />
          <div className="grid grid-cols-2 gap-x-6 gap-y-5 p-5 sm:grid-cols-4 xl:grid-cols-8">
            <Kennzahl label="Portfoliowert" wert={euro(k.wert)} zusatz={<Delta wert={k.rendite} />} />
            <Kennzahl label="Gegen Benchmark" wert={<Delta wert={k.gegen_bench} gross />} zusatz={`Bench. ${prozent(k.bench_rendite, true)}`} />
            <Kennzahl label="Max. Drawdown" wert={prozent(k.max_dd, false)} zusatz={`Höchststand ${euro(Number(k.hoechststand))}`} />
            <Kennzahl
              label="Sharpe Ratio"
              wert={k.handelstage >= k.min_tage && k.sharpe != null ? zahl(k.sharpe) : "–"}
              zusatz={k.handelstage >= k.min_tage ? `${k.handelstage} Handelstage` : `zu wenig Daten (${k.handelstage}/${k.min_tage})`}
              hilfe="Erst ab 60 Handelstagen aussagekräftig (regeln.md, KONZEPT.md 7)."
            />
            <Kennzahl label="Trefferquote" wert={prozent(k.trefferquote, false, 0)} zusatz={`${k.geschlossen} abgeschlossene Trades`} />
            <Kennzahl label="Payoff-Ratio" wert={k.payoff != null ? zahl(k.payoff) : "–"} zusatz="Ø Gewinn / Ø Verlust" />
            <Kennzahl label="Kostenquote" wert={prozent(k.kostenquote, false)} zusatz="Kosten / Startkapital" />
            <Kennzahl label="Cash" wert={euro(d.bewertung?.cash ?? Number(d.portfolio.cash))} zusatz={`Quote ${prozent(k.cashquote, false, 1)}`} />
          </div>
        </Karte>
      )}

      <Reiter defaultValue="ueberblick" className="mt-6">
        <ReiterLeiste>
          <ReiterKnopf value="ueberblick"><Gauge className="size-4" />Überblick</ReiterKnopf>
          <ReiterKnopf value="positionen"><Layers className="size-4" />Positionen {d && <Zaehler n={d.positionen.length} />}</ReiterKnopf>
          <ReiterKnopf value="orders"><ListOrdered className="size-4" />Orders {d && <Zaehler n={d.portfolio.offene_orders.length} />}</ReiterKnopf>
          <ReiterKnopf value="trades"><ReceiptText className="size-4" />Trades</ReiterKnopf>
          <ReiterKnopf value="limits"><ShieldHalf className="size-4" />Limits</ReiterKnopf>
          <ReiterKnopf value="strategie"><BookMarked className="size-4" />Anlagerichtlinie</ReiterKnopf>
        </ReiterLeiste>

        <ReiterInhalt value="ueberblick">
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
            <Karte>
              <KarteKopf titel="Portfoliowert gegen Benchmark" untertitel="Tageswerte aus data/nav und data/benchmark.csv" />
              <div className="px-4 pb-4">{nav.data ? <NavDiagramm daten={nav.data} profile={[profil]} /> : <Skelett className="h-[300px]" />}</div>
            </Karte>
            <Karte>
              <KarteKopf titel="Zusammensetzung" />
              {d?.bewertung ? <Zusammensetzung d={d} /> : <Skelett className="mx-5 mb-5 h-40" />}
            </Karte>
          </div>
          <Karte className="mt-4">
            <KarteKopf titel="Drawdown vom Höchststand" untertitel="Gestrichelt: Schwellen der Drawdown-Bremse (regeln.md 7)" />
            <div className="px-4 pb-4">
              {nav.data && d ? (
                <DrawdownDiagramm
                  zeilen={(nav.data.profile[profil] ?? []).map((z) => ({ datum: z.datum, drawdown: z.drawdown }))}
                  stufe1={d.grenzen.drawdown_stufe1}
                  stufe2={d.grenzen.drawdown_stufe2}
                  farbe={PROFIL_FARBE[profil]}
                />
              ) : (
                <Skelett className="h-[180px]" />
              )}
            </div>
          </Karte>
        </ReiterInhalt>

        <ReiterInhalt value="positionen">{d && <Positionen positionen={d.positionen} />}</ReiterInhalt>
        <ReiterInhalt value="orders">{d && <Orders d={d} />}</ReiterInhalt>
        <ReiterInhalt value="trades">
          <Trades profil={profil} />
        </ReiterInhalt>
        <ReiterInhalt value="limits">{d && <Limits d={d} />}</ReiterInhalt>
        <ReiterInhalt value="strategie">
          <VorgabenKarte profil={profil} />
          <Karte className="p-6 sm:p-8">{d?.strategie ? <Markdown text={d.strategie} /> : <Leer titel="Noch keine Anlagerichtlinie" text={`strategie/${profil}.md fehlt.`} />}</Karte>
        </ReiterInhalt>
      </Reiter>
    </div>
  );
}

function Zaehler({ n }: { n: number }) {
  return <span className="zahl rounded-full bg-flaeche-3 px-1.5 text-[11px] text-text-2">{n}</span>;
}

function Zusammensetzung({ d }: { d: PortfolioDetail }) {
  const b = d.bewertung!;
  const zert = d.positionen.filter((p) => p.typ === "ko" || p.typ === "faktor").reduce((s, p) => s + (p.wert_eur ?? 0), 0);
  const aktien = b.positionswert - zert;
  const teile = [
    { name: "Cash", wert: b.cash, farbe: "var(--benchmark)" },
    { name: "Aktien & ETFs", wert: aktien, farbe: PROFIL_FARBE[d.profil] },
    { name: "Zertifikate", wert: zert, farbe: "var(--akzent)" },
  ].filter((t) => t.wert > 0.004);
  return (
    <div className="px-5 pb-5">
      <div className="flex h-3 gap-[2px] overflow-hidden rounded-full" role="img" aria-label="Zusammensetzung">
        {teile.map((t) => (
          <div key={t.name} style={{ width: `${(t.wert / b.nav) * 100}%`, background: t.farbe }} className="first:rounded-l-full last:rounded-r-full" />
        ))}
      </div>
      <ul className="mt-4 space-y-2.5">
        {teile.map((t) => (
          <li key={t.name} className="flex items-center justify-between text-[13px]">
            <span className="flex items-center gap-2 text-text-2">
              <span className="size-2.5 rounded-[3px]" style={{ background: t.farbe }} />
              {t.name}
            </span>
            <span className="zahl text-text">
              {euro(t.wert)} <span className="text-text-3">· {prozent(t.wert / b.nav, false, 1)}</span>
            </span>
          </li>
        ))}
      </ul>
      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-rand pt-4">
        <Kennzahl label="Exposure" wert={faktor(b.exposure)} />
        <Kennzahl label="Zertifikate-Anteil" wert={prozent(b.zertifikate_anteil, false, 1)} />
      </div>
    </div>
  );
}

const TYP_NAME: Record<Position["typ"], string> = { aktie: "Aktie", etf: "ETF", ko: "Knock-out", faktor: "Faktor" };

function Positionen({ positionen }: { positionen: Position[] }) {
  if (!positionen.length) return <Karte><Leer titel="Keine offenen Positionen" text="Handeln ist der Normalfall, Cash die Ausnahme: Warum keine Position besteht, steht als belegte Ausnahme im Session-Eintrag." /></Karte>;
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {positionen.map((p) => {
        const einsatz = p.einsatz_eur ?? 0;
        const ergebnis = p.wert_eur != null && einsatz ? p.wert_eur / einsatz - 1 : null;
        const stop = p.stop ? Number(p.stop) : null;
        const abstand = stop && p.kurs ? (p.richtung === "long" ? p.kurs / stop - 1 : stop / p.kurs - 1) : null;
        return (
          <Karte key={p.id} className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-[15px] font-semibold text-text">{p.typ === "aktie" || p.typ === "etf" ? p.ticker : p.basiswert}</span>
                  <Abzeichen>{TYP_NAME[p.typ]}</Abzeichen>
                  {p.richtung === "short" && <Abzeichen ton="warnung">Short</Abzeichen>}
                </div>
                <div className="mt-0.5 text-[12px] text-text-3">
                  <Mono>{p.id}</Mono> · eröffnet {zeit(p.eroeffnet)}
                </div>
              </div>
              <div className="text-right">
                <div className="zahl text-[16px] font-semibold text-text">{euro(p.wert_eur)}</div>
                <Delta wert={ergebnis} />
              </div>
            </div>
            <dl className="mt-4 grid grid-cols-3 gap-3 text-[12.5px]">
              <Feldchen label="Stück" wert={frei(Number(p.stueck))} />
              <Feldchen label="Einstand je Stück" wert={euro(Number(p.einstand))} />
              <Feldchen label="Kurs Basiswert" wert={p.kurs != null ? `${zahl(p.kurs)} (${datum(p.kurs_datum)})` : "–"} />
              <Feldchen label="Stop" wert={p.stop ? zahl(Number(p.stop)) : "keiner"} zusatz={abstand != null ? `${prozent(abstand, false, 1)} Abstand` : undefined} />
              <Feldchen label="Kursziel" wert={p.kursziel ? zahl(Number(p.kursziel)) : "keines"} />
              <Feldchen
                label={p.typ === "ko" ? "Hebel / Barriere" : "Hebel"}
                wert={`${faktor(p.hebel_aktuell)}${p.typ === "ko" ? ` / ${zahl(Number(p.parameter.barriere))}` : ""}`}
              />
            </dl>
            <Link to="/entscheidungen/$id" params={{ id: p.journal_id }} className="mt-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-akzent hover:underline">
              Trade-Akte {p.journal_id} <ArrowRight className="size-3.5" />
            </Link>
          </Karte>
        );
      })}
    </div>
  );
}

function Feldchen({ label, wert, zusatz }: { label: string; wert: string; zusatz?: string }) {
  return (
    <div>
      <dt className="text-text-3">{label}</dt>
      <dd className="zahl mt-0.5 font-medium text-text">{wert}</dd>
      {zusatz && <dd className="text-[11.5px] text-text-3">{zusatz}</dd>}
    </div>
  );
}

function Orders({ d }: { d: PortfolioDetail }) {
  if (!d.portfolio.offene_orders.length) return <Karte><Leer titel="Keine offenen Orders" text="Vorgemerkte Orders werden beim Nachbuchen zum nächsten Eröffnungskurs ausgeführt." /></Karte>;
  return (
    <Karte className="overflow-hidden">
      <Tabelle
        kopf={["Order", "Aktion", "Instrument", "Einsatz", "Limit", "Stop / Ziel", "Erfasst", "Journal"]}
        zeilen={d.portfolio.offene_orders.map((o) => [
          <Mono key="id">{o.id}</Mono>,
          `${o.aktion} · ${o.art}`,
          o.ticker || o.basiswert,
          o.einsatz ? euro(Number(o.einsatz)) : "–",
          o.limit ?? "–",
          `${o.stop ?? "–"} / ${o.kursziel ?? "–"}`,
          zeit(o.erfasst),
          <Link key="j" to="/entscheidungen/$id" params={{ id: o.journal_id }} className="font-mono text-[12px] text-akzent hover:underline">{o.journal_id}</Link>,
        ])}
      />
    </Karte>
  );
}

function Tabelle({ kopf, zeilen, rechts = [] }: { kopf: string[]; zeilen: React.ReactNode[][]; rechts?: number[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="zahl w-full text-[13px]">
        <thead>
          <tr className="border-b border-rand text-left text-[12px] text-text-3">
            {kopf.map((k, i) => (
              <th key={k} className={cn("px-4 py-2.5 font-medium whitespace-nowrap", rechts.includes(i) && "text-right")}>{k}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {zeilen.map((z, i) => (
            <tr key={i} className="border-b border-rand/70 text-text-2 last:border-0 hover:bg-flaeche-2">
              {z.map((zelle, j) => (
                <td key={j} className={cn("px-4 py-2.5 whitespace-nowrap", rechts.includes(j) && "text-right")}>{zelle}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const AKTIONEN = ["alle", "kauf", "verkauf", "vormerkung", "dividende", "zins", "knockout", "verfall", "storno", "aenderung", "split"];

function Trades({ profil }: { profil: Profil }) {
  const abfrage = useQuery({ queryKey: ["trades", profil], queryFn: () => api<Trade[]>(`/api/spiel/portfolios/${profil}/trades`) });
  const [aktion, setAktion] = useState("ohne-zins");
  const [suche, setSuche] = useState("");
  const gefiltert = useMemo(() => {
    const s = suche.trim().toLowerCase();
    return (abfrage.data ?? [])
      .filter((t) => (aktion === "alle" ? true : aktion === "ohne-zins" ? t.aktion !== "zins" : t.aktion === aktion))
      .filter((t) => !s || [t.trade_id, t.ticker, t.basiswert, t.journal_id, t.bemerkung].some((w) => w?.toLowerCase().includes(s)))
      .reverse();
  }, [abfrage.data, aktion, suche]);
  if (abfrage.isError) return <Fehleranzeige fehler={abfrage.error} />;
  return (
    <Karte className="overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-rand p-4 sm:flex-row sm:items-center">
        <Eingabe placeholder="Suchen: Trade-ID, Ticker, Journal-ID …" value={suche} onChange={(e) => setSuche(e.target.value)} className="sm:max-w-xs" aria-label="Trades durchsuchen" />
        <div className="flex flex-wrap gap-1.5">
          {["ohne-zins", ...AKTIONEN].map((a) => (
            <button
              key={a}
              onClick={() => setAktion(a)}
              className={cn("rounded-full border px-2.5 py-1 text-[12px] transition-colors", aktion === a ? "border-text bg-text text-bg" : "border-rand text-text-2 hover:border-rand-stark")}
            >
              {a === "ohne-zins" ? "ohne Zinsen" : a}
            </button>
          ))}
        </div>
      </div>
      {abfrage.isPending ? (
        <Skelett className="m-4 h-40" />
      ) : gefiltert.length === 0 ? (
        <Leer titel="Keine passenden Buchungen" />
      ) : (
        <Tabelle
          rechts={[5, 6, 7, 8]}
          kopf={["Trade", "Zeit", "Aktion", "Instrument", "Grund", "Stück", "Kurs EUR", "Betrag", "Cash danach", "Journal"]}
          zeilen={gefiltert.slice(0, 400).map((t) => [
            <Mono key="t">{t.trade_id}</Mono>,
            zeit(t.zeit),
            <span key="a" className="font-medium text-text">
              {t.aktion}
              {automatischAusloeser(t.bemerkung) && (
                <Abzeichen ton="akzent" className="ml-1.5 align-middle">
                  automatisch · {automatischAusloeser(t.bemerkung)}
                </Abzeichen>
              )}
            </span>,
            t.ticker || "–",
            t.grund,
            t.stueck != null ? frei(t.stueck) : "–",
            t.kurs != null ? zahl(t.kurs, 4) : "–",
            <Ergebnis key="b" wert={t.betrag_eur} />,
            euro(t.cash_danach),
            t.journal_id ? (
              <Link key="j" to="/entscheidungen/$id" params={{ id: t.journal_id }} className="font-mono text-[12px] text-akzent hover:underline">{t.journal_id}</Link>
            ) : (
              "–"
            ),
          ])}
        />
      )}
    </Karte>
  );
}

function Limits({ d }: { d: PortfolioDetail }) {
  const g = d.grenzen;
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <Karte>
        <KarteKopf titel="Auslastung" untertitel={`Stand ${datum(d.letzter_tageswert.datum)} · Werte aus data/nav und tools/limits.py`} />
        <div className="space-y-5 px-5 pb-5">
          {d.auslastung.map((a) => (
            <Auslastungsbalken key={a.regel} label={a.regel} ist={a.ist} grenze={a.grenze} art={a.art} einheit={a.einheit} />
          ))}
        </div>
      </Karte>
      <Karte>
        <KarteKopf titel="Grenzen je Order" untertitel="regeln.md Abschnitt 7 · config/profile.json" />
        <dl className="divide-y divide-rand px-5 pb-3 text-[13px]">
          {[
            ["Max. Hebel je Zertifikat", `${g.max_hebel}x`],
            ["Max. Risiko je Trade", `${prozent(d.max_risiko_trade, false, 1)}${d.kennzahlen.stufe >= 1 ? " (halbiert, Stufe 1)" : ""}`],
            ["Max. Einzelposition", prozent(g.max_einzelposition, false, 0)],
            ["Max. Zertifikate-Anteil", prozent(g.max_anteil_zertifikate, false, 0)],
            ["Max. Gesamt-Exposure", `${zahl(g.max_exposure, 1)}x`],
            ["Mindest-Cashquote", prozent(g.min_cashquote, false, 0)],
            ["Drawdown-Bremse", `${prozent(g.drawdown_stufe1, false, 0)} / ${prozent(g.drawdown_stufe2, false, 0)}`],
            ["Neue Zertifikate", d.kennzahlen.stufe >= 2 ? "gesperrt (Stufe 2)" : "erlaubt"],
          ].map(([l, w]) => (
            <div key={l} className="flex items-center justify-between gap-4 py-2.5">
              <dt className="text-text-2">{l}</dt>
              <dd className="zahl font-medium text-text">{w}</dd>
            </div>
          ))}
        </dl>
      </Karte>
    </div>
  );
}
