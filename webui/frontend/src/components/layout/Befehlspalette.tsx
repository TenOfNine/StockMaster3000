import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Command } from "cmdk";
import { ArrowRight, FileText, NotebookPen } from "lucide-react";

import { api, PROFILE, type JournalEintrag } from "@/lib/api";
import { datum } from "@/lib/format";

import { PROFIL_FARBE, PROFIL_NAME } from "../ui";

const SEITEN: { zu: string; text: string; stichworte?: string }[] = [
  { zu: "/", text: "Cockpit", stichworte: "start übersicht dashboard" },
  ...PROFILE.map((p) => ({ zu: `/portfolios/${p}`, text: `Portfolio ${PROFIL_NAME[p]}`, stichworte: "positionen trades limits" })),
  { zu: "/entscheidungen", text: "Zeitachse & Trade-Akten", stichworte: "journal reasoning" },
  { zu: "/sessions", text: "Sessions & Abwägungen", stichworte: "nichtstun session-eintrag" },
  { zu: "/analyse/ranking", text: "Ranking & Benchmark", stichworte: "sharpe drawdown" },
  { zu: "/analyse/reviews", text: "Reviews & Lessons", stichworte: "wochenreview erkenntnisse" },
  { zu: "/analyse/kurse", text: "Markt & Kurse", stichworte: "chart historie" },
  { zu: "/analyse/rechner", text: "Zertifikatsrechner", stichworte: "knock-out faktor hebel" },
  { zu: "/regelwerk", text: "Regelwerk", stichworte: "regeln limits kosten universum" },
  { zu: "/einrichtung", text: "Einrichtung & Aufbau", stichworte: "status arbeitspakete auslegungsfragen" },
  { zu: "/pruefung", text: "Prüfung & Audit", stichworte: "pruefe git historie" },
  { zu: "/konto", text: "Konto & Sicherheit", stichworte: "passwort zwei-faktor" },
];

export function Befehlspalette({ offen, setOffen }: { offen: boolean; setOffen: (o: boolean) => void }) {
  const navigate = useNavigate();
  const journal = useQuery({ queryKey: ["journal"], queryFn: () => api<JournalEintrag[]>("/api/spiel/journal"), enabled: offen });
  const springen = (zu: string) => {
    setOffen(false);
    void navigate({ to: zu });
  };
  const eintraege = [...(journal.data ?? [])].reverse().slice(0, 200);
  return (
    <DialogPrimitive.Root open={offen} onOpenChange={setOffen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px]" />
        <DialogPrimitive.Content className="fixed top-[14vh] left-1/2 z-50 w-[calc(100vw-2rem)] max-w-[600px] -translate-x-1/2 overflow-hidden rounded-2xl border border-rand bg-flaeche shadow-2xl">
          <DialogPrimitive.Title className="sr-only">Befehlspalette</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">Seiten und Journal-Einträge suchen</DialogPrimitive.Description>
          <Command label="Befehlspalette" className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-text-3 [&_[cmdk-group-heading]]:uppercase">
            <Command.Input
              placeholder="Seite, Journal-ID, Instrument oder Stichwort …"
              className="h-13 w-full border-b border-rand bg-transparent px-4 text-[15px] text-text placeholder:text-text-3 focus:outline-none"
            />
            <Command.List className="max-h-[52vh] overflow-y-auto p-1.5">
              <Command.Empty className="px-4 py-8 text-center text-[13px] text-text-3">Nichts gefunden.</Command.Empty>
              <Command.Group heading="Seiten">
                {SEITEN.map((s) => (
                  <Zeile key={s.zu} wert={`${s.text} ${s.stichworte ?? ""}`} beiAuswahl={() => springen(s.zu)}>
                    <FileText className="size-4 text-text-3" />
                    <span className="flex-1">{s.text}</span>
                    <ArrowRight className="size-3.5 text-text-3" />
                  </Zeile>
                ))}
              </Command.Group>
              {eintraege.length > 0 && (
                <Command.Group heading="Journal">
                  {eintraege.map((e) => (
                    <Zeile
                      key={e.id}
                      wert={`${e.id} ${e.instrument ?? ""} ${e.portfolio ?? ""} ${e.felder.these ?? ""} ${e.art === "S" ? "session" : ""}`}
                      beiAuswahl={() => springen(e.art === "J" ? `/entscheidungen/${e.id}` : `/sessions#${e.id}`)}
                    >
                      {e.portfolio ? (
                        <span className="size-2 rounded-full" style={{ background: PROFIL_FARBE[e.portfolio] }} />
                      ) : (
                        <NotebookPen className="size-4 text-text-3" />
                      )}
                      <span className="font-mono text-[12px] text-text-3">{e.id}</span>
                      <span className="flex-1 truncate">{e.art === "S" ? "Session-Eintrag" : e.instrument}</span>
                      <span className="text-[12px] text-text-3">{datum(e.zeit)}</span>
                    </Zeile>
                  ))}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function Zeile({ wert, beiAuswahl, children }: { wert: string; beiAuswahl: () => void; children: React.ReactNode }) {
  return (
    <Command.Item
      value={wert}
      onSelect={beiAuswahl}
      className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-[13.5px] text-text-2 data-[selected=true]:bg-flaeche-3 data-[selected=true]:text-text"
    >
      {children}
    </Command.Item>
  );
}
