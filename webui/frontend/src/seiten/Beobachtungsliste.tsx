import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Clock, ListFilter, Search } from "lucide-react";
import { useEffect, useState } from "react";

import { Abzeichen, Delta, Fehleranzeige, Karte, KarteKopf, Knopf, Leer, Skelett } from "@/components/ui";
import { api, type Beobachtung, type BeobachtungKandidaten, type BeobachtungKennzahl, type BeobachtungWert } from "@/lib/api";
import { cn } from "@/lib/cn";
import { faktor, prozent, relativ, zahl } from "@/lib/format";

const SEITE = 50;
/** Spalten der Tabelle; die gewählte Sortierung kommt als weitere Spalte dazu. */
const SPALTEN: BeobachtungKennzahl[] = ["rendite_1t", "rendite_5t", "rendite_20t", "abstand_hoch", "volumen_relativ_1t", "volatilitaet_20t"];
const FELD_KLASSE = "h-9 rounded-lg border border-rand bg-flaeche-2 px-3 text-[13px] text-text hover:border-rand-stark focus:border-akzent focus:ring-2 focus:ring-akzent/25 focus:outline-none";

/** Wert einer Kennzahl für die Anzeige; Renditen mit Vorzeichen und Symbol, Abstände als schlichte Prozentwerte. */
export function KennzahlWert({ id, art, e }: { id: BeobachtungKennzahl; art: string; e: BeobachtungWert }) {
  const wert = e[id];
  if (typeof wert !== "number") return <span className="text-text-3">–</span>;
  if ((art === "prozent" && id.startsWith("rendite_")) || id === "gap_1t") return <Delta wert={wert} />;
  const text = art === "preis" ? zahl(wert, wert < 10 ? 3 : 2) : art === "faktor" ? faktor(wert) : art === "prozent_abs" ? prozent(wert, false, 1) : prozent(wert, true);
  return <span>{text}</span>;
}

function Kennzeichen({ e }: { e: BeobachtungWert }) {
  return (
    <>
      {!e.handelbar && (
        <Abzeichen ton="schlecht" className="ml-1.5">
          <span title={e.grund ?? undefined}>nicht handelbar</span>
        </Abzeichen>
      )}
      {e.veraltet && (
        <Abzeichen ton="warnung" className="ml-1.5">
          alter Stand
        </Abzeichen>
      )}
    </>
  );
}

function Wertname({ e }: { e: BeobachtungWert }) {
  return (
    <div className="min-w-0">
      <div className="font-mono text-[12.5px] text-text">
        {e.ticker}
        <Kennzeichen e={e} />
      </div>
      {e.name && <div className="truncate text-[12px] text-text-3">{e.name}</div>}
    </div>
  );
}

function Kandidatenbloecke({ liste, kennzahlen }: { liste: string; kennzahlen: Beobachtung["kennzahlen"] }) {
  const kandidaten = useQuery({
    queryKey: ["beobachtung", "kandidaten", liste],
    queryFn: () => api<BeobachtungKandidaten>(`/api/spiel/beobachtung/kandidaten${liste ? `?liste=${encodeURIComponent(liste)}` : ""}`),
    placeholderData: keepPreviousData,
  });
  if (kandidaten.isError) return <Fehleranzeige fehler={kandidaten.error} erneut={() => void kandidaten.refetch()} />;
  if (!kandidaten.data) return <Skelett className="h-64" />;
  const art = (id: BeobachtungKennzahl) => kennzahlen.find((k) => k.id === id)?.art ?? "prozent";
  return (
    <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
      {kandidaten.data.bloecke.map((b) => (
        <Karte key={b.titel}>
          <KarteKopf titel={b.titel} untertitel={kennzahlen.find((k) => k.id === b.kennzahl)?.titel} />
          {b.werte.length ? (
            <ul className="px-5 pb-4">
              {b.werte.map((e) => (
                <li key={e.ticker} className="flex items-center justify-between gap-3 border-t border-rand py-2 first:border-0">
                  <Wertname e={e} />
                  <div className="zahl shrink-0 text-right text-[13px]">
                    <div className="font-medium text-text">
                      <KennzahlWert id={b.kennzahl} art={art(b.kennzahl)} e={e} />
                    </div>
                    <div className="text-[11.5px] text-text-3">
                      {zahl(e.kurs)} {e.waehrung}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-5 pb-4 text-[13px] text-text-3">Keine Werte in dieser Kategorie.</p>
          )}
        </Karte>
      ))}
    </div>
  );
}

export function Beobachtungsliste() {
  const [ansicht, setAnsicht] = useState<"kandidaten" | "tabelle">("kandidaten");
  const [liste, setListe] = useState("");
  const [eingabe, setEingabe] = useState("");
  const [suche, setSuche] = useState("");
  const [sortiert, setSortiert] = useState<BeobachtungKennzahl>("rendite_1t");
  const [aufsteigend, setAufsteigend] = useState(false);
  const [nurHandelbar, setNurHandelbar] = useState(true);
  const [seite, setSeite] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSuche(eingabe.trim());
      setSeite(0);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [eingabe]);

  const abfrage = new URLSearchParams({ sortiert, aufsteigend: String(aufsteigend), nur_handelbar: String(nurHandelbar), anzahl: String(SEITE), offset: String(seite * SEITE) });
  if (liste) abfrage.set("liste", liste);
  if (suche) abfrage.set("suche", suche);
  const daten = useQuery({
    queryKey: ["beobachtung", abfrage.toString()],
    queryFn: () => api<Beobachtung>(`/api/spiel/beobachtung?${abfrage}`),
    placeholderData: keepPreviousData,
    refetchInterval: 5 * 60_000,
  });

  if (daten.isError) return <Fehleranzeige fehler={daten.error} erneut={() => void daten.refetch()} />;
  if (!daten.data) return <Skelett className="h-72 rounded-2xl" />;
  const d = daten.data;
  if (!d.zeit) {
    return (
      <Karte>
        <Leer
          icon={<ListFilter className="size-5" />}
          titel="Noch keine Beobachtungsliste"
          text="Der Hintergrunddienst holt die Tageskerzen von rund 600 Aktien und ETFs beim nächsten Durchlauf und danach nach jedem Handelsschluss (ab 23:15 Uhr). Ob er läuft und ob der Abruf klappt, zeigt der Systemstatus in der Einrichtung."
        />
      </Karte>
    );
  }

  const art = (id: BeobachtungKennzahl) => d.kennzahlen.find((k) => k.id === id)?.art ?? "prozent";
  const titel = (id: BeobachtungKennzahl) => d.kennzahlen.find((k) => k.id === id)?.titel ?? id;
  const spalten = SPALTEN.includes(sortiert) ? SPALTEN : [...SPALTEN, sortiert];
  const seiten = Math.max(1, Math.ceil(d.gesamt / SEITE));
  const sortierbar = d.kennzahlen.filter((k) => k.id !== "kurs");

  function sortierenNach(id: BeobachtungKennzahl) {
    if (id === sortiert) setAufsteigend(!aufsteigend);
    else {
      setSortiert(id);
      setAufsteigend(false);
    }
    setSeite(0);
  }

  return (
    <div className="space-y-4">
      <Karte>
        <KarteKopf
          titel="Beobachtungsliste"
          icon={<ListFilter className="size-4" />}
          untertitel={
            <>
              Tagesschlusskurse von {d.mit_daten} von {d.anzahl} Aktien und ETFs ({d.listen.map((l) => l.name).join(", ")}) – nur zur Orientierung. Gebucht wird zu protokollierten Kursen (tools/kurse.py), nie zu
              diesen Werten.
            </>
          }
          aktion={
            <span className="inline-flex shrink-0 items-center gap-1.5 text-[12.5px] text-text-3">
              <Clock className="size-3.5" /> Stand {relativ(d.zeit)} · {d.quelle}
            </span>
          }
        />
        <div className="flex flex-wrap items-center gap-2 px-5 pb-4">
          <div className="inline-flex rounded-lg border border-rand bg-flaeche-2 p-0.5" role="group" aria-label="Ansicht">
            {(["kandidaten", "tabelle"] as const).map((a) => (
              <button
                key={a}
                type="button"
                aria-pressed={ansicht === a}
                onClick={() => setAnsicht(a)}
                className={cn("rounded-md px-3 py-1.5 text-[13px] font-medium", ansicht === a ? "bg-flaeche-3 text-text" : "text-text-3 hover:text-text")}
              >
                {a === "kandidaten" ? "Kandidaten" : "Alle Werte"}
              </button>
            ))}
          </div>
          <select
            aria-label="Liste"
            value={liste}
            onChange={(e) => {
              setListe(e.target.value);
              setSeite(0);
            }}
            className={FELD_KLASSE}
          >
            <option value="">Alle Listen</option>
            {d.listen.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name} ({l.mit_daten})
              </option>
            ))}
          </select>
          {ansicht === "tabelle" && (
            <>
              <label className="relative">
                <span className="sr-only">Suchen nach Kürzel oder Name</span>
                <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-text-3" aria-hidden />
                <input type="search" value={eingabe} onChange={(e) => setEingabe(e.target.value)} placeholder="Kürzel oder Name" className={cn(FELD_KLASSE, "w-48 pl-8")} />
              </label>
              <select aria-label="Sortieren nach" value={sortiert} onChange={(e) => sortierenNach(e.target.value as BeobachtungKennzahl)} className={FELD_KLASSE}>
                {sortierbar.map((k) => (
                  <option key={k.id} value={k.id}>
                    Sortiert nach: {k.titel}
                  </option>
                ))}
              </select>
              <Knopf klein onClick={() => { setAufsteigend(!aufsteigend); setSeite(0); }} aria-label={aufsteigend ? "Aufsteigend sortiert, umkehren" : "Absteigend sortiert, umkehren"}>
                {aufsteigend ? <ArrowUp className="size-3.5" /> : <ArrowDown className="size-3.5" />}
                {aufsteigend ? "Aufsteigend" : "Absteigend"}
              </Knopf>
            </>
          )}
          <label className="inline-flex items-center gap-2 text-[13px] text-text-2">
            <input
              type="checkbox"
              checked={nurHandelbar}
              onChange={(e) => {
                setNurHandelbar(e.target.checked);
                setSeite(0);
              }}
              className="size-4 accent-[var(--akzent)]"
            />
            Nur handelbare Werte
          </label>
        </div>
      </Karte>

      {ansicht === "kandidaten" ? (
        <Kandidatenbloecke liste={liste} kennzahlen={d.kennzahlen} />
      ) : (
        <Karte className="overflow-hidden">
          {!d.eintraege.length ? (
            <Leer titel="Keine Treffer" text="Suche, Liste oder den Filter „Nur handelbare Werte“ anpassen." />
          ) : (
            <div className="overflow-x-auto">
              <table className="zahl w-full min-w-[820px]">
                <thead>
                  <tr className="text-left text-[11.5px] font-medium tracking-wide text-text-3 uppercase">
                    <th scope="col" className="px-4 py-2.5 font-medium">
                      Wert
                    </th>
                    <th scope="col" className="px-3 py-2.5 text-right font-medium">
                      Kurs
                    </th>
                    {spalten.map((id) => (
                      <th key={id} scope="col" className="px-3 py-2.5 text-right font-medium" aria-sort={id === sortiert ? (aufsteigend ? "ascending" : "descending") : "none"}>
                        <button type="button" onClick={() => sortierenNach(id)} className={cn("inline-flex items-center gap-1 uppercase hover:text-text", id === sortiert && "text-text")}>
                          {titel(id)}
                          {id === sortiert && (aufsteigend ? <ArrowUp className="size-3" aria-hidden /> : <ArrowDown className="size-3" aria-hidden />)}
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {d.eintraege.map((e) => (
                    <tr key={e.ticker} className="border-t border-rand hover:bg-flaeche-2">
                      <td className="px-4 py-2.5">
                        <Wertname e={e} />
                      </td>
                      <td className="px-3 py-2.5 text-right text-[13.5px] font-semibold whitespace-nowrap text-text">
                        {zahl(e.kurs)} <span className="text-[11.5px] font-normal text-text-3">{e.waehrung}</span>
                      </td>
                      {spalten.map((id) => (
                        <td key={id} className="px-3 py-2.5 text-right text-[13px] whitespace-nowrap text-text-2">
                          <KennzahlWert id={id} art={art(id)} e={e} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-rand px-4 py-2.5 text-[12.5px] text-text-3">
            <span>
              {d.gesamt} {d.gesamt === 1 ? "Wert" : "Werte"} · Seite {seite + 1} von {seiten}
            </span>
            <span className="inline-flex gap-1.5">
              <Knopf klein aria-label="Vorherige Seite" disabled={seite === 0} onClick={() => setSeite(seite - 1)}>
                <ChevronLeft className="size-3.5" />
              </Knopf>
              <Knopf klein aria-label="Nächste Seite" disabled={seite + 1 >= seiten} onClick={() => setSeite(seite + 1)}>
                <ChevronRight className="size-3.5" />
              </Knopf>
            </span>
          </div>
        </Karte>
      )}
      {d.ohne_daten.length > 0 && (
        <p className="text-[12px] text-text-3">
          Ohne Kursdaten ({d.ohne_daten.length}): {d.ohne_daten.slice(0, 12).join(", ")}
          {d.ohne_daten.length > 12 ? " …" : ""}. Kürzel prüfen (Indexwechsel, Umbenennung) – Pflege in config/beobachtung.json.
        </p>
      )}
    </div>
  );
}
