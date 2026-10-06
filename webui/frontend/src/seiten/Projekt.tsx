import * as Accordion from "@radix-ui/react-accordion";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, Circle, FileText, GitCommitHorizontal, PlayCircle, ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";

import { Markdown } from "@/components/Markdown";
import {
  Abzeichen,
  Dialog,
  Fehleranzeige,
  Karte,
  KarteKopf,
  Knopf,
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
} from "@/components/ui";
import { api, PROFILE, type Befund, type Commit, type Dokument, type StatusDaten } from "@/lib/api";
import { cn } from "@/lib/cn";
import { prozent, relativ, zeit } from "@/lib/format";

// --------------------------------------------------------------------------
// Regelwerk

interface Konfiguration {
  profile: { profile: Record<string, Record<string, string>> };
  kosten: Record<string, any>;
  universum: { boersen: Record<string, { name: string; zeitzone: string; oeffnung: string; schluss: string; waehrung: string; feiertage: string[]; fruehschluss?: Record<string, string> }>; basiswerte: Record<string, { name: string; boerse: string }> };
  projekt: Record<string, any>;
}

const LIMIT_ZEILEN: [string, string, "p" | "x"][] = [
  ["max_anteil_zertifikate", "Max. Anteil Zertifikate", "p"],
  ["max_hebel", "Max. Hebel je Zertifikat", "x"],
  ["max_exposure", "Max. Gesamt-Exposure", "x"],
  ["max_einzelposition", "Max. Einzelposition", "p"],
  ["min_cashquote", "Mindest-Cashquote", "p"],
  ["max_risiko_trade", "Max. Risiko je Trade", "p"],
  ["drawdown_stufe1", "Drawdown-Bremse Stufe 1", "p"],
  ["drawdown_stufe2", "Drawdown-Bremse Stufe 2", "p"],
  ["benchmark_etf_anteil", "Benchmark ETF-Anteil", "p"],
];

export function Regelwerk() {
  const regeln = useQuery({ queryKey: ["dokument", "regeln.md"], queryFn: () => api<Dokument>("/api/spiel/dokument?pfad=regeln.md") });
  const konfig = useQuery({ queryKey: ["konfiguration"], queryFn: () => api<Konfiguration>("/api/spiel/konfiguration") });
  const inhalt = regeln.data?.inhalt ?? "";
  const kapitel = useMemo(() => [...inhalt.matchAll(/^## (.+)$/gm)].map((m) => m[1]), [inhalt]);
  return (
    <div className="einblenden">
      <Seitenkopf titel="Regelwerk" untertitel="regeln.md ist verbindlich. Änderungen nur durch die Auftraggeber, mit Datum und ohne Rückwirkung; die Web-UI zeigt sie nur an." />
      <Reiter defaultValue="regeln">
        <ReiterLeiste>
          <ReiterKnopf value="regeln">Spielregeln</ReiterKnopf>
          <ReiterKnopf value="limits">Profile & Limits</ReiterKnopf>
          <ReiterKnopf value="kosten">Kosten</ReiterKnopf>
          <ReiterKnopf value="universum">Universum & Handelszeiten</ReiterKnopf>
        </ReiterLeiste>
        <ReiterInhalt value="regeln">
          <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
            <nav className="hidden lg:sticky lg:top-20 lg:block lg:self-start" aria-label="Kapitel">
              <ul className="space-y-0.5 border-l border-rand">
                {kapitel.map((k) => (
                  <li key={k}>
                    <a href={`#${encodeURIComponent(k)}`} onClick={(e) => { e.preventDefault(); document.getElementById(`kapitel-${k}`)?.scrollIntoView({ behavior: "smooth" }); }} className="-ml-px block border-l border-transparent py-1 pl-3 text-[12.5px] text-text-3 hover:border-text hover:text-text">
                      {k}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
            <Karte className="p-6 sm:p-10">
              {regeln.isError ? (
                <Fehleranzeige fehler={regeln.error} />
              ) : regeln.data ? (
                <div>
                  {inhalt.split(/^(?=## )/m).map((teil, i) => {
                    const titel = /^## (.+)$/m.exec(teil)?.[1];
                    return (
                      <div key={i} id={titel ? `kapitel-${titel}` : undefined} className="scroll-mt-20">
                        <Markdown text={teil} />
                      </div>
                    );
                  })}
                </div>
              ) : (
                <Skelett className="h-96" />
              )}
            </Karte>
          </div>
        </ReiterInhalt>
        <ReiterInhalt value="limits">
          <Karte className="overflow-hidden">
            <KarteKopf titel="Profile und Risikolimits" untertitel="config/profile.json – stimmt laut tools/pruefe.py mit regeln.md Abschnitt 7 überein" />
            {konfig.data ? (
              <div className="overflow-x-auto">
                <table className="zahl w-full text-[13px]">
                  <thead>
                    <tr className="border-y border-rand text-[12px] text-text-3">
                      <th className="px-5 py-2.5 text-left font-medium">Parameter</th>
                      {PROFILE.map((p) => (
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
                    {LIMIT_ZEILEN.map(([schluessel, name, art]) => (
                      <tr key={schluessel} className="border-b border-rand/70 last:border-0">
                        <td className="px-5 py-2.5 text-text-2">{name}</td>
                        {PROFILE.map((p) => {
                          const w = Number(konfig.data.profile.profile[p]?.[schluessel]);
                          return (
                            <td key={p} className="px-5 py-2.5 text-right font-medium text-text">
                              {art === "x" ? `${w.toLocaleString("de-DE")}x` : prozent(w, false, 0)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Skelett className="m-5 h-60" />
            )}
          </Karte>
        </ReiterInhalt>
        <ReiterInhalt value="kosten">
          {konfig.data && (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {[
                ["Gebühr je Order", `${Number(konfig.data.kosten.gebuehr_je_order).toLocaleString("de-DE", { style: "currency", currency: "EUR" })}`],
                ["Mindestorder", `${Number(konfig.data.kosten.mindestorder).toLocaleString("de-DE", { style: "currency", currency: "EUR" })}`],
                ["Spread Aktien/ETFs", prozent(Number(konfig.data.kosten.spread.aktie), false)],
                ["Spread Zertifikate", prozent(Number(konfig.data.kosten.spread.ko), false)],
                ["Cash-Zins", `${prozent(Number(konfig.data.kosten.cash_zins_pa), false, 0)} p. a.`],
                ["Knock-out Long Aufzinsung", `${prozent(Number(konfig.data.kosten.ko_long_aufzinsung_pa), false, 0)} p. a.`],
                ["Faktor-Kosten", `${prozent(Number(konfig.data.kosten.faktor_kosten_pa), false, 0)} p. a.`],
                ["Verlust ohne Stop (Aktie)", prozent(Number(konfig.data.kosten.verlust_ohne_stop.aktie), false, 0)],
                ["Verlust ohne Stop (Zertifikat)", prozent(Number(konfig.data.kosten.verlust_ohne_stop.ko), false, 0)],
              ].map(([n, w]) => (
                <Karte key={n} className="p-5">
                  <div className="text-[12.5px] text-text-3">{n}</div>
                  <div className="zahl mt-1 text-[20px] font-semibold text-text">{w}</div>
                </Karte>
              ))}
            </div>
          )}
        </ReiterInhalt>
        <ReiterInhalt value="universum">
          {konfig.data && (
            <div className="grid gap-4 lg:grid-cols-2">
              <Karte className="overflow-hidden">
                <KarteKopf titel="Börsen und Handelszeiten" untertitel="config/universum.json" />
                <div className="divide-y divide-rand">
                  {Object.entries(konfig.data.universum.boersen).map(([k, b]) => (
                    <div key={k} className="px-5 py-3">
                      <div className="flex items-center justify-between">
                        <span className="text-[13.5px] font-medium text-text">{b.name}</span>
                        <Abzeichen>{b.waehrung}</Abzeichen>
                      </div>
                      <div className="mt-0.5 text-[12.5px] text-text-3">
                        {b.oeffnung}–{b.schluss} ({b.zeitzone}) · {b.feiertage.length} Feiertage gepflegt
                        {b.fruehschluss && Object.keys(b.fruehschluss).length > 0 && ` · ${Object.keys(b.fruehschluss).length} Frühschlüsse`}
                      </div>
                    </div>
                  ))}
                </div>
              </Karte>
              <Karte className="overflow-hidden">
                <KarteKopf titel="Erlaubte Basiswerte für Zertifikate" untertitel="zusätzlich Aktien des Universums über 10 Mrd. Marktkapitalisierung" />
                <div className="divide-y divide-rand">
                  {Object.entries(konfig.data.universum.basiswerte).map(([t, b]) => (
                    <div key={t} className="flex items-center justify-between px-5 py-2.5 text-[13px]">
                      <span className="text-text">{b.name}</span>
                      <Mono className="text-text-3">{t}</Mono>
                    </div>
                  ))}
                </div>
              </Karte>
            </div>
          )}
        </ReiterInhalt>
      </Reiter>
    </div>
  );
}

// --------------------------------------------------------------------------
// Einrichtung & Aufbau

export function Einrichtung() {
  const status = useQuery({ queryKey: ["status"], queryFn: () => api<StatusDaten>("/api/spiel/status") });
  const [dokument, setDokument] = useState<string | null>(null);
  const dok = useQuery({ queryKey: ["dokument", dokument], queryFn: () => api<Dokument>(`/api/spiel/dokument?pfad=${dokument}`), enabled: !!dokument });
  if (status.isError) return <Fehleranzeige fehler={status.error} />;
  const s = status.data;
  const gruppen = s ? [...new Set(s.arbeitspakete.map((a) => a.gruppe))] : [];
  const offeneFragen = s?.auslegungsfragen.filter((f) => !f.entschieden).length ?? 0;
  return (
    <div className="einblenden">
      <Seitenkopf
        titel="Einrichtung & Aufbau"
        untertitel="Projektstatus aus STATUS.md: Arbeitspakete, Entscheidungen der Auftraggeber und offene Auslegungsfragen."
        aktionen={
          <>
            {["AUFTRAG_PHASE1.md", "AUFTRAG_WEBUI.md", "KONZEPT.md", "STATUS.md"].map((d) => (
              <Knopf key={d} klein onClick={() => setDokument(d)}>
                <FileText className="size-3.5" /> {d.replace(".md", "")}
              </Knopf>
            ))}
          </>
        }
      />
      {!s ? (
        <Skelett className="h-96 rounded-2xl" />
      ) : (
        <>
          <Karte className="glanz mb-4 p-5">
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <div className="text-[12px] text-text-3">Phase</div>
                <div className="mt-1 text-[14px] font-medium text-text">{s.kopf.phase ?? "–"}</div>
              </div>
              <div>
                <div className="text-[12px] text-text-3">Startdatum</div>
                <div className="mt-1 text-[14px] font-medium text-text">{s.kopf.startdatum ?? "–"}</div>
              </div>
              <div>
                <div className="text-[12px] text-text-3">Letzte Session</div>
                <div className="mt-1 text-[14px] font-medium text-text">{s.kopf.letzte_session ?? "–"}</div>
              </div>
            </div>
          </Karte>
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
            <div className="space-y-4">
              {gruppen.map((g) => {
                const pakete = s.arbeitspakete.filter((a) => a.gruppe === g);
                const erledigt = pakete.filter((a) => a.erledigt).length;
                return (
                  <Karte key={g}>
                    <KarteKopf titel={g} untertitel={`${erledigt} von ${pakete.length} erledigt`} />
                    <div className="px-5">
                      <div className="h-1.5 overflow-hidden rounded-full bg-flaeche-3">
                        <div className="h-full rounded-full bg-gut" style={{ width: `${(erledigt / Math.max(1, pakete.length)) * 100}%` }} />
                      </div>
                    </div>
                    <ul className="space-y-0.5 p-3">
                      {pakete.map((a) => (
                        <li key={a.kennung + a.titel} className="flex items-start gap-2.5 rounded-lg px-2 py-1.5 text-[13px]">
                          {a.erledigt ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-gut" /> : <Circle className="mt-0.5 size-4 shrink-0 text-text-3" />}
                          <span className={cn("min-w-0 break-words [overflow-wrap:anywhere]", a.erledigt ? "text-text-2" : "text-text")}>
                            <span className="font-medium">{a.kennung}</span> {a.titel}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </Karte>
                );
              })}
            </div>
            <div className="space-y-4">
              <Karte>
                <KarteKopf
                  titel="Auslegungsfragen"
                  untertitel="Konservativ umgesetzt; Bestätigung oder Änderung durch die Auftraggeber"
                  aktion={offeneFragen ? <Abzeichen ton="warnung">{offeneFragen} offen</Abzeichen> : <Abzeichen ton="gut">alle entschieden</Abzeichen>}
                />
                <Accordion.Root type="multiple" className="px-3 pb-3">
                  {s.auslegungsfragen.map((f) => (
                    <Accordion.Item key={`${f.abschnitt}-${f.nummer}`} value={`${f.abschnitt}-${f.nummer}`} className="border-b border-rand last:border-0">
                      <Accordion.Header>
                        <Accordion.Trigger className="group flex w-full items-start gap-3 px-2 py-3 text-left">
                          <span className="zahl mt-0.5 w-6 shrink-0 text-[12px] font-semibold text-text-3">{f.nummer}.</span>
                          <span className="line-clamp-2 flex-1 text-[13px] text-text">{f.text}</span>
                          {f.entschieden ? <Abzeichen ton="gut">entschieden</Abzeichen> : <Abzeichen ton="warnung">offen</Abzeichen>}
                          <ChevronDown className="mt-0.5 size-4 shrink-0 text-text-3 transition-transform group-data-[state=open]:rotate-180" />
                        </Accordion.Trigger>
                      </Accordion.Header>
                      <Accordion.Content className="px-11 pb-3 text-[13px] leading-relaxed whitespace-pre-line text-text-2">
                        {f.text}
                        <div className="mt-2 text-[12px] text-text-3">{f.abschnitt}</div>
                      </Accordion.Content>
                    </Accordion.Item>
                  ))}
                </Accordion.Root>
              </Karte>
              <Karte>
                <KarteKopf titel="Entscheidungen der Auftraggeber" untertitel={`${s.entscheidungen.length} vermerkt in STATUS.md`} />
                <ol className="space-y-3 px-5 pb-5">
                  {s.entscheidungen.map((e) => (
                    <li key={e.nummer} className="flex gap-3 text-[13px] leading-relaxed">
                      <span className="zahl w-6 shrink-0 font-semibold text-text-3">{e.nummer}.</span>
                      <span className="text-text-2">{e.text}</span>
                    </li>
                  ))}
                </ol>
              </Karte>
            </div>
          </div>
        </>
      )}
      <Dialog offen={!!dokument} setOffen={(o) => !o && setDokument(null)} titel={dokument ?? ""} breit>
        {dok.data ? <Markdown text={dok.data.inhalt} /> : <Skelett className="h-80" />}
      </Dialog>
    </div>
  );
}

// --------------------------------------------------------------------------
// Prüfung & Audit

interface PruefErgebnis {
  ok: boolean;
  befunde: Befund[];
  zusammenfassung: string;
}

export function Pruefung() {
  const pruefung = useMutation({ mutationFn: () => api<PruefErgebnis>("/api/spiel/pruefung", { methode: "POST" }) });
  const log = useQuery({ queryKey: ["git"], queryFn: () => api<Commit[]>("/api/spiel/git?anzahl=150") });
  const [commit, setCommit] = useState<string | null>(null);
  const detail = useQuery({ queryKey: ["commit", commit], queryFn: () => api<{ hash: string; text: string; zeit: string; diff: string; gekuerzt: boolean }>(`/api/spiel/git/${commit}`), enabled: !!commit });
  const e = pruefung.data;
  return (
    <div className="einblenden">
      <Seitenkopf
        titel="Prüfung & Audit"
        untertitel="tools/pruefe.py kontrolliert unabhängig: Nachrechnung, Journal-Bezug, Kursbelege, Nur-Anhängen, Limits und Konfiguration. Die Git-Historie ist die Prüfspur."
        aktionen={
          <Knopf variante="primaer" onClick={() => pruefung.mutate()} laedt={pruefung.isPending}>
            <PlayCircle className="size-4" /> Prüfung ausführen
          </Knopf>
        }
      />
      <Karte className="mb-4">
        {pruefung.isError ? (
          <Fehleranzeige fehler={pruefung.error} />
        ) : !e ? (
          <Leer icon={<ShieldCheck className="size-5" />} titel="Noch nicht geprüft" text="Die Prüfung läuft lesend im Spiel-Repository und dauert wenige Sekunden." />
        ) : (
          <div className="p-5">
            <div className={cn("flex items-center gap-3 rounded-xl px-4 py-3", e.ok ? "bg-gut-flaeche text-gut" : "bg-schlecht-flaeche text-schlecht")}>
              {e.ok ? <ShieldCheck className="size-5" /> : <ShieldAlert className="size-5" />}
              <span className="text-[14px] font-medium">{e.zusammenfassung}</span>
            </div>
            {e.befunde.length > 0 && (
              <ul className="mt-3 divide-y divide-rand">
                {e.befunde.map((b, i) => (
                  <li key={i} className="flex items-start gap-3 py-2.5 text-[13px]">
                    {b.stufe === "FEHLER" ? <ShieldAlert className="mt-0.5 size-4 shrink-0 text-schlecht" /> : <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warnung" />}
                    <div>
                      <Abzeichen ton={b.stufe === "FEHLER" ? "schlecht" : "warnung"}>{b.pruefung}</Abzeichen>
                      <p className="mt-1 text-text-2">{b.text}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Karte>
      <Karte>
        <KarteKopf titel="Git-Historie" icon={<GitCommitHorizontal className="size-4" />} untertitel="Jede Session, Buchung und Regeländerung ist ein Commit" />
        {log.data && log.data.length === 0 ? (
          <Leer titel="Keine Git-Historie verfügbar" text="Das Repository hat keine Commits oder Git ist im Container nicht installiert." />
        ) : log.data ? (
          <ol className="relative mx-5 mb-5 border-l border-rand">
            {log.data.map((c) => (
              <li key={c.hash} className="relative">
                <button onClick={() => setCommit(c.hash)} className="flex w-full items-start gap-3 rounded-lg py-2 pr-2 pl-5 text-left hover:bg-flaeche-2">
                  <span className={cn("absolute top-3.5 -left-[5px] size-2.5 rounded-full ring-4 ring-[var(--flaeche)]", c.text.startsWith("session:") ? "bg-akzent" : c.text.startsWith("aufbau:") ? "bg-ausgewogen" : "bg-text-3")} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-medium text-text">{c.text}</div>
                    <div className="text-[12px] text-text-3">
                      <Mono>{c.kurz}</Mono> · {relativ(c.zeit)} · {c.statistik || "keine Dateiänderungen"}
                    </div>
                  </div>
                </button>
              </li>
            ))}
          </ol>
        ) : (
          <Skelett className="m-5 h-60" />
        )}
      </Karte>
      <Dialog offen={!!commit} setOffen={(o) => !o && setCommit(null)} titel={detail.data?.text.split("\n")[0] ?? "Commit"} beschreibung={detail.data ? `${detail.data.hash.slice(0, 12)} · ${zeit(detail.data.zeit)}` : undefined} breit>
        {detail.data ? (
          <pre className="max-h-[60vh] overflow-auto rounded-lg border border-rand bg-flaeche-2 p-3 font-mono text-[11.5px] leading-relaxed">
            {detail.data.diff.split("\n").map((z, i) => (
              <div key={i} className={cn(z.startsWith("+") && !z.startsWith("+++") && "text-gut", z.startsWith("-") && !z.startsWith("---") && "text-schlecht", z.startsWith("@@") && "text-akzent")}>
                {z || " "}
              </div>
            ))}
          </pre>
        ) : (
          <Skelett className="h-60" />
        )}
      </Dialog>
    </div>
  );
}
