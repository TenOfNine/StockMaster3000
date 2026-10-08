import { useQuery } from "@tanstack/react-query";
import { ScrollText } from "lucide-react";

import { Abzeichen, Karte, KarteKopf } from "@/components/ui";
import { api, type Profil, type VorgabenLesen } from "@/lib/api";
import { datum } from "@/lib/format";

/** Vorgaben der Auftraggeber für ein Portfolio, nur lesen (ändern dürfen nur Administratoren in der Einrichtung). */
export function VorgabenKarte({ profil }: { profil: Profil }) {
  const vorgaben = useQuery({ queryKey: ["vorgaben-lesen"], queryFn: () => api<VorgabenLesen>("/api/spiel/vorgaben") });
  const v = vorgaben.data?.profile[profil];
  if (!v?.text) return null;
  return (
    <Karte className="mb-4">
      <KarteKopf
        titel="Vorgaben der Auftraggeber"
        icon={<ScrollText className="size-4" />}
        untertitel="Ergänzen die Anlagerichtlinie, gelten ab dem nächsten Lauf und sind nachrangig gegenüber Regeln, Limits und Prüfungen."
        aktion={<Abzeichen>Version {v.version} · {datum(v.zeit)}</Abzeichen>}
      />
      <p className="px-5 pb-5 text-[13.5px] leading-relaxed whitespace-pre-wrap text-text-2">{v.text}</p>
    </Karte>
  );
}
