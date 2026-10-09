import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { ArrowLeft, BookOpenText, CandlestickChart, ExternalLink, FileText, Lightbulb, Link2, Scale, ShieldCheck } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { Ergebnis, StatusAbzeichen } from "@/components/Bausteine";
import { Kerzendiagramm, type Markierung, type Preislinie } from "@/components/diagramme/Kerzendiagramm";
import { szenarienLesen, SzenarioBalken } from "@/components/diagramme/Szenarien";
import { Markdown } from "@/components/Markdown";
import { Abzeichen, Fehleranzeige, Karte, Leer, Mono, PROFIL_FARBE, PROFIL_NAME, Skelett } from "@/components/ui";
import { api, ApiFehler, type Akte as AkteTyp, type Trade } from "@/lib/api";
import { cn } from "@/lib/cn";
import { automatischAusloeser, datum, euro, faktor, frei, prozent, zahl, zeit } from "@/lib/format";

function feld(felder: Record<string, string>, praefix: string): string | undefined {
  const schluessel = Object.keys(felder).find((k) => k.startsWith(praefix));
  return schluessel ? felder[schluessel] : undefined;
}

function Abschnitt({ titel, icon, children, className }: { titel: string; icon?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn("border-t border-rand py-6 first:border-0 first:pt-0", className)}>
      <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold tracking-wide text-text-3 uppercase">
        {icon}
        {titel}
      </h2>
      {children}
    </section>
  );
}

export function Akte() {
  const { id } = useParams({ strict: false }) as { id: string };
  const akte = useQuery({ queryKey: ["akte", id], queryFn: () => api<AkteTyp>(`/api/spiel/journal/${id}`) });

  if (akte.isError)
    return akte.error instanceof ApiFehler && akte.error.status === 404 ? (
      <Karte>
        <Leer titel={`${id} nicht gefunden`} aktion={<Link to="/entscheidungen" className="text-[13px] text-akzent">Zur Zeitachse</Link>} />
      </Karte>
    ) : (
      <Fehleranzeige fehler={akte.error} erneut={() => void akte.refetch()} />
    );
  if (!akte.data) return <Skelett className="h-[600px] rounded-2xl" />;
  return <AkteInhalt a={akte.data} />;
}

function AkteInhalt({ a }: { a: AkteTyp }) {
  const [roh, setRoh] = useState(false);
  const kauf = a.folge.find((t) => t.aktion === "kauf" && t.journal_id === a.id);
  const szenarien = szenarienLesen(feld(a.felder, "szenarien"));
  const quellen = useMemo(() => [...new Set((feld(a.felder, "quellen") ?? "").match(/https?:\/\/[^\s,;)]+/g) ?? [])], [a.felder]);

  const linien = useMemo<Preislinie[]>(() => {
    const l: Preislinie[] = [];
    if (kauf?.kurs_basiswert) l.push({ preis: kauf.kurs_basiswert, titel: "Einstieg", art: "einstieg" });
    if (kauf?.stop) l.push({ preis: kauf.stop, titel: "Stop", art: "stop" });
    if (kauf?.kursziel) l.push({ preis: kauf.kursziel, titel: "Ziel", art: "ziel" });
    const barriere = /Barriere ([\d.]+)/.exec(kauf?.bemerkung ?? "")?.[1];
    if (barriere) l.push({ preis: Number(barriere), titel: "Barriere", art: "barriere" });
    return l;
  }, [kauf]);
  const markierungen = useMemo<Markierung[]>(
    () =>
      a.folge
        .filter((t) => ["kauf", "verkauf", "knockout", "dividende"].includes(t.aktion))
        .map((t) => ({
          datum: (t.kurs_zeit || t.zeit).slice(0, 10),
          text: t.aktion === "kauf" ? "Kauf" : t.aktion === "verkauf" ? `Verkauf${t.grund !== "order" ? ` (${t.grund})` : ""}` : t.aktion === "knockout" ? "Knock-out" : "Dividende",
          art: t.aktion === "kauf" ? "kauf" : t.aktion === "dividende" ? "ereignis" : "verkauf",
        })),
    [a.folge],
  );

  return (
    <div className="einblenden">
      <Link to="/entscheidungen" className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-text-3 hover:text-text">
        <ArrowLeft className="size-4" /> Zeitachse
      </Link>
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-2 text-[12.5px] text-text-3">
          {a.portfolio && (
            <span className="inline-flex items-center gap-1.5 font-medium text-text-2">
              <span className="size-2 rounded-full" style={{ background: PROFIL_FARBE[a.portfolio] }} />
              {PROFIL_NAME[a.portfolio]}
            </span>
          )}
          <span>·</span>
          <Mono>{a.id}</Mono>
          <span>·</span>
          <span>{zeit(a.zeit)}</span>
          <span>·</span>
          <span>Auftraggeber {a.person}</span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-[28px] font-semibold tracking-[-0.02em] text-text">{a.instrument}</h1>
          <StatusAbzeichen status={a.status} />
        </div>
        {feld(a.felder, "aktion") && <p className="mt-1 text-[14px] text-text-2">{feld(a.felder, "aktion")}</p>}
      </header>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Karte className="p-6 sm:p-8">
          {roh ? (
            <Markdown text={a.text} />
          ) : (
            <>
              <Abschnitt titel="These" icon={<Lightbulb className="size-4" />}>
                <p className="text-[16px] leading-relaxed text-text">{feld(a.felder, "these") ?? "–"}</p>
              </Abschnitt>
              {szenarien.length > 0 && (
                <Abschnitt titel="Szenarien">
                  <SzenarioBalken szenarien={szenarien} />
                </Abschnitt>
              )}
              <Abschnitt titel="Plan">
                <dl className="grid gap-4 sm:grid-cols-2">
                  <Absatz titel="Katalysator und Zeithorizont" text={feld(a.felder, "katalysator")} />
                  <Absatz titel="Einstieg, Stop, Kursziel" text={feld(a.felder, "einstieg")} />
                  <Absatz titel="Positionsgröße und Risikorechnung" text={feld(a.felder, "positionsgröße")} breit />
                </dl>
              </Abschnitt>
              {a.basiswert && (
                <Abschnitt titel={`Kursverlauf ${a.basiswert}`} icon={<CandlestickChart className="size-4" />}>
                  <Kerzendiagramm kerzen={a.kerzen} linien={linien} markierungen={markierungen} />
                  <p className="mt-2 text-[12px] text-text-3">Tageskerzen aus data/historie/. Linien: Einstieg, Stop, Kursziel{linien.some((l) => l.art === "barriere") && ", Barriere beim Kauf"}.</p>
                </Abschnitt>
              )}
              <Abschnitt titel="Ausführung und Verlauf" icon={<Scale className="size-4" />}>
                <Verlauf folge={a.folge} />
              </Abschnitt>
              {a.limit_schnappschuesse.length > 0 && (
                <Abschnitt titel="Limitprüfung bei Ausführung" icon={<ShieldCheck className="size-4" />}>
                  {a.limit_schnappschuesse.map((s) => (
                    <Limitschnappschuss key={s.trade_id} s={s} />
                  ))}
                </Abschnitt>
              )}
              <Abschnitt titel="Unsicherheiten">
                <p className="text-[14px] leading-relaxed text-text-2">{feld(a.felder, "unsicherheiten") ?? "–"}</p>
              </Abschnitt>
              <Abschnitt titel="Quellen" icon={<Link2 className="size-4" />}>
                {quellen.length ? (
                  <ul className="space-y-1.5">
                    {quellen.map((q) => (
                      <li key={q}>
                        <a href={q} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1.5 text-[13.5px] break-all text-akzent hover:underline">
                          <ExternalLink className="size-3.5 shrink-0" /> {q}
                        </a>
                      </li>
                    ))}
                  </ul>
                ) : null}
                <p className="mt-2 text-[12.5px] text-text-3">{feld(a.felder, "quellen")}</p>
              </Abschnitt>
            </>
          )}
          <button onClick={() => setRoh((r) => !r)} className="mt-2 inline-flex items-center gap-1.5 text-[12.5px] text-text-3 hover:text-text">
            <FileText className="size-3.5" /> {roh ? "Aufbereitete Ansicht" : "Originaltext aus dem Journal"}
          </button>
        </Karte>

        <aside className="space-y-4 xl:sticky xl:top-20 xl:self-start">
          <Karte className="p-5">
            <div className="text-[12px] font-medium text-text-3">
              Ergebnis inkl. Kosten{a.ergebnis_art === "unrealisiert" ? " (unrealisiert, letzter Schlusskurs)" : ""}
            </div>
            <Ergebnis wert={a.ergebnis_eur} className="mt-1 block text-[26px] font-semibold tracking-[-0.02em]" />
            <dl className="mt-4 space-y-2.5 text-[13px]">
              <Zeile label="Status" wert={<StatusAbzeichen status={a.status} />} />
              {kauf && <Zeile label="Kauf" wert={`${frei(kauf.stueck)} × ${euro(kauf.kurs)}`} />}
              {kauf && <Zeile label="Einsatz" wert={euro(-(kauf.betrag_eur ?? 0) - (kauf.gebuehr_eur ?? 0))} />}
              {kauf?.hebel != null && kauf.hebel !== 1 && <Zeile label="Hebel" wert={faktor(kauf.hebel)} />}
              {kauf && <Zeile label="Stop / Ziel" wert={`${kauf.stop != null ? zahl(kauf.stop) : "–"} / ${kauf.kursziel != null ? zahl(kauf.kursziel) : "–"}`} />}
              {a.position && <Zeile label="Position" wert={<Abzeichen ton="akzent">{a.position.id} offen</Abzeichen>} />}
            </dl>
          </Karte>
          <Karte className="p-5">
            <div className="mb-3 text-[13px] font-semibold text-text">Verknüpfungen</div>
            <ul className="space-y-2 text-[13px]">
              {a.erwaehnt_in.map((e) => (
                <li key={e.id}>
                  <Link to={e.art === "S" ? "/sessions" : "/entscheidungen/$id"} params={e.art === "S" ? undefined : { id: e.id }} hash={e.art === "S" ? e.id : undefined} className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-flaeche-2">
                    <span className="text-text-2">{e.art === "S" ? "Session-Eintrag" : "Journal"}</span>
                    <Mono className="text-text-3">{e.id}</Mono>
                  </Link>
                </li>
              ))}
              {a.reviews.map((r) => (
                <li key={r.pfad}>
                  <Link to="/analyse/reviews" search={{ datei: r.pfad }} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-text-2 hover:bg-flaeche-2">
                    <BookOpenText className="size-3.5" /> {r.titel}
                  </Link>
                </li>
              ))}
              {a.lessons.map((l) => (
                <li key={l.id} className="px-2 py-1.5 text-text-2">
                  {l.id} {l.titel}
                </li>
              ))}
              {!a.erwaehnt_in.length && !a.reviews.length && !a.lessons.length && <li className="text-text-3">Keine Verweise.</li>}
            </ul>
          </Karte>
        </aside>
      </div>
    </div>
  );
}

function Zeile({ label, wert }: { label: string; wert: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-text-3">{label}</dt>
      <dd className="zahl text-right font-medium text-text">{wert}</dd>
    </div>
  );
}

function Absatz({ titel, text, breit }: { titel: string; text?: string; breit?: boolean }) {
  return (
    <div className={cn("rounded-xl border border-rand bg-flaeche-2 p-4", breit && "sm:col-span-2")}>
      <dt className="text-[12px] font-medium text-text-3">{titel}</dt>
      <dd className="mt-1 text-[13.5px] leading-relaxed text-text">{text ?? "–"}</dd>
    </div>
  );
}

const AKTION_TEXT: Record<string, string> = {
  vormerkung: "Order vorgemerkt",
  kauf: "Kauf ausgeführt",
  verkauf: "Verkauf ausgeführt",
  knockout: "Knock-out",
  dividende: "Dividende gutgeschrieben",
  split: "Split",
  aenderung: "Stop/Ziel geändert",
  storno: "Order storniert",
  verfall: "Order verfallen",
};

function Verlauf({ folge }: { folge: Trade[] }) {
  if (!folge.length) return <p className="text-[13.5px] text-text-3">Keine Ausführung – die Order wurde nicht gebucht (z. B. von tools/limits.py abgelehnt).</p>;
  return (
    <ol className="relative space-y-4 border-l border-rand pl-5">
      {folge.map((t) => (
        <li key={`${t.profil}-${t.trade_id}`} className="relative">
          <span
            className={cn(
              "absolute top-1 -left-[25px] size-2.5 rounded-full ring-4 ring-[var(--flaeche)]",
              t.aktion === "kauf" ? "bg-akzent" : t.aktion === "verkauf" ? "bg-text" : t.aktion === "verfall" || t.aktion === "knockout" ? "bg-schlecht" : "bg-text-3",
            )}
          />
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-[13.5px] font-medium text-text">
              {AKTION_TEXT[t.aktion] ?? t.aktion}
              {t.grund !== "order" && t.aktion !== "dividende" && <span className="text-text-3"> · Auslöser {t.grund}</span>}
              {automatischAusloeser(t.bemerkung) && (
                <Abzeichen ton="akzent" className="ml-2 align-middle">
                  automatisch ausgeführt · {automatischAusloeser(t.bemerkung)}
                </Abzeichen>
              )}
            </span>
            <span className="text-[12px] text-text-3">{zeit(t.zeit)}</span>
          </div>
          <div className="zahl mt-0.5 text-[12.5px] text-text-2">
            {t.stueck != null && <>{frei(t.stueck)} Stück · </>}
            {t.kurs_basiswert != null && <>Basiswert {zahl(t.kurs_basiswert)} ({t.kursquelle}) · </>}
            {t.betrag_eur != null && t.betrag_eur !== 0 && (
              <>
                Betrag <Ergebnis wert={t.betrag_eur} />
              </>
            )}
            {t.bemerkung && <span className="block text-text-3">{t.bemerkung}</span>}
          </div>
        </li>
      ))}
    </ol>
  );
}

const KENNZAHL_NAMEN: [string, string, string | null, "max" | "min" | null][] = [
  ["einzelposition", "Einzelposition", "max_einzelposition", "max"],
  ["zertifikate_anteil", "Zertifikate-Anteil", "max_anteil_zertifikate", "max"],
  ["exposure", "Gesamt-Exposure", "max_exposure", "max"],
  ["cashquote", "Cashquote nach Order", "min_cashquote", "min"],
  ["risiko_quote", "Risiko je Trade", "risiko_grenze", "max"],
];

function Limitschnappschuss({ s }: { s: AkteTyp["limit_schnappschuesse"][number] }) {
  const k = s.kennzahlen as Record<string, number>;
  return (
    <div className="overflow-x-auto rounded-xl border border-rand">
      <table className="zahl w-full text-[13px]">
        <thead className="bg-flaeche-2 text-left text-[12px] text-text-3">
          <tr>
            <th className="px-3 py-2 font-medium">Regel</th>
            <th className="px-3 py-2 text-right font-medium">Istwert</th>
            <th className="px-3 py-2 text-right font-medium">Grenze</th>
            <th className="px-3 py-2 font-medium">Ergebnis</th>
          </tr>
        </thead>
        <tbody>
          {KENNZAHL_NAMEN.map(([schluessel, name, grenzschluessel, art]) => {
            const ist = k[schluessel];
            const grenze = grenzschluessel === "risiko_grenze" ? k.risiko_grenze : s.grenzen[grenzschluessel ?? ""];
            const istX = schluessel === "exposure";
            const ok = art === "max" ? ist <= grenze : ist >= grenze;
            return (
              <tr key={schluessel} className="border-t border-rand text-text-2">
                <td className="px-3 py-2">{name}</td>
                <td className="px-3 py-2 text-right text-text">{istX ? faktor(ist) : prozent(ist, false)}</td>
                <td className="px-3 py-2 text-right">
                  {art === "max" ? "≤ " : "≥ "}
                  {istX ? faktor(grenze) : prozent(grenze, false)}
                </td>
                <td className="px-3 py-2">{ok ? <Abzeichen ton="gut">eingehalten</Abzeichen> : <Abzeichen ton="schlecht">verletzt</Abzeichen>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="border-t border-rand bg-flaeche-2 px-3 py-2 text-[12px] text-text-3">
        {s.trade_id} · {zeit(s.zeit)} · Portfoliowert vorher {euro(k.nav_vorher)} · Verlust bis Stop {prozent(k.verlust_bis_stop, false, 1)} · Risiko {euro(k.risiko_eur)} ·
        Stand {datum(s.zeit)}
      </div>
    </div>
  );
}
