import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Bot, CircleStop, Loader2, Play, ScrollText, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Abzeichen, Dialog, Eingabe, Feld, Fehleranzeige, Karte, KarteKopf, Knopf, Leer, Mono, Seitenkopf, Skelett } from "@/components/ui";
import { api, ApiFehler, type EinrichtungDaten, type Lauf, type LaufStatus } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { relativ, zeit } from "@/lib/format";

const ARTNAMEN: Record<string, string> = { trading: "Trading-Session", review: "Reviews und Bericht", testsession: "Testsession (AP12)" };

export function LaufStatusAbzeichen({ status }: { status: LaufStatus }) {
  const text = { wartet: "wartet", laeuft: "läuft", ok: "fertig", fehler: "Fehler", abgebrochen: "abgebrochen", limit: "Kontingent erschöpft" }[status];
  const ton = status === "ok" ? "gut" : status === "fehler" ? "schlecht" : status === "limit" || status === "abgebrochen" ? "warnung" : "akzent";
  return (
    <Abzeichen ton={ton} icon={status === "laeuft" ? <Loader2 className="size-3 animate-spin" /> : undefined}>
      {text}
    </Abzeichen>
  );
}

export function laufText(l: Lauf): string {
  return `${ARTNAMEN[l.art] ?? l.art} · ${l.modell ?? "?"}${l.aufwand ? ` / ${l.aufwand}` : ""} · ${l.auftraggeber ?? ""}`;
}

function Log({ lauf }: { lauf: Lauf }) {
  const [text, setText] = useState("");
  const ab = useRef(0);
  const [fertig, setFertig] = useState(false);
  const ende = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setText("");
    ab.current = 0;
    setFertig(false);
    let aktiv = true;
    let zeitgeber: ReturnType<typeof setTimeout>;
    const holen = async () => {
      try {
        const teil = await api<{ text: string; naechstes: number; fertig: boolean }>(`/api/laeufe/${lauf.id}/log?ab=${ab.current}`);
        if (!aktiv) return;
        if (teil.text) setText((t) => t + teil.text);
        ab.current = teil.naechstes;
        setFertig(teil.fertig);
        if (!teil.fertig || teil.text) zeitgeber = setTimeout(holen, teil.fertig ? 0 : 1500);
      } catch {
        if (aktiv) zeitgeber = setTimeout(holen, 5000);
      }
    };
    void holen();
    return () => {
      aktiv = false;
      clearTimeout(zeitgeber);
    };
  }, [lauf.id]);
  useEffect(() => ende.current?.scrollIntoView({ block: "end" }), [text]);
  return (
    <div className="max-h-[560px] overflow-auto rounded-xl border border-rand bg-[var(--bg)] p-4" aria-live="polite" aria-label="Session-Log">
      {text ? (
        <pre className="font-mono text-[12px] leading-relaxed whitespace-pre-wrap text-text-2">
          {text.split("\n").map((zeile, i) => (
            <div key={i} className={cn(zeile.startsWith("Claude:") && "text-text", zeile.startsWith("→") && "text-akzent", zeile.trimStart().startsWith("✗") && "text-schlecht", zeile.startsWith("Prüfung:") && "font-semibold text-text")}>
              {zeile || " "}
            </div>
          ))}
        </pre>
      ) : (
        <p className="text-[12.5px] text-text-3">{fertig ? "Kein Log vorhanden." : "Warte auf den Hintergrunddienst …"}</p>
      )}
      {!fertig && text && (
        <div className="mt-2 flex items-center gap-2 text-[12px] text-text-3">
          <Loader2 className="size-3.5 animate-spin" /> läuft – das Log aktualisiert sich live
        </div>
      )}
      <div ref={ende} />
    </div>
  );
}

function StartDialog({ offen, setOffen }: { offen: boolean; setOffen: (o: boolean) => void }) {
  const client = useQueryClient();
  const einrichtung = useQuery({ queryKey: ["einrichtung"], queryFn: () => api<EinrichtungDaten>("/api/einrichtung"), enabled: offen });
  const [art, setArt] = useState("trading");
  const [auftraggeber, setAuftraggeber] = useState("");
  const [ueberschreiben, setUeberschreiben] = useState(false);
  const [modell, setModell] = useState("");
  const [aufwand, setAufwand] = useState("");
  const d = einrichtung.data;
  useEffect(() => {
    if (d && !auftraggeber) setAuftraggeber(d.einstellungen.zeitplan.auftraggeber || d.optionen.auftraggeber[0]);
  }, [d, auftraggeber]);
  const zweck = d?.optionen.claude.laufarten[art]?.zweck as "trading" | "review" | undefined;
  const vorgabe = d && zweck ? d.einstellungen.claude.voreinstellungen[zweck] : undefined;
  const start = useMutation({
    mutationFn: () => api<Lauf>("/api/laeufe", { daten: { art, auftraggeber, bestaetigt: true, ...(ueberschreiben ? { modell, aufwand } : {}) } }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["laeufe"] });
      void client.invalidateQueries({ queryKey: ["ueberblick"] });
      setOffen(false);
    },
  });
  const auswahlKlasse = "h-10 w-full rounded-lg border border-rand bg-flaeche-2 px-3 text-sm text-text";
  return (
    <Dialog offen={offen} setOffen={setOffen} titel="Claude-Lauf starten" beschreibung="Der Lauf startet im Container mit dem hinterlegten Pro-Abo. Die Session-Sperre gilt; es läuft nie mehr als ein Lauf." breit>
      {!d ? (
        <Skelett className="h-48" />
      ) : (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            start.mutate();
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Feld id="l-art" label="Art">
              <select id="l-art" className={auswahlKlasse} value={art} onChange={(e) => setArt(e.target.value)}>
                {Object.entries(d.optionen.claude.laufarten).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v.name}
                  </option>
                ))}
              </select>
            </Feld>
            <Feld id="l-auftraggeber" label="Auftraggeber (Kennung)">
              <select id="l-auftraggeber" className={auswahlKlasse} value={auftraggeber} onChange={(e) => setAuftraggeber(e.target.value)}>
                {d.optionen.auftraggeber.map((a) => (
                  <option key={a}>{a}</option>
                ))}
              </select>
            </Feld>
          </div>
          <div className="rounded-xl border border-rand bg-flaeche-2/50 p-3.5 text-[13px]">
            Voreinstellung: <Mono>{vorgabe?.modell}</Mono> · Aufwand <Mono>{vorgabe?.aufwand || "Standard"}</Mono>
            <label className="mt-2 flex items-center gap-2 text-[12.5px] text-text-2">
              <input
                type="checkbox"
                className="size-4 accent-[var(--akzent)]"
                checked={ueberschreiben}
                onChange={(e) => {
                  setUeberschreiben(e.target.checked);
                  setModell(vorgabe?.modell ?? "");
                  setAufwand(vorgabe?.aufwand ?? "");
                }}
              />
              Für diesen Lauf einmalig überschreiben
            </label>
            {ueberschreiben && (
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Feld id="l-modell" label="Modell (Alias oder Modell-ID)">
                  <Eingabe id="l-modell" list="l-modelle" value={modell} onChange={(e) => setModell(e.target.value.trim())} className="font-mono text-[12.5px]" />
                  <datalist id="l-modelle">
                    {d.optionen.claude.modelle.map((m) => (
                      <option key={m.wert} value={m.wert}>
                        {m.name}
                      </option>
                    ))}
                  </datalist>
                </Feld>
                <Feld id="l-aufwand" label="Aufwand">
                  <select id="l-aufwand" className={auswahlKlasse} value={aufwand} onChange={(e) => setAufwand(e.target.value)}>
                    {d.optionen.claude.aufwand.map((a) => (
                      <option key={a.wert} value={a.wert}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                </Feld>
              </div>
            )}
          </div>
          {start.isError && (
            <p className="text-[12.5px] text-schlecht" role="alert">
              {start.error instanceof ApiFehler ? start.error.message : "Start fehlgeschlagen."}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Knopf type="button" variante="geist" onClick={() => setOffen(false)}>
              Abbrechen
            </Knopf>
            <Knopf type="submit" variante="primaer" laedt={start.isPending}>
              <Play className="size-4" /> Starten
            </Knopf>
          </div>
        </form>
      )}
    </Dialog>
  );
}

export function Laeufe() {
  const { sitzung } = useAuth();
  const admin = !!sitzung?.benutzer?.ist_admin;
  const client = useQueryClient();
  const laeufe = useQuery({
    queryKey: ["laeufe"],
    queryFn: () => api<Lauf[]>("/api/laeufe"),
    refetchInterval: (q) => (q.state.data?.some((l) => l.status === "laeuft" || l.status === "wartet") ? 3000 : 20_000),
  });
  const [auswahl, setAuswahl] = useState<string | null>(null);
  const [startOffen, setStartOffen] = useState(false);
  useEffect(() => {
    if (!auswahl && laeufe.data?.length) setAuswahl(laeufe.data[0].id);
  }, [laeufe.data, auswahl]);
  const abbrechen = useMutation({
    mutationFn: (id: string) => api<Lauf>(`/api/laeufe/${id}/abbrechen`, { daten: {} }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["laeufe"] }),
  });
  if (laeufe.isError) return <Fehleranzeige fehler={laeufe.error} erneut={() => void laeufe.refetch()} />;
  const gewaehlt = laeufe.data?.find((l) => l.id === auswahl);
  const aktiv = laeufe.data?.some((l) => l.status === "laeuft" || l.status === "wartet");
  return (
    <div className="einblenden">
      <Seitenkopf
        titel="Claude-Läufe"
        untertitel="Trading-Sessions, Reviews und Testsessions im Container: Live-Log, Ergebnis und die anschließende Prüfung mit tools/pruefe.py."
        aktionen={
          admin ? (
            <Knopf variante="primaer" onClick={() => setStartOffen(true)} disabled={aktiv}>
              <Play className="size-4" /> Lauf starten
            </Knopf>
          ) : undefined
        }
      />
      {admin && <StartDialog offen={startOffen} setOffen={setStartOffen} />}
      {!laeufe.data ? (
        <Skelett className="h-96 rounded-2xl" />
      ) : !laeufe.data.length ? (
        <Karte>
          <Leer
            icon={<Bot className="size-5" />}
            titel="Noch keine Läufe"
            text={admin ? "Claude-Token und Modell in der Einrichtung festlegen, dann hier eine Testsession oder Trading-Session starten." : "Läufe startet ein Administrator."}
            aktion={admin ? <Link to="/einrichtung" hash="claude" className="text-[13px] font-medium text-akzent hover:underline">Zur Einrichtung</Link> : undefined}
          />
        </Karte>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
          <Karte className="overflow-hidden xl:self-start">
            <ul className="divide-y divide-rand">
              {laeufe.data.map((l) => (
                <li key={l.id}>
                  <button onClick={() => setAuswahl(l.id)} className={cn("w-full px-4 py-3 text-left", auswahl === l.id ? "bg-flaeche-3" : "hover:bg-flaeche-2")}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[13px] font-medium text-text">{ARTNAMEN[l.art] ?? l.art}</span>
                      <LaufStatusAbzeichen status={l.status} />
                    </div>
                    <div className="mt-0.5 text-[12px] text-text-3">
                      {relativ(l.erstellt)} · {l.modell}
                      {l.aufwand ? ` / ${l.aufwand}` : ""} · {l.ausloeser === "zeitplan" ? "Zeitplan" : "manuell"}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </Karte>
          {gewaehlt && (
            <Karte>
              <KarteKopf
                titel={ARTNAMEN[gewaehlt.art] ?? gewaehlt.art}
                icon={<ScrollText className="size-4" />}
                untertitel={
                  <>
                    Erstellt {zeit(gewaehlt.erstellt)} · Modell <Mono>{gewaehlt.modell}</Mono> · Aufwand <Mono>{gewaehlt.aufwand || "Standard"}</Mono> · Auftraggeber{" "}
                    <Mono>{gewaehlt.auftraggeber}</Mono>
                  </>
                }
                aktion={
                  <div className="flex items-center gap-2">
                    {gewaehlt.pruefung_ok != null && (
                      <Abzeichen ton={gewaehlt.pruefung_ok ? "gut" : "schlecht"} icon={<ShieldCheck className="size-3" />}>
                        {gewaehlt.pruefung_ok ? "Prüfung bestanden" : "Prüfung mit Fehlern"}
                      </Abzeichen>
                    )}
                    {admin && (gewaehlt.status === "laeuft" || gewaehlt.status === "wartet") && (
                      <Knopf klein variante="gefahr" onClick={() => abbrechen.mutate(gewaehlt.id)} laedt={abbrechen.isPending}>
                        <CircleStop className="size-4" /> Abbrechen
                      </Knopf>
                    )}
                  </div>
                }
              />
              <div className="space-y-3 px-5 pb-5">
                {gewaehlt.meldung && (
                  <div className={cn("rounded-lg border px-3 py-2 text-[13px]", gewaehlt.status === "ok" ? "border-rand bg-flaeche-2 text-text" : "border-warnung/30 bg-warnung-flaeche text-text")}>
                    {gewaehlt.meldung}
                  </div>
                )}
                <Log lauf={gewaehlt} />
              </div>
            </Karte>
          )}
        </div>
      )}
    </div>
  );
}
