import { cn } from "@/lib/cn";

export interface Szenario {
  name: "Bull" | "Base" | "Bear";
  prozent: number;
  text: string;
}

/** Liest "Bull 30 % (…) / Base 50 % (…) / Bear 20 % (…)" aus dem Journal-Feld. */
export function szenarienLesen(text: string | undefined): Szenario[] {
  if (!text) return [];
  const ergebnis: Szenario[] = [];
  for (const name of ["Bull", "Base", "Bear"] as const) {
    const treffer = new RegExp(`${name}\\s*(\\d{1,3})\\s*%\\s*(?:\\(([^)]*)\\))?`, "i").exec(text);
    if (treffer) ergebnis.push({ name, prozent: Number(treffer[1]), text: treffer[2] ?? "" });
  }
  return ergebnis;
}

const STIL: Record<Szenario["name"], string> = {
  Bull: "bg-gut",
  Base: "bg-[var(--benchmark)]",
  Bear: "bg-schlecht",
};

/** Szenario-Balken: Anteile mit 2-px-Lücken, beschriftet (nie nur Farbe). */
export function SzenarioBalken({ szenarien }: { szenarien: Szenario[] }) {
  if (!szenarien.length) return null;
  const summe = szenarien.reduce((s, x) => s + x.prozent, 0) || 1;
  return (
    <div>
      <div className="flex h-3 gap-[2px] overflow-hidden rounded-full" role="img" aria-label={szenarien.map((s) => `${s.name} ${s.prozent} %`).join(", ")}>
        {szenarien.map((s) => (
          <div key={s.name} className={cn("h-full first:rounded-l-full last:rounded-r-full", STIL[s.name])} style={{ width: `${(s.prozent / summe) * 100}%` }} />
        ))}
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        {szenarien.map((s) => (
          <div key={s.name} className="rounded-xl border border-rand bg-flaeche-2 px-3 py-2.5">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-[12.5px] font-medium text-text-2">
                <span className={cn("size-2 rounded-full", STIL[s.name])} />
                {s.name}
              </span>
              <span className="zahl text-[15px] font-semibold text-text">{s.prozent} %</span>
            </div>
            {s.text && <p className="mt-1 text-[12.5px] leading-snug text-text-3">{s.text}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}
