import { Link } from "@tanstack/react-router";
import { CalendarClock, CircleDot, CircleSlash, Clock3, LockOpen, Pencil, ShoppingCart, XCircle } from "lucide-react";

import type { JournalEintrag, Termin } from "@/lib/api";
import { cn } from "@/lib/cn";
import { datum, euro, zeit } from "@/lib/format";

import { Abzeichen, PROFIL_FARBE } from "./ui";

export function StatusAbzeichen({ status }: { status?: string }) {
  switch (status) {
    case "offen":
      return <Abzeichen ton="akzent" icon={<CircleDot className="size-3" />}>offen</Abzeichen>;
    case "geschlossen":
      return <Abzeichen icon={<LockOpen className="size-3" />}>geschlossen</Abzeichen>;
    case "vorgemerkt":
      return <Abzeichen ton="warnung" icon={<Clock3 className="size-3" />}>vorgemerkt</Abzeichen>;
    case "verkauf":
      return <Abzeichen icon={<ShoppingCart className="size-3" />}>Verkauf</Abzeichen>;
    case "verfallen":
      return <Abzeichen ton="schlecht" icon={<XCircle className="size-3" />}>verfallen</Abzeichen>;
    case "storniert":
      return <Abzeichen icon={<XCircle className="size-3" />}>storniert</Abzeichen>;
    case "änderung":
      return <Abzeichen icon={<Pencil className="size-3" />}>Änderung</Abzeichen>;
    default:
      return <Abzeichen icon={<CircleSlash className="size-3" />}>nicht ausgeführt</Abzeichen>;
  }
}

export function Ergebnis({ wert, className }: { wert: number | null | undefined; className?: string }) {
  if (wert == null) return <span className={cn("text-text-3", className)}>–</span>;
  return (
    <span className={cn("zahl font-medium", wert > 0 ? "text-gut" : wert < 0 ? "text-schlecht" : "text-text-2", className)}>
      {wert > 0 ? "+" : wert < 0 ? "−" : "±"}
      {euro(Math.abs(wert)).replace("-", "")}
    </span>
  );
}

/** Eine Zeile je Journal-Eintrag (Order-Begründung). */
export function EntscheidungsZeile({ e }: { e: JournalEintrag }) {
  return (
    <Link
      to="/entscheidungen/$id"
      params={{ id: e.id }}
      className="group grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1 rounded-xl px-3 py-2.5 transition-colors hover:bg-flaeche-2 sm:grid-cols-[auto_150px_minmax(0,1fr)_140px_104px]"
    >
      <span className="size-2.5 rounded-full" style={{ background: e.portfolio ? PROFIL_FARBE[e.portfolio] : "var(--text-3)" }} aria-label={e.portfolio ?? ""} />
      <div className="min-w-0">
        <div className="truncate text-[13.5px] font-medium text-text">{e.instrument}</div>
        <div className="font-mono text-[11.5px] text-text-3">{e.id}</div>
      </div>
      <p className="col-span-3 col-start-2 line-clamp-1 text-[13px] text-text-2 sm:col-span-1 sm:col-start-auto">{e.felder.these ?? e.felder.aktion}</p>
      <span className="justify-self-end sm:justify-self-start"><StatusAbzeichen status={e.status} /></span>
      <span className="hidden text-right sm:block">
        <Ergebnis wert={e.ergebnis_eur} className="text-[13px]" />
        {e.ergebnis_art === "unrealisiert" && <span className="block text-[10.5px] text-text-3">unrealisiert</span>}
      </span>
    </Link>
  );
}

const TERMIN_TEXT: Record<Termin["art"], string> = { woche: "Wochenreview", monat: "Monatsvergleich", quartal: "Quartals-Meta-Review", stufe2: "Pflicht-Review" };

export function TerminZeile({ t }: { t: Termin }) {
  return (
    <div className="flex items-start gap-3 rounded-xl px-3 py-2.5">
      <span className={cn("mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg", t.art === "stufe2" ? "bg-schlecht-flaeche text-schlecht" : "bg-warnung-flaeche text-warnung")}>
        <CalendarClock className="size-4" />
      </span>
      <div className="min-w-0">
        <div className="text-[13.5px] font-medium text-text">
          {TERMIN_TEXT[t.art]} <span className="text-text-3">{t.zeitraum}</span>
        </div>
        <div className="truncate font-mono text-[11.5px] text-text-3">{t.datei}</div>
      </div>
    </div>
  );
}

export function SessionKarte({ s }: { s: JournalEintrag }) {
  const profile = ["defensiv", "ausgewogen", "aggressiv"] as const;
  return (
    <Link to="/sessions" hash={s.id} className="block rounded-xl border border-rand bg-flaeche-2 p-3 transition-colors hover:border-rand-stark">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[11.5px] text-text-3">{s.id}</span>
        <span className="text-[12px] text-text-3">{zeit(s.zeit)}</span>
      </div>
      <ul className="mt-2 space-y-1">
        {profile.map((p) =>
          s.felder[p] ? (
            <li key={p} className="flex gap-2 text-[12.5px] text-text-2">
              <span className="mt-[7px] size-1.5 shrink-0 rounded-full" style={{ background: PROFIL_FARBE[p] }} />
              <span className="line-clamp-1">{s.felder[p]}</span>
            </li>
          ) : null,
        )}
      </ul>
    </Link>
  );
}

export function DatumsTrenner({ wert }: { wert: string }) {
  return <div className="sticky top-14 z-10 -mx-1 bg-bg/90 px-1 py-2 text-[12px] font-semibold tracking-wide text-text-3 backdrop-blur">{datum(wert)}</div>;
}
