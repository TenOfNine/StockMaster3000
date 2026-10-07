import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { AlertTriangle, Check, ShieldAlert, ShieldQuestion, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api, type Freigabe, type FreigabeStatus, type Lauf } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { zeit } from "@/lib/format";

import { Abzeichen, Knopf, Mono } from "./ui";

// Befehle müssen Zeichen für Zeichen lesbar sein: Ohne das setzt die Schrift z. B. "<=" und "==" zu Ligaturen zusammen.
export const OHNE_LIGATUREN = "[font-variant-ligatures:none] [font-feature-settings:'liga'_0,'calt'_0]";

const STATUS: Record<FreigabeStatus, { text: string; ton: "gut" | "schlecht" | "warnung" | "neutral" }> = {
  offen: { text: "wartet auf Entscheidung", ton: "warnung" },
  erlaubt: { text: "erlaubt", ton: "gut" },
  abgelehnt: { text: "abgelehnt", ton: "schlecht" },
  abgelaufen: { text: "abgelaufen, automatisch abgelehnt", ton: "warnung" },
  gesperrt: { text: "nie freigebbar, automatisch abgelehnt", ton: "schlecht" },
  abgebrochen: { text: "Lauf beendet", ton: "neutral" },
};

export function hinweisText(anzahl: number): string {
  return anzahl === 1 ? "1 Freigabe offen" : `${anzahl} Freigaben offen`;
}

/** Verbleibende Zeit bis zur automatischen Ablehnung, tickt sekündlich ab dem Stand der letzten Abfrage. */
export function Restzeit({ sekunden, seit }: { sekunden: number; seit: number }) {
  const [jetzt, setJetzt] = useState(() => Date.now());
  useEffect(() => {
    const takt = setInterval(() => setJetzt(Date.now()), 1000);
    return () => clearInterval(takt);
  }, []);
  const rest = Math.max(0, sekunden - Math.floor((jetzt - seit) / 1000));
  return <span className="zahl font-medium">{`${Math.floor(rest / 60)}:${String(rest % 60).padStart(2, "0")}`}</span>;
}

function fehlerText(fehler: unknown): string {
  return fehler instanceof Error ? fehler.message : "Unbekannter Fehler";
}

/** Freigaben eines Laufs: offene Anfragen mit Befehl und Knöpfen, darunter der Verlauf. */
export function FreigabePanel({ lauf, admin }: { lauf: Lauf; admin: boolean }) {
  const client = useQueryClient();
  const aktiv = lauf.status === "laeuft" || lauf.status === "wartet";
  const liste = useQuery({
    queryKey: ["freigaben", lauf.id],
    queryFn: async () => {
      const antwort = await api<Freigabe[]>(`/api/freigaben?lauf=${encodeURIComponent(lauf.id)}`);
      return Array.isArray(antwort) ? antwort : [];
    },
    refetchInterval: aktiv ? 2000 : false,
  });
  const entscheiden = useMutation({
    mutationFn: ({ id, entscheidung }: { id: string; entscheidung: "erlauben" | "ablehnen" }) => api<Freigabe>(`/api/freigaben/${id}/entscheidung`, { daten: { entscheidung } }),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ["freigaben"] });
      void client.invalidateQueries({ queryKey: ["freigaben-offen"] });
    },
  });
  if (!liste.data?.length) return null;
  const offen = liste.data.filter((f) => f.entscheidbar);
  const verlauf = liste.data.filter((f) => !f.entscheidbar);
  return (
    <section aria-label="Freigaben" className="space-y-3">
      {offen.map((f) => (
        <div key={f.id} role="alert" className="rounded-xl border border-warnung/40 bg-warnung-flaeche p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-[13.5px] font-semibold text-text">
              <ShieldQuestion className="size-4 text-warnung" aria-hidden /> Freigabe angefragt: {f.werkzeug}
            </div>
            <div className="text-[12.5px] text-text-2">
              Noch <Restzeit sekunden={f.sekunden_rest} seit={liste.dataUpdatedAt} /> Min., dann automatisch abgelehnt
            </div>
          </div>
          <pre className={cn("mt-3 max-h-48 overflow-auto rounded-lg border border-rand bg-flaeche p-3 font-mono text-[12.5px] leading-relaxed break-all whitespace-pre-wrap text-text", OHNE_LIGATUREN)}>{f.befehl}</pre>
          {f.beschreibung && <p className="mt-2 text-[12px] text-text-3">Beschreibung von Claude (ungeprüft): {f.beschreibung}</p>}
          {admin ? (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Knopf variante="primaer" klein onClick={() => entscheiden.mutate({ id: f.id, entscheidung: "erlauben" })} disabled={entscheiden.isPending}>
                <Check className="size-4" /> Erlauben
              </Knopf>
              <Knopf klein onClick={() => entscheiden.mutate({ id: f.id, entscheidung: "ablehnen" })} disabled={entscheiden.isPending}>
                <X className="size-4" /> Ablehnen
              </Knopf>
              <span className="text-[12px] text-text-3">Gilt nur für diesen einen Aufruf. Schreiben in den Spielstand ist nie freigebbar.</span>
            </div>
          ) : (
            <p className="mt-3 text-[12.5px] text-text-2">Ein Administrator entscheidet in der Web-UI.</p>
          )}
          {entscheiden.isError && (
            <p role="alert" className="mt-2 flex items-start gap-1.5 text-[12.5px] text-schlecht">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> {fehlerText(entscheiden.error)}
            </p>
          )}
        </div>
      ))}
      {verlauf.length > 0 && (
        <details className="rounded-xl border border-rand bg-flaeche-2/60 px-4 py-3" open={offen.length === 0}>
          <summary className="cursor-pointer text-[12px] font-semibold tracking-wide text-text-3 uppercase">Freigaben dieses Laufs ({verlauf.length})</summary>
          <ul className="mt-3 divide-y divide-rand">
            {verlauf.map((f) => (
              <li key={f.id} className="py-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Mono className={cn("min-w-0 flex-1 text-[12px] break-all text-text", OHNE_LIGATUREN)}>{f.befehl}</Mono>
                  <Abzeichen ton={STATUS[f.status]?.ton ?? "neutral"} icon={f.status === "gesperrt" ? <ShieldAlert className="size-3" /> : undefined}>
                    {STATUS[f.status]?.text ?? f.status}
                  </Abzeichen>
                </div>
                <div className="mt-0.5 text-[11.5px] text-text-3">
                  {zeit(f.erstellt)}
                  {f.grund ? ` · ${f.grund}` : ""}
                </div>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

/** Kopfzeile: Administratoren sehen sofort, wenn irgendwo ein Lauf auf eine Freigabe wartet. */
export function FreigabeHinweis() {
  const { sitzung } = useAuth();
  const admin = !!sitzung?.benutzer?.ist_admin;
  const offen = useQuery({
    queryKey: ["freigaben-offen"],
    queryFn: async () => {
      const antwort = await api<Freigabe[]>("/api/freigaben?offen=true");
      return Array.isArray(antwort) ? antwort : [];
    },
    enabled: admin,
    refetchInterval: 10_000,
  });
  const anzahl = offen.data?.length ?? 0;
  if (!admin || !anzahl) return null;
  return (
    <Link to="/laeufe" className="inline-flex items-center gap-1.5 rounded-full bg-warnung-flaeche px-2.5 py-1 text-[12px] font-medium text-warnung hover:underline">
      <ShieldQuestion className="size-3.5" aria-hidden /> {hinweisText(anzahl)}
    </Link>
  );
}
