import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { AlertTriangle, ArrowRight, Bot, CalendarCheck2, Flag, History, Newspaper, NotebookPen, Rocket } from "lucide-react";
import { useState } from "react";

import { EntscheidungsZeile, SessionKarte, TerminZeile } from "@/components/Bausteine";
import { NewsListe } from "@/components/News";
import { NavDiagramm, Sparkline } from "@/components/diagramme/NavDiagramm";
import { useUeberblick } from "@/components/layout/AppRahmen";
import { Abzeichen, Delta, Fehleranzeige, Karte, KarteKopf, Leer, PROFIL_FARBE, PROFIL_NAME, Seitenkopf, Skelett, StufenAbzeichen } from "@/components/ui";
import { api, PROFILE, type Kennzahlen, type Lauf, type NavDaten, type NewsMeldung, type Pflichtschritt, type Profil } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { datum, euro, faktor, prozent, relativ } from "@/lib/format";
import { LaufStatusAbzeichen, laufText } from "@/seiten/Laeufe";

function gruss(): string {
  const stunde = new Date().getHours();
  return stunde < 11 ? "Guten Morgen" : stunde < 18 ? "Guten Tag" : "Guten Abend";
}

export function Cockpit() {
  const { sitzung } = useAuth();
  const ueberblick = useUeberblick();
  const nav = useQuery({ queryKey: ["nav"], queryFn: () => api<NavDaten>("/api/spiel/nav") });
  const [auswahl, setAuswahl] = useState<"alle" | Profil>("alle");

  if (ueberblick.isError) return <Fehleranzeige fehler={ueberblick.error} erneut={() => void ueberblick.refetch()} />;
  const daten = ueberblick.data;
  const profile = PROFILE.filter((p) => daten?.profile[p]);
  const stand = profile.length ? daten?.profile[profile[0]]?.stand : undefined;

  return (
    <div className="einblenden">
      <Seitenkopf
        titel={`${gruss()}, ${sitzung?.benutzer?.anzeigename ?? ""}`}
        untertitel={
          daten?.gestartet ? (
            <>
              Bewertungsstand {datum(stand)} · Spielstart {datum(daten.profile[profile[0]]?.startdatum)}
              {daten.repo.demo && " · Demo-Daten mit simulierten Kursen"}
            </>
          ) : (
            "Das Spiel ist noch nicht gestartet."
          )
        }
        aktionen={
          <Link to="/entscheidungen" className="inline-flex h-9 items-center gap-2 rounded-lg border border-rand bg-flaeche-2 px-3 text-[13px] font-medium text-text hover:border-rand-stark">
            <NotebookPen className="size-4" /> Alle Entscheidungen
          </Link>
        }
      />

      {daten && daten.einrichtung_offen.length > 0 && <EinrichtungsHinweis schritte={daten.einrichtung_offen} />}

      {!daten ? (
        <div className="grid gap-4 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skelett key={i} className="h-[208px] rounded-2xl" />
          ))}
        </div>
      ) : !daten.gestartet ? (
        <>
          <NichtGestartet phase={daten.status.phase} ziel={daten.einrichtung_offen[0]?.link} />
          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
            <NewsKarte meldungen={daten.news} />
            <LaufKarte lauf={daten.letzter_lauf} />
          </div>
        </>
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-3" aria-label="Portfolios">
            {profile.map((p) => (
              <PortfolioKarte key={p} profil={p} k={daten.profile[p]!} werte={(nav.data?.profile[p] ?? []).map((z) => z.portfoliowert)} />
            ))}
          </section>

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
            <Karte>
              <KarteKopf
                titel="Wertentwicklung"
                untertitel={auswahl === "alle" ? "Rendite seit Start, alle Profile" : "Portfoliowert gegen die profilgerechte Benchmark"}
                aktion={<Segmente wert={auswahl} setWert={setAuswahl} profile={profile} />}
              />
              <div className="px-4 pb-4">
                {nav.data ? <NavDiagramm daten={nav.data} profile={auswahl === "alle" ? profile : [auswahl]} hoehe={380} /> : <Skelett className="h-[380px]" />}
              </div>
            </Karte>
            <div className="flex flex-col gap-4">
              <Karte>
                <KarteKopf titel="Fällig" icon={<CalendarCheck2 className="size-4" />} untertitel="Reviews laut tools/termine.py" />
                <div className="px-2 pb-3">
                  {daten.termine.length ? (
                    daten.termine.slice(0, 4).map((t) => <TerminZeile key={t.datei} t={t} />)
                  ) : (
                    <p className="px-3 pb-2 text-[13px] text-text-3">Keine Reviews fällig.</p>
                  )}
                  {daten.termine.length > 4 && <p className="px-3 text-[12px] text-text-3">und {daten.termine.length - 4} weitere</p>}
                </div>
              </Karte>
              <LaufKarte lauf={daten.letzter_lauf} />
              <Karte className="flex-1">
                <KarteKopf
                  titel="Letzte Sessions"
                  icon={<History className="size-4" />}
                  aktion={
                    <Link to="/sessions" className="text-[12.5px] text-text-3 hover:text-text">
                      Alle
                    </Link>
                  }
                />
                <div className="space-y-2 px-4 pb-4">
                  {daten.letzte_sessions.length ? (
                    daten.letzte_sessions.slice(0, 3).map((s) => <SessionKarte key={s.id} s={s} />)
                  ) : (
                    <p className="text-[13px] text-text-3">Noch keine Session-Einträge.</p>
                  )}
                </div>
              </Karte>
            </div>
          </div>

          <div className="mt-4">
            <NewsKarte meldungen={daten.news} />
          </div>

          <Karte className="mt-4">
            <KarteKopf
              titel="Letzte Entscheidungen"
              untertitel="Journal-Einträge mit These, Ausführung und Ergebnis"
              aktion={
                <Link to="/entscheidungen" className="inline-flex items-center gap-1 text-[12.5px] text-text-3 hover:text-text">
                  Zeitachse <ArrowRight className="size-3.5" />
                </Link>
              }
            />
            <div className="px-2 pb-3">
              {daten.letzte_entscheidungen.map((e) => (
                <EntscheidungsZeile key={e.id} e={e} />
              ))}
              {!daten.letzte_entscheidungen.length && <Leer titel="Noch keine Entscheidungen" />}
            </div>
          </Karte>
        </>
      )}
    </div>
  );
}

function Segmente({ wert, setWert, profile }: { wert: "alle" | Profil; setWert: (w: "alle" | Profil) => void; profile: Profil[] }) {
  const optionen: ("alle" | Profil)[] = ["alle", ...profile];
  return (
    <div className="flex rounded-lg border border-rand bg-flaeche-2 p-0.5" role="radiogroup" aria-label="Ansicht">
      {optionen.map((o) => (
        <button
          key={o}
          role="radio"
          aria-checked={wert === o}
          onClick={() => setWert(o)}
          className={cn(
            "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[12.5px] font-medium transition-colors",
            wert === o ? "bg-flaeche-3 text-text shadow-sm" : "text-text-3 hover:text-text",
          )}
        >
          {o !== "alle" && <span className="size-2 rounded-full" style={{ background: PROFIL_FARBE[o] }} />}
          <span className={cn(o !== "alle" && "hidden sm:inline")}>{o === "alle" ? "Alle" : PROFIL_NAME[o]}</span>
        </button>
      ))}
    </div>
  );
}

function PortfolioKarte({ profil, k, werte }: { profil: Profil; k: Kennzahlen; werte: number[] }) {
  return (
    <Link to="/portfolios/$profil" params={{ profil }} className="group block focus-visible:outline-none">
      <Karte className="relative overflow-hidden transition-all duration-200 group-hover:-translate-y-0.5 group-hover:border-rand-stark group-focus-visible:ring-2 group-focus-visible:ring-akzent">
        <div className="absolute inset-x-0 top-0 h-[3px]" style={{ background: PROFIL_FARBE[profil] }} />
        <div className="px-5 pt-5">
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-2 text-[13.5px] font-semibold text-text">
              <span className="size-2.5 rounded-[3px]" style={{ background: PROFIL_FARBE[profil] }} />
              {PROFIL_NAME[profil]}
            </span>
            {k.status !== "aktiv" ? <Abzeichen ton="schlecht">{k.status}</Abzeichen> : k.stufe > 0 ? <StufenAbzeichen stufe={k.stufe} /> : <Abzeichen>aktiv</Abzeichen>}
          </div>
          <div className="zahl mt-3 text-[30px] font-semibold tracking-[-0.025em] text-text">{euro(k.wert)}</div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-text-3">
            <span className="flex items-center gap-1">
              <Delta wert={k.rendite} /> seit Start
            </span>
            <span className="flex items-center gap-1">
              <Delta wert={k.gegen_bench} /> ggü. Benchmark
            </span>
          </div>
        </div>
        <div className="mt-2">
          <Sparkline werte={werte} farbe={PROFIL_FARBE[profil]} />
        </div>
        <dl className="grid grid-cols-3 border-t border-rand text-center">
          {[
            ["Cash", prozent(k.cashquote, false, 0)],
            ["Exposure", faktor(k.exposure)],
            ["Positionen", String(k.anzahl_positionen)],
          ].map(([label, wert]) => (
            <div key={label} className="px-2 py-2.5 [&:not(:first-child)]:border-l [&:not(:first-child)]:border-rand">
              <dt className="text-[11px] text-text-3">{label}</dt>
              <dd className="zahl text-[13px] font-semibold text-text">{wert}</dd>
            </div>
          ))}
        </dl>
      </Karte>
    </Link>
  );
}

function linkTeile(link: string | undefined): { to: string; hash?: string } {
  const [to, hash] = (link ?? "/einrichtung").split("#");
  return { to, hash };
}

function EinrichtungsHinweis({ schritte }: { schritte: Pflichtschritt[] }) {
  const erster = linkTeile(schritte[0].link);
  return (
    <Karte className="mb-4 border-warnung/40">
      <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-warnung-flaeche text-warnung">
          <AlertTriangle className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[13.5px] font-semibold text-text">Einrichtung noch nicht abgeschlossen</div>
          <p className="text-[12.5px] text-text-3">
            {schritte.map((s, i) => (
              <span key={s.schritt}>
                {i > 0 && " · "}
                <Link to={linkTeile(s.link).to} hash={linkTeile(s.link).hash} className="text-text-2 hover:text-text hover:underline">
                  {s.titel}
                </Link>
              </span>
            ))}
            {" – "}
            {schritte[0].text}
          </p>
        </div>
        <Link to={erster.to} hash={erster.hash} className="inline-flex h-9 shrink-0 items-center gap-2 rounded-lg bg-text px-3.5 text-[13px] font-medium text-bg hover:opacity-90">
          {schritte[0].titel} <ArrowRight className="size-4" />
        </Link>
      </div>
    </Karte>
  );
}

function NewsKarte({ meldungen }: { meldungen: NewsMeldung[] }) {
  return (
    <Karte>
      <KarteKopf
        titel="Neueste Meldungen"
        icon={<Newspaper className="size-4" />}
        untertitel="News-Speicher (RSS) mit Quelle und Datum"
        aktion={
          <Link to="/analyse/kurse" className="inline-flex items-center gap-1 text-[12.5px] text-text-3 hover:text-text">
            Je Wert <ArrowRight className="size-3.5" />
          </Link>
        }
      />
      <div className="px-2 pb-2">
        <NewsListe meldungen={meldungen} kompakt />
      </div>
    </Karte>
  );
}

function LaufKarte({ lauf }: { lauf: Lauf | null }) {
  return (
    <Karte>
      <KarteKopf
        titel="Letzter Claude-Lauf"
        icon={<Bot className="size-4" />}
        aktion={
          <Link to="/laeufe" className="text-[12.5px] text-text-3 hover:text-text">
            Alle
          </Link>
        }
      />
      <div className="px-5 pb-4">
        {lauf ? (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-[13px] font-medium text-text">{laufText(lauf)}</span>
              <LaufStatusAbzeichen status={lauf.status} />
            </div>
            <p className="text-[12px] text-text-3">
              {relativ(lauf.erstellt)} · {lauf.ausloeser === "zeitplan" ? "per Zeitplan" : "manuell"}
              {lauf.pruefung_ok != null && ` · Prüfung ${lauf.pruefung_ok ? "bestanden" : "mit Fehlern"}`}
            </p>
            {lauf.meldung && <p className="line-clamp-3 text-[12.5px] text-text-2">{lauf.meldung}</p>}
          </div>
        ) : (
          <p className="text-[13px] text-text-3">Noch kein Lauf. Sessions starten unter Claude-Läufe oder per Zeitplan.</p>
        )}
      </div>
    </Karte>
  );
}

function NichtGestartet({ phase, ziel }: { phase?: string; ziel?: string }) {
  const schritte = [
    ["Einrichtung", "Claude-Token, Kursdaten und News in der App hinterlegen und testen."],
    ["Testsession ohne Order", "Nachbuchen, Prüfen, Marktüberblick und Bericht einmal vollständig durchspielen (Claude-Läufe)."],
    ["Anlagerichtlinien", "Ziel, Risikobudget, Horizont und Ausgangsstrategie je Profil ausformulieren."],
    ["Freigabe und Start", "Nach der Freigabe startet ein Admin das Spiel in der Einrichtung (tools/init.py) – nie rückwirkend."],
  ];
  const link = linkTeile(ziel ?? "/einrichtung#spielstart");
  return (
    <Karte className="glanz overflow-hidden">
      <div className="grid gap-8 p-6 sm:p-8 lg:grid-cols-[1fr_1.2fr]">
        <div>
          <div className="mb-4 grid size-12 place-items-center rounded-2xl border border-rand bg-flaeche-2 text-text-2">
            <Rocket className="size-5" />
          </div>
          <h2 className="text-[22px] font-semibold tracking-[-0.02em] text-text">Noch kein Spielstart</h2>
          <p className="mt-2 text-[14px] leading-relaxed text-text-2">
            Die Werkzeuge sind fertig und geprüft. Sobald das Spiel in der Einrichtung gestartet ist, erscheinen hier Werte, Benchmarks und
            Entscheidungen.
          </p>
          {phase && <p className="mt-4 rounded-lg border border-rand bg-flaeche-2 px-3 py-2 text-[12.5px] text-text-3">Phase laut STATUS.md: {phase}</p>}
          <Link to={link.to} hash={link.hash} className="mt-5 inline-flex h-10 items-center gap-2 rounded-lg bg-text px-4 text-sm font-medium text-bg hover:opacity-90">
            Zur Einrichtung <ArrowRight className="size-4" />
          </Link>
        </div>
        <ol className="space-y-3">
          {schritte.map(([titel, text], i) => (
            <li key={titel} className="flex gap-3 rounded-xl border border-rand bg-flaeche/60 p-3.5">
              <span className="grid size-7 shrink-0 place-items-center rounded-full border border-rand-stark text-[12px] font-semibold text-text-2">{i + 1}</span>
              <div>
                <div className="flex items-center gap-2 text-[13.5px] font-medium text-text">
                  {titel} {i === 3 && <Flag className="size-3.5 text-text-3" />}
                </div>
                <p className="mt-0.5 text-[12.5px] text-text-3">{text}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </Karte>
  );
}
