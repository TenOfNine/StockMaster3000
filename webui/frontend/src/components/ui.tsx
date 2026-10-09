import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Inbox, Loader2, Minus, X } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";

import type { Profil } from "@/lib/api";
import { cn } from "@/lib/cn";
import { prozent } from "@/lib/format";

// --------------------------------------------------------------------------
// Schaltflächen und Eingaben

type Variante = "primaer" | "sekundaer" | "geist" | "gefahr";

export const Knopf = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante; laedt?: boolean; klein?: boolean }>(
  ({ variante = "sekundaer", laedt, klein, className, children, disabled, ...rest }, ref) => (
    <button
      ref={ref}
      disabled={disabled || laedt}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all duration-150 select-none",
        "disabled:cursor-not-allowed disabled:opacity-50 active:scale-[0.98]",
        klein ? "h-8 px-3 text-[13px]" : "h-10 px-4 text-sm",
        variante === "primaer" && "bg-text text-bg hover:opacity-90 shadow-sm",
        variante === "sekundaer" && "border border-rand bg-flaeche-2 text-text hover:border-rand-stark hover:bg-flaeche-3",
        variante === "geist" && "text-text-2 hover:bg-flaeche-3 hover:text-text",
        variante === "gefahr" && "bg-schlecht text-white hover:opacity-90",
        className,
      )}
      {...rest}
    >
      {laedt && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  ),
);
Knopf.displayName = "Knopf";

export const Eingabe = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(({ className, ...rest }, ref) => (
  <input
    ref={ref}
    className={cn(
      "h-10 w-full rounded-lg border border-rand bg-flaeche-2 px-3 text-sm text-text placeholder:text-text-3",
      "transition-colors hover:border-rand-stark focus:border-akzent focus:outline-none focus:ring-2 focus:ring-akzent/25",
      className,
    )}
    {...rest}
  />
));
Eingabe.displayName = "Eingabe";

export function Feld({ label, hinweis, fehler, children, id }: { label: string; hinweis?: string; fehler?: string; children: ReactNode; id: string }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-[13px] font-medium text-text-2">
        {label}
      </label>
      {children}
      {fehler ? (
        <p className="text-[12.5px] text-schlecht" role="alert">
          {fehler}
        </p>
      ) : hinweis ? (
        <p className="text-[12.5px] text-text-3">{hinweis}</p>
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------
// Karten, Kopfzeilen, Abschnitte

export function Karte({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-2xl border border-rand bg-flaeche shadow-karte", className)} {...rest}>
      {children}
    </div>
  );
}

export function KarteKopf({ titel, untertitel, aktion, icon }: { titel: ReactNode; untertitel?: ReactNode; aktion?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 px-5 pt-4 pb-3">
      <div className="min-w-0">
        <h3 className="flex items-center gap-2 text-[14px] font-semibold tracking-[-0.005em] text-text">
          {icon && <span className="text-text-3">{icon}</span>}
          {titel}
        </h3>
        {untertitel && <p className="mt-0.5 text-[12.5px] text-text-3">{untertitel}</p>}
      </div>
      {aktion}
    </div>
  );
}

export function Seitenkopf({ titel, untertitel, aktionen, vorne }: { titel: ReactNode; untertitel?: ReactNode; aktionen?: ReactNode; vorne?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {vorne}
        <h1 className="text-[26px] font-semibold tracking-[-0.02em] text-text">{titel}</h1>
        {untertitel && <p className="mt-1 max-w-3xl text-sm text-text-2">{untertitel}</p>}
      </div>
      {aktionen && <div className="flex shrink-0 flex-wrap items-center gap-2">{aktionen}</div>}
    </header>
  );
}

// --------------------------------------------------------------------------
// Abzeichen, Profile, Deltas

type Ton = "neutral" | "gut" | "schlecht" | "warnung" | "akzent";

export function Abzeichen({ ton = "neutral", children, className, icon }: { ton?: Ton; children: ReactNode; className?: string; icon?: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-medium whitespace-nowrap",
        ton === "neutral" && "bg-flaeche-3 text-text-2",
        ton === "gut" && "bg-gut-flaeche text-gut",
        ton === "schlecht" && "bg-schlecht-flaeche text-schlecht",
        ton === "warnung" && "bg-warnung-flaeche text-warnung",
        ton === "akzent" && "bg-akzent/15 text-akzent",
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

export const PROFIL_NAME: Record<Profil, string> = { defensiv: "Defensiv", ausgewogen: "Ausgewogen", aggressiv: "Aggressiv", overnight: "Overnight" };
export const PROFIL_FARBE: Record<Profil, string> = {
  defensiv: "var(--defensiv)",
  ausgewogen: "var(--ausgewogen)",
  aggressiv: "var(--aggressiv)",
  overnight: "var(--overnight)",
};

export function ProfilMarke({ profil, className, nurPunkt }: { profil: Profil; className?: string; nurPunkt?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[13px] font-medium text-text", className)}>
      <span className="size-2 shrink-0 rounded-full ring-2 ring-[var(--flaeche)]" style={{ background: PROFIL_FARBE[profil] }} aria-hidden />
      {!nurPunkt && PROFIL_NAME[profil]}
    </span>
  );
}

/** Gewinn/Verlust: nie nur über Farbe – immer mit Vorzeichen und Symbol. */
export function Delta({ wert, className, gross, text }: { wert: number | null | undefined; className?: string; gross?: boolean; text?: string }) {
  if (wert == null) return <span className={cn("text-text-3", className)}>–</span>;
  const ton = wert > 0 ? "gut" : wert < 0 ? "schlecht" : "neutral";
  const Icon = wert > 0 ? ArrowUpRight : wert < 0 ? ArrowDownRight : Minus;
  return (
    <span
      className={cn(
        "zahl inline-flex items-center gap-0.5 font-medium",
        ton === "gut" && "text-gut",
        ton === "schlecht" && "text-schlecht",
        ton === "neutral" && "text-text-2",
        gross ? "text-[15px]" : "text-[13px]",
        className,
      )}
    >
      <Icon className={gross ? "size-4" : "size-3.5"} aria-hidden />
      {text ?? prozent(wert, true)}
    </span>
  );
}

export function StufenAbzeichen({ stufe }: { stufe: number }) {
  if (stufe >= 2) return <Abzeichen ton="schlecht" icon={<AlertTriangle className="size-3" />}>Drawdown-Stufe 2</Abzeichen>;
  if (stufe === 1) return <Abzeichen ton="warnung" icon={<AlertTriangle className="size-3" />}>Drawdown-Stufe 1</Abzeichen>;
  return <Abzeichen>Stufe 0</Abzeichen>;
}

// --------------------------------------------------------------------------
// Kennzahl

export function Kennzahl({ label, wert, zusatz, hilfe, className }: { label: string; wert: ReactNode; zusatz?: ReactNode; hilfe?: string; className?: string }) {
  const inhalt = (
    <div className={cn("min-w-0", className)}>
      <div className="text-[12px] font-medium tracking-wide text-text-3">{label}</div>
      <div className="zahl mt-1 truncate text-[19px] font-semibold tracking-[-0.01em] text-text">{wert}</div>
      {zusatz && <div className="mt-0.5 text-[12.5px] text-text-3">{zusatz}</div>}
    </div>
  );
  return hilfe ? <Hinweis text={hilfe}>{inhalt}</Hinweis> : inhalt;
}

// --------------------------------------------------------------------------
// Auslastungsbalken für Limits

export function Auslastungsbalken({ ist, grenze, art, einheit, label }: { ist: number; grenze: number; art: "max" | "min"; einheit: "%" | "x"; label: string }) {
  const fmt = (w: number) => (einheit === "x" ? `${w.toFixed(2).replace(".", ",")}x` : prozent(w, false, 1));
  let anteil: number;
  let ton: Ton;
  if (art === "max") {
    anteil = grenze > 0 ? ist / grenze : 0;
    ton = anteil >= 1 ? "schlecht" : anteil >= 0.8 ? "warnung" : "gut";
  } else {
    // Mindestwert: voll ausgefüllt, solange weit über der Grenze
    anteil = grenze > 0 ? Math.min(1, grenze / Math.max(ist, 1e-9)) : 0;
    ton = ist < grenze ? "schlecht" : anteil >= 0.8 ? "warnung" : "gut";
  }
  const breite = `${Math.min(100, Math.max(2, anteil * 100))}%`;
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-medium text-text">{label}</span>
        <span className="zahl text-[12.5px] text-text-2">
          <span className="font-semibold text-text">{fmt(ist)}</span>
          <span className="text-text-3"> {art === "max" ? "von max." : "min."} {fmt(grenze)}</span>
        </span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full bg-flaeche-3"
        role="meter"
        aria-label={label}
        aria-valuenow={Math.round(anteil * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500",
            ton === "gut" && "bg-gut",
            ton === "warnung" && "bg-warnung",
            ton === "schlecht" && "bg-schlecht",
          )}
          style={{ width: breite }}
        />
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Zustände

export function Skelett({ className }: { className?: string }) {
  return <div className={cn("skelett rounded-lg", className)} aria-hidden />;
}

export function Leer({ titel, text, icon, aktion }: { titel: string; text?: ReactNode; icon?: ReactNode; aktion?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="mb-3 grid size-11 place-items-center rounded-xl border border-rand bg-flaeche-2 text-text-3">{icon ?? <Inbox className="size-5" />}</div>
      <p className="text-sm font-medium text-text">{titel}</p>
      {text && <p className="mt-1 max-w-md text-[13px] text-text-3">{text}</p>}
      {aktion && <div className="mt-4">{aktion}</div>}
    </div>
  );
}

export function Fehleranzeige({ fehler, erneut }: { fehler: unknown; erneut?: () => void }) {
  const text = fehler instanceof Error ? fehler.message : "Unbekannter Fehler";
  return (
    <Karte className="border-schlecht/30">
      <Leer
        titel="Daten konnten nicht geladen werden"
        text={text}
        icon={<AlertTriangle className="size-5 text-schlecht" />}
        aktion={erneut && <Knopf onClick={erneut} klein>Erneut versuchen</Knopf>}
      />
    </Karte>
  );
}

// --------------------------------------------------------------------------
// Tabs, Tooltip, Dialog, Tastenkürzel

export const Reiter = TabsPrimitive.Root;

export function ReiterLeiste({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <TabsPrimitive.List className={cn("flex gap-1 overflow-x-auto border-b border-rand", className)} aria-label="Bereiche">
      {children}
    </TabsPrimitive.List>
  );
}

export function ReiterKnopf({ value, children }: { value: string; children: ReactNode }) {
  return (
    <TabsPrimitive.Trigger
      value={value}
      className={cn(
        "relative -mb-px flex items-center gap-1.5 border-b-2 border-transparent px-3 py-2.5 text-[13.5px] font-medium whitespace-nowrap text-text-3 transition-colors",
        "hover:text-text data-[state=active]:border-text data-[state=active]:text-text",
      )}
    >
      {children}
    </TabsPrimitive.Trigger>
  );
}

export const ReiterInhalt = forwardRef<HTMLDivElement, TabsPrimitive.TabsContentProps>(({ className, ...rest }, ref) => (
  <TabsPrimitive.Content ref={ref} className={cn("einblenden pt-5 focus:outline-none", className)} {...rest} />
));
ReiterInhalt.displayName = "ReiterInhalt";

export function Hinweis({ text, children }: { text: ReactNode; children: ReactNode }) {
  return (
    <TooltipPrimitive.Root delayDuration={250}>
      <TooltipPrimitive.Trigger asChild>
        <span className="inline-block cursor-help">{children}</span>
      </TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          sideOffset={6}
          className="z-50 max-w-xs rounded-lg border border-rand bg-flaeche-3 px-3 py-2 text-[12.5px] leading-snug text-text shadow-karte"
        >
          {text}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

export function Dialog({ offen, setOffen, titel, beschreibung, children, breit }: { offen: boolean; setOffen: (o: boolean) => void; titel: string; beschreibung?: string; children: ReactNode; breit?: boolean }) {
  return (
    <DialogPrimitive.Root open={offen} onOpenChange={setOffen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px] data-[state=open]:animate-[einblenden_0.2s]" />
        <DialogPrimitive.Content
          className={cn(
            "fixed top-1/2 left-1/2 z-50 max-h-[88vh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-rand bg-flaeche p-6 shadow-2xl",
            breit ? "max-w-2xl" : "max-w-md",
          )}
        >
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <DialogPrimitive.Title className="text-[16px] font-semibold text-text">{titel}</DialogPrimitive.Title>
              {beschreibung ? (
                <DialogPrimitive.Description className="mt-1 text-[13px] text-text-3">{beschreibung}</DialogPrimitive.Description>
              ) : (
                <DialogPrimitive.Description className="sr-only">{titel}</DialogPrimitive.Description>
              )}
            </div>
            <DialogPrimitive.Close className="rounded-md p-1 text-text-3 hover:bg-flaeche-3 hover:text-text" aria-label="Schließen">
              <X className="size-4" />
            </DialogPrimitive.Close>
          </div>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export function Taste({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-rand bg-flaeche-2 px-1.5 py-0.5 font-mono text-[10.5px] text-text-3">{children}</kbd>;
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("font-mono text-[12.5px]", className)}>{children}</span>;
}
