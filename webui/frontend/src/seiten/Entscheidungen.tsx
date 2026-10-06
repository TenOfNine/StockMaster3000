import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "@tanstack/react-router";
import { FileClock, Filter, NotebookPen } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { EntscheidungsZeile } from "@/components/Bausteine";
import { Markdown } from "@/components/Markdown";
import { Abzeichen, Eingabe, Fehleranzeige, Karte, Knopf, Leer, PROFIL_FARBE, PROFIL_NAME, Seitenkopf, Skelett } from "@/components/ui";
import { api, PROFILE, type JournalEintrag, type Profil } from "@/lib/api";
import { cn } from "@/lib/cn";
import { datum, zeit } from "@/lib/format";

export function useJournal() {
  return useQuery({ queryKey: ["journal"], queryFn: () => api<JournalEintrag[]>("/api/spiel/journal") });
}

const STATUS = [
  { wert: "alle", text: "Alle" },
  { wert: "offen", text: "Offen" },
  { wert: "geschlossen", text: "Geschlossen" },
  { wert: "vorgemerkt", text: "Vorgemerkt" },
  { wert: "verkauf", text: "Verkäufe" },
  { wert: "ohne ausführung", text: "Nicht ausgeführt" },
];

function Chip({ aktiv, onClick, children }: { aktiv: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={aktiv}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12.5px] font-medium transition-colors",
        aktiv ? "border-text bg-text text-bg" : "border-rand bg-flaeche text-text-2 hover:border-rand-stark hover:text-text",
      )}
    >
      {children}
    </button>
  );
}

export function Entscheidungen() {
  const journal = useJournal();
  const [profil, setProfil] = useState<"alle" | Profil>("alle");
  const [status, setStatus] = useState("alle");
  const [suche, setSuche] = useState("");
  const [sichtbar, setSichtbar] = useState(20);
  useEffect(() => setSichtbar(20), [profil, status, suche]);

  const gruppen = useMemo(() => {
    const s = suche.trim().toLowerCase();
    const gefiltert = (journal.data ?? []).filter(
      (e) =>
        e.art === "J" &&
        (profil === "alle" || e.portfolio === profil) &&
        (status === "alle" || e.status === status || (status === "ohne ausführung" && ["ohne ausführung", "verfallen", "storniert"].includes(e.status ?? ""))) &&
        (!s || `${e.id} ${e.instrument} ${Object.values(e.felder).join(" ")}`.toLowerCase().includes(s)),
    );
    const sessions = new Map((journal.data ?? []).filter((e) => e.art === "S").map((e) => [e.datei, e]));
    const nachDatei = new Map<string, JournalEintrag[]>();
    for (const e of gefiltert) nachDatei.set(e.datei, [...(nachDatei.get(e.datei) ?? []), e]);
    return [...nachDatei.entries()]
      .sort((a, b) => b[0].localeCompare(a[0]))
      .map(([datei, eintraege]) => ({ datei, datum: eintraege[0].datum, eintraege, session: sessions.get(datei) }));
  }, [journal.data, profil, status, suche]);

  const anzahl = gruppen.reduce((s, g) => s + g.eintraege.length, 0);

  return (
    <div className="einblenden">
      <Seitenkopf
        titel="Entscheidungen"
        untertitel="Jede Order beginnt mit einem Journal-Eintrag: These, Szenarien, Stop, Ziel, Risikorechnung und Quellen. Hier ist jede Entscheidung bis zur Ausführung verfolgbar."
      />
      <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-1.5">
          <Filter className="mr-1 size-4 text-text-3" aria-hidden />
          <Chip aktiv={profil === "alle"} onClick={() => setProfil("alle")}>Alle Portfolios</Chip>
          {PROFILE.map((p) => (
            <Chip key={p} aktiv={profil === p} onClick={() => setProfil(p)}>
              <span className="size-2 rounded-full" style={{ background: PROFIL_FARBE[p] }} />
              {PROFIL_NAME[p]}
            </Chip>
          ))}
          <span className="mx-1 hidden h-5 w-px bg-rand sm:block" />
          {STATUS.map((s) => (
            <Chip key={s.wert} aktiv={status === s.wert} onClick={() => setStatus(s.wert)}>
              {s.text}
            </Chip>
          ))}
        </div>
        <Eingabe placeholder="These, Instrument oder ID suchen …" value={suche} onChange={(e) => setSuche(e.target.value)} className="lg:max-w-[280px]" aria-label="Entscheidungen durchsuchen" />
      </div>

      {journal.isError ? (
        <Fehleranzeige fehler={journal.error} erneut={() => void journal.refetch()} />
      ) : journal.isPending ? (
        <Skelett className="h-[420px] rounded-2xl" />
      ) : anzahl === 0 ? (
        <Karte>
          <Leer icon={<NotebookPen className="size-5" />} titel="Keine passenden Entscheidungen" text="Filter anpassen oder nach dem Spielstart wiederkommen." />
        </Karte>
      ) : (
        <div className="relative space-y-5">
          <p className="text-[12.5px] text-text-3">{anzahl} Einträge</p>
          {gruppen.slice(0, sichtbar).map((g) => (
            <section key={g.datei} className="grid gap-3 md:grid-cols-[140px_minmax(0,1fr)]">
              <div className="md:pt-3">
                <div className="text-[13px] font-semibold text-text">{datum(g.datum)}</div>
                <div className="font-mono text-[11.5px] text-text-3">{g.eintraege[0].person}</div>
              </div>
              <Karte className="overflow-hidden">
                {g.session && (
                  <Link to="/sessions" hash={g.session.id} className="flex items-center gap-2 border-b border-rand bg-flaeche-2 px-4 py-2 text-[12.5px] text-text-3 hover:text-text">
                    <FileClock className="size-3.5" /> Session-Eintrag {g.session.id} – Abwägungen je Portfolio ansehen
                  </Link>
                )}
                <div className="p-1.5">
                  {g.eintraege.map((e) => (
                    <EntscheidungsZeile key={e.id} e={e} />
                  ))}
                </div>
              </Karte>
            </section>
          ))}
          {gruppen.length > sichtbar && (
            <div className="flex justify-center pt-2">
              <Knopf onClick={() => setSichtbar((n) => n + 20)}>Ältere Sessions laden ({gruppen.length - sichtbar} weitere Tage)</Knopf>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function Sessions() {
  const journal = useJournal();
  const ort = useLocation();
  const sessions = useMemo(() => [...(journal.data ?? [])].filter((e) => e.art === "S").reverse(), [journal.data]);
  const [kennung, setKennung] = useState("alle");
  const [sichtbar, setSichtbar] = useState(10);
  const kennungen = [...new Set(sessions.map((s) => s.auftraggeber ?? ""))].filter(Boolean);

  useEffect(() => {
    if (!ort.hash || !sessions.length) return;
    document.getElementById(ort.hash)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [ort.hash, sessions.length]);

  return (
    <div className="einblenden">
      <Seitenkopf
        titel="Sessions & Abwägungen"
        untertitel="Jede Session endet mit einem Session-Eintrag: je Portfolio die Entscheidung, die erwogenen und verworfenen Alternativen und die Begründung – auch bei Nichtstun."
      />
      {kennungen.length > 1 && (
        <div className="mb-5 flex flex-wrap gap-1.5">
          <Chip aktiv={kennung === "alle"} onClick={() => setKennung("alle")}>Alle Auftraggeber</Chip>
          {kennungen.map((k) => (
            <Chip key={k} aktiv={kennung === k} onClick={() => setKennung(k)}>
              {k}
            </Chip>
          ))}
        </div>
      )}
      {journal.isError ? (
        <Fehleranzeige fehler={journal.error} />
      ) : journal.isPending ? (
        <Skelett className="h-[420px] rounded-2xl" />
      ) : sessions.length === 0 ? (
        <Karte>
          <Leer titel="Noch keine Session-Einträge" />
        </Karte>
      ) : (
        <div className="space-y-4">
          {sessions
            .filter((s) => kennung === "alle" || s.auftraggeber === kennung)
            .slice(0, Math.max(sichtbar, sessions.findIndex((s) => s.id === ort.hash) + 1))
            .map((s) => (
              <SessionEintrag key={s.id} s={s} hervorheben={ort.hash === s.id} />
            ))}
          {sessions.length > sichtbar && (
            <div className="flex justify-center pt-2">
              <Knopf onClick={() => setSichtbar((n) => n + 10)}>Ältere Sessions laden</Knopf>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SessionEintrag({ s, hervorheben }: { s: JournalEintrag; hervorheben: boolean }) {
  const [roh, setRoh] = useState(false);
  return (
    <Karte id={s.id} className={cn("scroll-mt-20 p-5 transition-shadow", hervorheben && "ring-2 ring-akzent")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[12.5px] text-text-2">{s.id}</span>
          <Abzeichen>{s.auftraggeber}</Abzeichen>
        </div>
        <span className="text-[12.5px] text-text-3">{zeit(s.zeit)}</span>
      </div>
      {roh ? (
        <Markdown text={s.text} className="mt-4" />
      ) : (
        <>
          {s.felder.marktlage && <p className="mt-3 text-[13.5px] leading-relaxed text-text-2">{s.felder.marktlage}</p>}
          <div className="mt-4 grid gap-3 lg:grid-cols-3">
            {PROFILE.map((p) => (
              <div key={p} className="rounded-xl border border-rand bg-flaeche-2 p-3.5">
                <div className="mb-1.5 flex items-center gap-2 text-[12.5px] font-semibold text-text">
                  <span className="size-2 rounded-full" style={{ background: PROFIL_FARBE[p] }} />
                  {PROFIL_NAME[p]}
                </div>
                <Markdown text={s.felder[p] ?? "–"} className="text-[13px] [&_p]:my-0" />
              </div>
            ))}
          </div>
          {Object.entries(s.felder)
            .filter(([k]) => k.startsWith("offene punkte"))
            .map(([k, w]) => (
              <p key={k} className="mt-3 text-[12.5px] text-text-3">
                <span className="font-medium text-text-2">Nächste Session: </span>
                {w}
              </p>
            ))}
        </>
      )}
      <button onClick={() => setRoh((r) => !r)} className="mt-3 text-[12px] text-text-3 hover:text-text">
        {roh ? "Aufbereitete Ansicht" : "Originaltext anzeigen"}
      </button>
    </Karte>
  );
}
