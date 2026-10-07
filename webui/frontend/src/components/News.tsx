import { ExternalLink, Newspaper } from "lucide-react";

import type { NewsMeldung } from "@/lib/api";
import { relativ, zeit } from "@/lib/format";

import { Abzeichen, Leer } from "./ui";

/** News aus dem Speicher (tools/news.py): nur Titel, Kurztext und Link, mit Quelle und Datum. */
export function NewsListe({ meldungen, kompakt, leerText }: { meldungen: NewsMeldung[]; kompakt?: boolean; leerText?: string }) {
  if (!meldungen.length) return <Leer icon={<Newspaper className="size-5" />} titel="Keine Meldungen" text={leerText ?? "Der Hintergrunddienst ruft die Feeds regelmäßig ab (Einrichtung → News)."} />;
  return (
    <ul className="divide-y divide-rand">
      {meldungen.map((m) => (
        <li key={m.id} className="px-3 py-2.5">
          <a href={m.link} target="_blank" rel="noreferrer noopener" className="group block">
            <div className="flex items-start gap-2">
              <span className="flex-1 text-[13px] leading-snug font-medium text-text group-hover:underline">{m.titel}</span>
              <ExternalLink className="mt-0.5 size-3.5 shrink-0 text-text-3" aria-hidden />
            </div>
            {!kompakt && m.kurztext && <p className="mt-0.5 line-clamp-2 text-[12.5px] text-text-3">{m.kurztext}</p>}
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11.5px] text-text-3">
              <span title={zeit(m.zeit ?? m.abgerufen)}>{relativ(m.zeit ?? m.abgerufen)}</span>
              <span>·</span>
              <span title={m.herausgeber_url ?? undefined}>{m.herausgeber ?? m.quelle_name}</span>
              {m.ticker.slice(0, 3).map((t) => (
                <Abzeichen key={t} className="font-mono">
                  {t}
                </Abzeichen>
              ))}
            </div>
          </a>
        </li>
      ))}
    </ul>
  );
}
