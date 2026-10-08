import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  Activity,
  AlertTriangle,
  ArchiveRestore,
  Bot,
  CalendarClock,
  Check,
  CircleDashed,
  Copy,
  Download,
  ExternalLink,
  KeyRound,
  LineChart,
  LogIn,
  Newspaper,
  Plus,
  PlugZap,
  RefreshCw,
  Rocket,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { Abzeichen, Dialog, Eingabe, Feld, Fehleranzeige, Karte, KarteKopf, Knopf, Leer, Mono, Seitenkopf, Skelett } from "@/components/ui";
import { api, ApiFehler, rohAnfrage, type Ampel, type AmpelDetail, type EigenerFeed, type EinrichtungDaten, type GeheimnisInfo, type NewsFeedStatus, type NewsStatus, type TestErgebnis, type Voreinstellung, type ZeitplanTermin } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { relativ, zeit } from "@/lib/format";

const BEREICHE = [
  { id: "claude", titel: "Claude", icon: <Bot className="size-4" /> },
  { id: "kursdaten", titel: "Kursdaten", icon: <LineChart className="size-4" /> },
  { id: "news", titel: "News", icon: <Newspaper className="size-4" /> },
  { id: "zeitplan", titel: "Sessions & Zeitplan", icon: <CalendarClock className="size-4" /> },
  { id: "spielstart", titel: "Spielstart", icon: <Rocket className="size-4" /> },
  { id: "sicherung", titel: "Sicherung", icon: <ArchiveRestore className="size-4" /> },
  { id: "system", titel: "Systemstatus", icon: <Activity className="size-4" /> },
] as const;

const WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

function fehlerText(fehler: unknown): string {
  return fehler instanceof ApiFehler || fehler instanceof Error ? fehler.message : "Unbekannter Fehler";
}

function useEinrichtung() {
  return useQuery({ queryKey: ["einrichtung"], queryFn: () => api<EinrichtungDaten>("/api/einrichtung"), refetchInterval: 30_000 });
}

type Meldung = { ok: boolean; text: string; warnung?: boolean };

/** Mutation mit Rückmeldung im Klartext; lädt danach Einrichtung und Cockpit neu. Der Rückgabewert von erfolg darf ihn zur Warnung (Erfolg mit Einschränkung) oder zum Fehler (ok: false) machen. */
function useAktion<E = unknown, V = void>(ausfuehren: (v: V) => Promise<E>, erfolg?: (e: E) => string | { text: string; ok?: boolean; warnung?: boolean }) {
  const client = useQueryClient();
  const [meldung, setMeldung] = useState<Meldung | null>(null);
  const mutation = useMutation({
    mutationFn: ausfuehren,
    onMutate: () => setMeldung(null),
    onSuccess: (e) => {
      const ergebnis = erfolg ? erfolg(e) : "Gespeichert.";
      setMeldung({ ok: true, ...(typeof ergebnis === "string" ? { text: ergebnis } : ergebnis) });
      void client.invalidateQueries({ queryKey: ["einrichtung"] });
      void client.invalidateQueries({ queryKey: ["ueberblick"] });
    },
    onError: (f) => setMeldung({ ok: false, text: fehlerText(f) }),
  });
  return { ...mutation, meldung, setMeldung };
}

function Rueckmeldung({ meldung }: { meldung: Meldung | null }) {
  if (!meldung) return null;
  const gut = meldung.ok && !meldung.warnung;
  return (
    <p role={meldung.ok ? "status" : "alert"} className={cn("flex items-start gap-1.5 text-[12.5px]", gut ? "text-gut" : meldung.ok ? "text-warnung" : "text-schlecht")}>
      {gut ? <Check className="mt-0.5 size-3.5 shrink-0" /> : <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />}
      <span>{meldung.text}</span>
    </p>
  );
}

function Testergebnis({ ergebnis, titel = "Letzter Test" }: { ergebnis: TestErgebnis | null | undefined; titel?: string }) {
  if (!ergebnis) return null;
  return (
    <div className={cn("rounded-lg border px-3 py-2 text-[12.5px]", ergebnis.ok ? "border-gut/30 bg-gut-flaeche text-gut" : "border-schlecht/30 bg-schlecht-flaeche text-schlecht")}>
      <span className="font-medium">{titel}{ergebnis.zeit ? ` (${relativ(ergebnis.zeit)})` : ""}: </span>
      {ergebnis.meldung}
      {ergebnis.beispiele?.length ? <ul className="mt-1 list-disc pl-4 text-text-2">{ergebnis.beispiele.map((b) => <li key={b}>{b}</li>)}</ul> : null}
    </div>
  );
}

function Schalter({ an, setAn, label, beschreibung }: { an: boolean; setAn: (a: boolean) => void; label: string; beschreibung?: string }) {
  return (
    <button type="button" role="switch" aria-checked={an} onClick={() => setAn(!an)} className="group flex w-full items-start gap-3 text-left">
      <span className={cn("relative mt-0.5 inline-flex h-5 w-9 shrink-0 rounded-full transition-colors", an ? "bg-gut" : "bg-flaeche-3 ring-1 ring-rand-stark")}>
        <span className={cn("absolute top-0.5 size-4 rounded-full bg-white shadow transition-transform", an ? "translate-x-[18px]" : "translate-x-0.5")} />
      </span>
      <span className="min-w-0">
        <span className="block text-[13.5px] font-medium text-text">{label}</span>
        {beschreibung && <span className="block text-[12.5px] text-text-3">{beschreibung}</span>}
      </span>
    </button>
  );
}

function Auswahl({ id, wert, setWert, optionen, className }: { id: string; wert: string; setWert: (w: string) => void; optionen: { wert: string; name: string }[]; className?: string }) {
  return (
    <select
      id={id}
      value={wert}
      onChange={(e) => setWert(e.target.value)}
      className={cn("h-10 w-full rounded-lg border border-rand bg-flaeche-2 px-3 text-sm text-text hover:border-rand-stark focus:border-akzent focus:ring-2 focus:ring-akzent/25 focus:outline-none", className)}
    >
      {optionen.map((o) => (
        <option key={o.wert} value={o.wert}>
          {o.name}
        </option>
      ))}
    </select>
  );
}

function Bereich({ id, titel, icon, untertitel, status, children }: { id: string; titel: string; icon: ReactNode; untertitel: ReactNode; status?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24" aria-labelledby={`${id}-titel`}>
      <Karte>
        <div className="flex items-start justify-between gap-4 border-b border-rand px-5 pt-4 pb-3.5">
          <div className="flex min-w-0 items-start gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-xl border border-rand bg-flaeche-2 text-text-2">{icon}</span>
            <div className="min-w-0">
              <h2 id={`${id}-titel`} className="text-[15px] font-semibold tracking-[-0.005em] text-text">
                {titel}
              </h2>
              <p className="mt-0.5 text-[12.5px] text-text-3">{untertitel}</p>
            </div>
          </div>
          {status}
        </div>
        <div className="space-y-5 p-5">{children}</div>
      </Karte>
    </section>
  );
}

function Hinweisbox({ ton = "info", children }: { ton?: "info" | "warnung"; children: ReactNode }) {
  return (
    <div className={cn("flex gap-2.5 rounded-xl border px-3.5 py-3 text-[12.5px] leading-relaxed", ton === "warnung" ? "border-warnung/30 bg-warnung-flaeche text-text-2" : "border-rand bg-flaeche-2 text-text-2")}>
      {ton === "warnung" ? <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warnung" /> : <KeyRound className="mt-0.5 size-4 shrink-0 text-text-3" />}
      <div>{children}</div>
    </div>
  );
}

// --------------------------------------------------------------------------

export function Einrichtung() {
  const { sitzung } = useAuth();
  const daten = useEinrichtung();
  useEffect(() => {
    if (!daten.data) return;
    const ziel = window.location.hash.slice(1);
    if (ziel) document.getElementById(ziel)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [daten.data]);

  if (!sitzung?.benutzer?.ist_admin)
    return (
      <Karte className="mt-6">
        <Leer titel="Nur für Administratoren" text="Die Einrichtung ist Administratoren mit Zwei-Faktor-Anmeldung vorbehalten. Den Projektstand zeigt „Roadmap & Status“." aktion={<Link to="/roadmap" className="text-[13px] font-medium text-akzent hover:underline">Zu Roadmap & Status</Link>} />
      </Karte>
    );
  if (daten.isError) return <Fehleranzeige fehler={daten.error} erneut={() => void daten.refetch()} />;
  const d = daten.data;
  const ampel = (id: string) => d?.systemstatus.find((s) => s.id === id)?.stufe;
  const offen = new Set(d?.pflichtschritte.map((p) => p.schritt));

  return (
    <div className="einblenden">
      <Seitenkopf
        titel="Einrichtung"
        untertitel="Alles, was diese Instanz braucht: Claude, Kursdaten, News, Zeitplan, Spielstart und Sicherung. Gespeichert wird in der App (App-Verzeichnis im Volume), nicht im Stack und nicht im Spielstand."
      />
      {!d ? (
        <Skelett className="h-[600px] rounded-2xl" />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
          <nav aria-label="Bereiche der Einrichtung" className="lg:sticky lg:top-20 lg:self-start">
            <ul className="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible">
              {BEREICHE.map((b) => {
                const pflicht = offen.has(b.id as never);
                const stufe = b.id === "claude" ? ampel("claude") : b.id === "kursdaten" ? ampel("kurse") : b.id === "news" ? ampel("news") : b.id === "system" ? gesamtstufe(d.systemstatus) : b.id === "spielstart" ? (d.spielstart.gestartet ? "gruen" : "gelb") : undefined;
                return (
                  <li key={b.id}>
                    <a href={`#${b.id}`} className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] font-medium whitespace-nowrap text-text-2 hover:bg-flaeche-2 hover:text-text">
                      <span className="text-text-3">{b.icon}</span>
                      <span className="flex-1">{b.titel}</span>
                      {pflicht ? <Abzeichen ton="warnung">offen</Abzeichen> : stufe && <Punkt stufe={stufe} />}
                    </a>
                  </li>
                );
              })}
            </ul>
          </nav>
          <div className="min-w-0 space-y-5">
            {d.pflichtschritte.length > 0 && (
              <Hinweisbox ton="warnung">
                <span className="font-medium text-text">Noch offen: </span>
                {d.pflichtschritte.map((p, i) => (
                  <span key={p.schritt}>
                    {i > 0 && " · "}
                    <a href={`#${p.schritt}`} className="font-medium text-akzent hover:underline">{p.titel}</a>
                  </span>
                ))}
              </Hinweisbox>
            )}
            {d.migration.ueberfluessige_variablen.length > 0 && (
              <Hinweisbox>
                <span className="font-medium text-text">Aus dem Stack entfernbar: </span>
                {d.migration.ueberfluessige_variablen.map((v) => <Mono key={v} className="mr-1.5 rounded bg-flaeche-3 px-1 py-0.5">{v}</Mono>)}
                <span>Die Werte wurden in die App-Konfiguration übernommen; ab jetzt gilt die App, nicht mehr die Umgebungsvariable.</span>
              </Hinweisbox>
            )}
            <ClaudeBereich d={d} />
            <KursBereich d={d} />
            <NewsBereich d={d} />
            <ZeitplanBereich d={d} />
            <SpielstartBereich d={d} />
            <SicherungBereich />
            <SystemBereich d={d} />
          </div>
        </div>
      )}
    </div>
  );
}

const STUFE_TEXT: Record<Ampel["stufe"], string> = { gruen: "in Ordnung", gelb: "Hinweis", rot: "Problem" };

function Punkt({ stufe }: { stufe: Ampel["stufe"] }) {
  const text = STUFE_TEXT[stufe];
  return <span className={cn("size-2.5 shrink-0 rounded-full", stufe === "gruen" ? "bg-gut" : stufe === "gelb" ? "bg-warnung" : "bg-schlecht")} role="img" aria-label={text} title={text} />;
}

/** Schlechteste Stufe aller Zeilen: so färbt sich der Punkt vor „Systemstatus“ in der Navigation und das Banner im Bereich. */
export function gesamtstufe(liste: Ampel[]): Ampel["stufe"] {
  return liste.some((s) => s.stufe === "rot") ? "rot" : liste.some((s) => s.stufe === "gelb") ? "gelb" : "gruen";
}

/** Eine einzelne Ursache (z. B. ein ausgefallener Feed): was, warum, seit wann, was dagegen hilft. */
function FehlerDetail({ detail }: { detail: AmpelDetail }) {
  const verlauf = [detail.seit ? `seit ${zeit(detail.seit)}` : null, detail.anzahl > 1 ? `${detail.anzahl} Abrufe in Folge` : null].filter(Boolean).join(" · ");
  return (
    <li className="rounded-lg border border-rand bg-flaeche px-3 py-2">
      <div className="text-[12.5px] text-text">
        <span className="font-medium">{detail.titel}</span>: {detail.text}
      </div>
      {detail.hinweis && <div className="mt-0.5 text-[12px] text-text-2">{detail.hinweis}</div>}
      {(verlauf || detail.url) && (
        <div className="mt-0.5 text-[11.5px] break-all text-text-3">
          {verlauf}
          {verlauf && detail.url ? " · " : ""}
          {detail.url && <Mono className="text-[11.5px]">{detail.url}</Mono>}
        </div>
      )}
    </li>
  );
}

// --------------------------------------------------------------------------
// Secrets

function GeheimnisFeld({ name, label, info, hinweis, platzhalter }: { name: string; label: string; info: GeheimnisInfo; hinweis?: ReactNode; platzhalter: string }) {
  const [wert, setWert] = useState("");
  const speichern = useAktion(() => api<GeheimnisInfo>(`/api/einrichtung/geheimnis/${name}`, { methode: "PUT", daten: { wert } }), () => {
    setWert("");
    return `${label} gespeichert (verschlüsselt).`;
  });
  const loeschen = useAktion(() => api<GeheimnisInfo>(`/api/einrichtung/geheimnis/${name}`, { methode: "DELETE" }), () => `${label} gelöscht.`);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label htmlFor={`g-${name}`} className="text-[13px] font-medium text-text-2">
          {label}
        </label>
        {info.gesetzt ? (
          <span className="flex items-center gap-2 text-[12.5px] text-text-3">
            <Abzeichen ton="gut" icon={<Check className="size-3" />}>gesetzt</Abzeichen>
            {info.letzte4 && <Mono>••••{info.letzte4}</Mono>}
            {info.geaendert && <span>geändert {relativ(info.geaendert)}</span>}
            {info.quelle === "umgebung" && <Abzeichen>aus Umgebung übernommen</Abzeichen>}
          </span>
        ) : (
          <Abzeichen ton="warnung">nicht gesetzt</Abzeichen>
        )}
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Eingabe
          id={`g-${name}`}
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={wert}
          onChange={(e) => setWert(e.target.value)}
          placeholder={info.gesetzt ? "Neuen Wert eintragen, um ihn zu ersetzen" : platzhalter}
          className="font-mono text-[12.5px]"
        />
        <Knopf variante="primaer" onClick={() => speichern.mutate()} laedt={speichern.isPending} disabled={wert.trim().length < 8}>
          Speichern
        </Knopf>
        {info.gesetzt && (
          <Knopf variante="geist" onClick={() => loeschen.mutate()} laedt={loeschen.isPending} aria-label={`${label} löschen`}>
            <Trash2 className="size-4" />
          </Knopf>
        )}
      </div>
      {hinweis && <p className="text-[12.5px] text-text-3">{hinweis}</p>}
      <Rueckmeldung meldung={speichern.meldung ?? loeschen.meldung} />
    </div>
  );
}

// --------------------------------------------------------------------------
// 1 Claude

interface Anmeldung {
  id: string | null;
  status: "wartet" | "laeuft" | "ok" | "fehler" | "abgebrochen";
  phase: "starte" | "warte_auf_code" | "pruefe_code" | "fertig" | "fehler";
  link: string | null;
  test_ok: boolean | null;
  meldung: string | null;
  token: GeheimnisInfo;
}

function Schritt({ nummer, titel, children, aktiv = true }: { nummer: number; titel: string; children: ReactNode; aktiv?: boolean }) {
  return (
    <div className={cn("flex gap-3", !aktiv && "opacity-50")}>
      <span className="grid size-7 shrink-0 place-items-center rounded-full border border-rand-stark text-[12px] font-semibold text-text-2">{nummer}</span>
      <div className="min-w-0 flex-1 space-y-2">
        <div className="text-[13.5px] font-medium text-text">{titel}</div>
        {children}
      </div>
    </div>
  );
}

/** Anmeldung mit dem Claude-Abo: der Container führt `claude setup-token` aus, Link und Code laufen über die UI. */
function ClaudeAnmeldung({ verbunden }: { verbunden: boolean }) {
  const client = useQueryClient();
  const [offen, setOffen] = useState(false);
  const [stand, setStand] = useState<Anmeldung | null>(null);
  const [code, setCode] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [kopiert, setKopiert] = useState(false);
  const laeuft = stand != null && (stand.status === "wartet" || stand.status === "laeuft");

  useEffect(() => {
    if (!offen || !stand?.id || !laeuft) return;
    const zeitgeber = setTimeout(async () => {
      try {
        setStand(await api<Anmeldung>(`/api/einrichtung/claude/anmeldung/${stand.id}`));
      } catch (f) {
        setFehler(fehlerText(f));
      }
    }, 1000);
    return () => clearTimeout(zeitgeber);
  }, [offen, stand, laeuft]);

  useEffect(() => {
    if (stand?.status === "ok") {
      void client.invalidateQueries({ queryKey: ["einrichtung"] });
      void client.invalidateQueries({ queryKey: ["ueberblick"] });
    }
  }, [stand?.status, client]);

  const starten = useMutation({
    mutationFn: () => api<Anmeldung>("/api/einrichtung/claude/anmeldung", { daten: {} }),
    onMutate: () => {
      setFehler(null);
      setCode("");
      setStand(null);
    },
    onSuccess: setStand,
    onError: (f) => setFehler(fehlerText(f)),
  });
  const senden = useMutation({
    mutationFn: () => api<Anmeldung>(`/api/einrichtung/claude/anmeldung/${stand!.id}/code`, { daten: { code: code.trim() } }),
    onMutate: () => setFehler(null),
    onSuccess: (s) => {
      setStand(s);
      setCode("");
    },
    onError: (f) => setFehler(fehlerText(f)),
  });

  const oeffnen = () => {
    setOffen(true);
    starten.mutate();
  };
  const schliessen = (neu: boolean) => {
    if (!neu && stand?.id && laeuft) void api(`/api/einrichtung/claude/anmeldung/${stand.id}/abbrechen`, { daten: {} }).catch(() => undefined);
    setOffen(neu);
  };
  const kopieren = async () => {
    if (!stand?.link) return;
    try {
      await navigator.clipboard.writeText(stand.link);
      setKopiert(true);
      setTimeout(() => setKopiert(false), 2000);
    } catch {
      setFehler("Kopieren nicht möglich – den Link bitte markieren und kopieren.");
    }
  };

  const phase = stand?.phase ?? "starte";
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-akzent/30 bg-akzent/5 p-4 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-semibold text-text">{verbunden ? "Claude-Abo verbunden" : "Mit dem Claude-Abo anmelden"}</div>
        <p className="mt-0.5 text-[12.5px] text-text-3">
          Der Container erzeugt den Anmeldelink selbst (<Mono>claude setup-token</Mono>). Link öffnen, mit dem Pro-Konto anmelden, den angezeigten Code hier einfügen – das Token
          wird verschlüsselt gespeichert und nie angezeigt.
        </p>
      </div>
      <Knopf variante={verbunden ? "sekundaer" : "primaer"} onClick={oeffnen}>
        <LogIn className="size-4" /> {verbunden ? "Neu anmelden" : "Mit Claude anmelden"}
      </Knopf>
      <Dialog offen={offen} setOffen={schliessen} titel="Mit dem Claude-Abo anmelden" beschreibung="Ein Jahr gültiges Token für die Sessions im Container (Claude Pro, Max, Team oder Enterprise)." breit>
        <div className="space-y-5">
          {stand?.status === "ok" ? (
            <div className="flex items-start gap-3 rounded-xl border border-gut/30 bg-gut-flaeche p-4 text-[13px] text-text">
              <Check className="mt-0.5 size-5 shrink-0 text-gut" />
              <div>
                <div className="font-semibold">Verbunden</div>
                <p className="mt-0.5 text-text-2">{stand.meldung}</p>
                {stand.token.letzte4 && <p className="mt-1 text-[12.5px] text-text-3">Token ••••{stand.token.letzte4}, verschlüsselt im App-Verzeichnis.</p>}
              </div>
            </div>
          ) : stand && !laeuft ? (
            <div className="flex items-start gap-3 rounded-xl border border-schlecht/30 bg-schlecht-flaeche p-4 text-[13px] text-text">
              <AlertTriangle className="mt-0.5 size-5 shrink-0 text-schlecht" />
              <div>
                <div className="font-semibold">Anmeldung nicht abgeschlossen</div>
                <p className="mt-0.5 text-text-2">{stand.meldung}</p>
              </div>
            </div>
          ) : (
            <>
              <Schritt nummer={1} titel="Anmeldelink öffnen">
                {!stand?.link ? (
                  <p className="flex items-center gap-2 text-[12.5px] text-text-3">
                    <RefreshCw className="size-3.5 animate-spin" /> {stand?.meldung ?? "Anmeldelink wird im Container erzeugt …"}
                  </p>
                ) : (
                  <>
                    <div className="flex gap-2">
                      <Eingabe readOnly value={stand.link} aria-label="Anmeldelink" onFocus={(e) => e.target.select()} className="font-mono text-[11.5px]" />
                      <Knopf onClick={() => void kopieren()} aria-label="Link kopieren">
                        {kopiert ? <Check className="size-4 text-gut" /> : <Copy className="size-4" />}
                      </Knopf>
                      <a href={stand.link} target="_blank" rel="noreferrer noopener" className="inline-flex h-10 shrink-0 items-center gap-2 rounded-lg bg-text px-4 text-sm font-medium text-bg hover:opacity-90">
                        Öffnen <ExternalLink className="size-4" />
                      </a>
                    </div>
                    <p className="text-[12px] text-text-3">Auf jedem Gerät möglich, z. B. am Handy. Mit dem Konto anmelden, das das Claude-Abo hat, und den Zugriff erlauben.</p>
                  </>
                )}
              </Schritt>
              <Schritt nummer={2} titel="Code von der Anmeldeseite einfügen" aktiv={phase === "warte_auf_code" || phase === "pruefe_code"}>
                <form
                  className="flex flex-col gap-2 sm:flex-row"
                  onSubmit={(e) => {
                    e.preventDefault();
                    senden.mutate();
                  }}
                >
                  <Eingabe
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    aria-label="Anmeldecode"
                    placeholder="Code von platform.claude.com"
                    autoComplete="off"
                    spellCheck={false}
                    disabled={phase !== "warte_auf_code"}
                    className="font-mono text-[12.5px]"
                  />
                  <Knopf type="submit" variante="primaer" laedt={senden.isPending || phase === "pruefe_code"} disabled={phase !== "warte_auf_code" || code.trim().length < 8}>
                    Verbinden
                  </Knopf>
                </form>
                {phase === "pruefe_code" && <p className="text-[12.5px] text-text-3">Code wird geprüft und das Token gespeichert …</p>}
                <p className="text-[12px] text-text-3">Der Link ist 10 Minuten gültig. Der Code wird nur an den wartenden Anmeldeprozess im Container weitergereicht und nicht gespeichert.</p>
              </Schritt>
            </>
          )}
          {fehler && (
            <p role="alert" className="flex items-start gap-1.5 text-[12.5px] text-schlecht">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> {fehler}
            </p>
          )}
          <div className="flex justify-end gap-2">
            {stand && !laeuft && stand.status !== "ok" && (
              <Knopf onClick={() => starten.mutate()} laedt={starten.isPending}>
                <RefreshCw className="size-4" /> Neu starten
              </Knopf>
            )}
            <Knopf variante={stand?.status === "ok" ? "primaer" : "geist"} onClick={() => schliessen(false)}>
              {stand?.status === "ok" ? "Fertig" : "Abbrechen"}
            </Knopf>
          </div>
        </div>
      </Dialog>
    </div>
  );
}

function VoreinstellungFeld({ id, titel, wert, setWert, d }: { id: string; titel: string; wert: Voreinstellung; setWert: (v: Voreinstellung) => void; d: EinrichtungDaten }) {
  const o = d.optionen.claude;
  const istAlias = o.modelle.some((m) => m.wert === wert.modell);
  const [eigen, setEigen] = useState(!istAlias);
  const konflikt = o.unvertraeglich.find((r) => r.modell === wert.modell && r.aufwand.includes(wert.aufwand));
  const modellHinweis = o.modelle.find((m) => m.wert === wert.modell)?.hinweis;
  return (
    <div className="rounded-xl border border-rand bg-flaeche-2/50 p-4">
      <div className="mb-3 text-[13.5px] font-semibold text-text">{titel}</div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Feld id={`${id}-modell`} label="Modell" hinweis={eigen ? "Volle Modell-ID, z. B. für eine exakte Version." : modellHinweis}>
          <Auswahl
            id={`${id}-modell`}
            wert={eigen ? "__eigen" : wert.modell}
            setWert={(w) => {
              if (w === "__eigen") setEigen(true);
              else {
                setEigen(false);
                setWert({ ...wert, modell: w });
              }
            }}
            optionen={[...o.modelle.map((m) => ({ wert: m.wert, name: m.name })), { wert: "__eigen", name: "Eigene Modell-ID …" }]}
          />
        </Feld>
        <Feld id={`${id}-aufwand`} label="Aufwand (Denktiefe)">
          <Auswahl id={`${id}-aufwand`} wert={wert.aufwand} setWert={(w) => setWert({ ...wert, aufwand: w })} optionen={o.aufwand} />
        </Feld>
        {eigen && (
          <div className="sm:col-span-2">
            <Feld id={`${id}-eigen`} label="Eigene Modell-ID">
              <Eingabe id={`${id}-eigen`} value={istAlias ? "" : wert.modell} onChange={(e) => setWert({ ...wert, modell: e.target.value.trim() })} placeholder="claude-…" className="font-mono text-[12.5px]" />
            </Feld>
          </div>
        )}
      </div>
      {konflikt && (
        <p className="mt-3 flex items-start gap-1.5 text-[12.5px] text-schlecht" role="alert">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> {wert.modell} mit Aufwand „{wert.aufwand}“ wird nicht unterstützt: {konflikt.grund}
        </p>
      )}
    </div>
  );
}

function ClaudeBereich({ d }: { d: EinrichtungDaten }) {
  const vorgabe = d.einstellungen.claude.voreinstellungen;
  const [trading, setTrading] = useState(vorgabe.trading);
  const [review, setReview] = useState(vorgabe.review);
  const o = d.optionen.claude;
  const konflikt = [trading, review].some((v) => o.unvertraeglich.some((r) => r.modell === v.modell && r.aufwand.includes(v.aufwand)) || !v.modell);
  const speichern = useAktion(() => api("/api/einrichtung/claude", { methode: "PUT", daten: { trading, review } }), () => "Voreinstellungen gespeichert.");
  const test = useAktion(() => api<{ status: string; meldung: string | null }>("/api/einrichtung/claude/test", { daten: {} }), (e) => e.meldung ?? "Test abgeschlossen.");
  const token = d.geheimnisse.claude_token;
  return (
    <Bereich
      id="claude"
      titel="Claude"
      icon={<Bot className="size-4" />}
      untertitel={`Anmeldung über das eigene Claude-Pro-Abo und Modellwahl für die Sessions (Claude Code ${o.cli_version} im Container).`}
      status={token.gesetzt ? <Abzeichen ton="gut">verbunden</Abzeichen> : <Abzeichen ton="warnung">Token fehlt</Abzeichen>}
    >
      <ClaudeAnmeldung verbunden={token.gesetzt} />
      <details className="group rounded-xl border border-rand bg-flaeche-2/40 px-4 py-3">
        <summary className="cursor-pointer text-[13px] font-medium text-text-2 select-none group-open:mb-3">Oder Token manuell eintragen</summary>
        <GeheimnisFeld
          name="claude_token"
          label="Claude-Token"
          info={token}
          platzhalter="sk-ant-oat01-…"
          hinweis={
            <>
              Auf einem eigenen Rechner mit installiertem Claude Code <Mono className="rounded bg-flaeche-3 px-1">claude setup-token</Mono> ausführen, im Browser mit dem Pro-Konto anmelden
              und das ausgegebene Token hier einfügen (ein Jahr gültig).
            </>
          }
        />
      </details>
      <p className="text-[12.5px] text-text-3">Ist im claude.ai-Konto eine kostenpflichtige Zusatznutzung aktiv, dort abschalten – die App kann das nicht prüfen.</p>
      <div className="flex flex-wrap items-center gap-3">
        <Knopf onClick={() => test.mutate()} laedt={test.isPending} disabled={!token.gesetzt}>
          <PlugZap className="size-4" /> Verbindung testen
        </Knopf>
        <span className="text-[12.5px] text-text-3">Kurzer Aufruf mit den gespeicherten Voreinstellungen (eine Runde, keine Werkzeuge).</span>
      </div>
      <Rueckmeldung meldung={test.meldung} />
      <Testergebnis ergebnis={d.einstellungen.claude.letzter_test} />
      <div className="grid gap-3 xl:grid-cols-2">
        <VoreinstellungFeld id="trading" titel={o.zwecke.trading ?? "Trading-Session"} wert={trading} setWert={setTrading} d={d} />
        <VoreinstellungFeld id="review" titel={o.zwecke.review ?? "Review/Bericht"} wert={review} setWert={setReview} d={d} />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Knopf variante="primaer" onClick={() => speichern.mutate()} laedt={speichern.isPending} disabled={konflikt}>
          Voreinstellungen speichern
        </Knopf>
        <span className="text-[12.5px] text-text-3">Beim manuellen Start lassen sie sich einmalig überschreiben. Modell und Aufwand stehen im Lauf, im Audit-Log und im Session-Eintrag.</span>
      </div>
      <Rueckmeldung meldung={speichern.meldung} />
    </Bereich>
  );
}

// --------------------------------------------------------------------------
// 2 Kursdaten

function KursBereich({ d }: { d: EinrichtungDaten }) {
  const k = d.einstellungen.kursdaten;
  const [anbieter, setAnbieter] = useState(k.anbieter);
  const [offen, setOffen] = useState(String(k.intervall_offen_minuten));
  const [zu, setZu] = useState(String(k.intervall_geschlossen_minuten));
  const speichern = useAktion(
    () => api("/api/einrichtung/kursdaten", { methode: "PUT", daten: { anbieter, intervall_offen_minuten: Number(offen), intervall_geschlossen_minuten: Number(zu) } }),
    () => "Kursdaten gespeichert.",
  );
  const test = useAktion((quelle: string) => api<{ meldung: string | null }>("/api/einrichtung/kursdaten/test", { daten: { anbieter: quelle } }), (e) => e.meldung ?? "Test abgeschlossen.");
  const abruf = useAktion(() => api<{ meldung: string | null }>("/api/einrichtung/kursdaten/abrufen", { daten: {} }), (e) => e.meldung ?? "Abruf beauftragt.");
  const karten = [{ id: "keiner" as const, name: "Nur yfinance", hinweis: "Bestehende freie Quelle (Yahoo Finance, verzögert). Kein Key nötig." }, ...d.optionen.kursanbieter];
  const verzoegert = anbieter === "keiner";
  return (
    <Bereich
      id="kursdaten"
      titel="Kursdaten"
      icon={<LineChart className="size-4" />}
      untertitel="Reihenfolge: gewählter Anbieter → yfinance → nur zur Anzeige der letzte bekannte Kurs (gekennzeichnet „veraltet“). Gebucht wird nur zu protokollierten Kursen."
      status={d.pflichtschritte.some((p) => p.schritt === "kursdaten") ? <Abzeichen ton="warnung">kein Kurs</Abzeichen> : <Abzeichen ton="gut">Kurse kommen an</Abzeichen>}
    >
      <div className="grid gap-2 md:grid-cols-3" role="radiogroup" aria-label="Kursanbieter">
        {karten.map((karte) => (
          <button
            key={karte.id}
            type="button"
            role="radio"
            aria-checked={anbieter === karte.id}
            onClick={() => setAnbieter(karte.id)}
            className={cn("rounded-xl border p-3.5 text-left transition-colors", anbieter === karte.id ? "border-akzent bg-akzent/10" : "border-rand bg-flaeche-2/50 hover:border-rand-stark")}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[13.5px] font-semibold text-text">{karte.name}</span>
              {anbieter === karte.id && <Check className="size-4 text-akzent" />}
            </div>
            <p className="mt-1 text-[12px] leading-snug text-text-3">{karte.hinweis}</p>
          </button>
        ))}
      </div>
      {verzoegert && (
        <Hinweisbox>
          <span className="font-medium text-text">Nur yfinance: </span>
          Die Kurse sind typischerweise etwa 15 Minuten verzögert. Das genügt den Regeln (Handel nur mit Kursen, die höchstens 30 Minuten alt sind), lässt für US-Werte aber wenig
          Spielraum. <b>Empfehlung:</b> einen kostenlosen Finnhub-Key eintragen (Echtzeit-Kurse für US-Aktien und -ETFs). Xetra-Werte, Indizes und Futures bleiben bei yfinance, weil der
          Anbieter sie im kostenlosen Zugang nicht als dasselbe Instrument führt; fällt ein Anbieter aus oder ist sein Kontingent erschöpft, übernimmt yfinance automatisch.
        </Hinweisbox>
      )}
      {d.optionen.kursanbieter.map((a) => (
        <div key={a.id} className={cn("space-y-2", anbieter !== a.id && "opacity-80")}>
          <GeheimnisFeld name={`kurs_key_${a.id}`} label={`${a.name}: API-Key`} info={d.geheimnisse[`kurs_key_${a.id}`]} platzhalter="API-Key des Anbieters" />
          {a.doku && (
            <a href={a.doku} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-[12.5px] text-text-3 hover:text-text">
              Dokumentation <ExternalLink className="size-3" />
            </a>
          )}
        </div>
      ))}
      <div className="grid gap-3 sm:grid-cols-2">
        <Feld id="k-offen" label="Abruf bei offenem Markt (Minuten)" hinweis="Xetra oder NYSE/NASDAQ offen. Standard 5.">
          <Eingabe id="k-offen" inputMode="numeric" value={offen} onChange={(e) => setOffen(e.target.value.replace(/\D/g, ""))} />
        </Feld>
        <Feld id="k-zu" label="Abruf außerhalb der Handelszeit (Minuten)" hinweis="Standard 60; nach Börsenschluss zusätzlich einmal mit Tagesdaten.">
          <Eingabe id="k-zu" inputMode="numeric" value={zu} onChange={(e) => setZu(e.target.value.replace(/\D/g, ""))} />
        </Feld>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Knopf variante="primaer" onClick={() => speichern.mutate()} laedt={speichern.isPending}>
          Speichern
        </Knopf>
        {(anbieter === "keiner" ? ["yfinance"] : [anbieter, "yfinance"]).map((q) => (
          <Knopf key={q} onClick={() => test.mutate(q)} laedt={test.isPending && test.variables === q}>
            <PlugZap className="size-4" /> {q === "yfinance" ? "yfinance testen" : "Verbindung testen"}
          </Knopf>
        ))}
        <Knopf variante="geist" onClick={() => abruf.mutate()} laedt={abruf.isPending}>
          <RefreshCw className="size-4" /> Jetzt abrufen
        </Knopf>
      </div>
      <Rueckmeldung meldung={speichern.meldung ?? test.meldung ?? abruf.meldung} />
      <Testergebnis ergebnis={k.letzter_test} titel={`Letzter Test${k.letzter_test?.anbieter ? ` (${k.letzter_test.anbieter})` : ""}`} />
    </Bereich>
  );
}

// --------------------------------------------------------------------------
// 3 News

function kennung(name: string): string {
  const basis = name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 30);
  return basis.length >= 2 ? `eigen-${basis}` : `eigen-${Date.now().toString(36)}`;
}

/** Ergebnis des letzten Abrufs: ausgefallene Feeds mit Ursache, Dauer und Hinweis; darunter alle Feeds. */
export function NewsAbrufstatus({ status }: { status: NewsStatus }) {
  if (!status.zeit) return <p className="text-[12.5px] text-text-3">Noch kein Abruf. „Jetzt abrufen“ startet ihn sofort, sonst übernimmt es der Hintergrunddienst.</p>;
  const ausgefallen = status.feeds.filter((f) => !f.ok);
  const stufe: Ampel["stufe"] = ausgefallen.length === 0 ? "gruen" : ausgefallen.length === status.anzahl_feeds ? "rot" : "gelb";
  return (
    <div data-stufe={stufe} className={cn("rounded-xl border px-4 py-3", BANNER[stufe].rahmen)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-[13px] font-medium text-text">
          Letzter Abruf {relativ(status.zeit)}: {status.neu} neue Meldungen aus {status.anzahl_feeds} Feeds
        </div>
        {stufe === "gruen" ? (
          <Abzeichen ton="gut">alle Feeds erreichbar</Abzeichen>
        ) : (
          <Abzeichen ton={stufe === "gelb" ? "warnung" : "schlecht"} icon={<AlertTriangle className="size-3" />}>
            {ausgefallen.length} von {status.anzahl_feeds} mit Fehler
          </Abzeichen>
        )}
      </div>
      {ausgefallen.length > 0 && (
        <ul className="mt-2.5 space-y-1.5" aria-label="Feeds mit Fehler">
          {ausgefallen.map((f) => (
            <FehlerDetail key={f.id} detail={{ titel: f.name, text: f.fehler ?? "Fehler ohne Angabe.", hinweis: f.hinweis, seit: f.seit, anzahl: f.in_folge, url: f.url }} />
          ))}
        </ul>
      )}
      <details className="mt-2.5 text-[12.5px]">
        <summary className="cursor-pointer text-text-2 hover:text-text">Alle {status.anzahl_feeds} Feeds im letzten Abruf</summary>
        <ul className="mt-2 divide-y divide-rand rounded-lg border border-rand bg-flaeche">
          {status.feeds.map((f) => (
            <li key={f.id} className="flex items-start justify-between gap-3 px-3 py-1.5">
              <span className="min-w-0 text-text-2">{f.name}</span>
              <span className={cn("shrink-0 text-right", f.ok ? "text-text-3" : "text-schlecht")}>{f.ok ? `${f.neu} neu von ${f.anzahl}` : "Fehler"}</span>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

/** Kurzhinweis an einem Feed der Liste, wenn dessen letzter Abruf fehlschlug (Einzelheiten stehen im Abrufstatus). */
function FeedAusfall({ feeds }: { feeds?: NewsFeedStatus[] }) {
  if (!feeds?.length) return null;
  const erste = feeds[0];
  const text = feeds.length === 1 ? `Letzter Abruf fehlgeschlagen: ${erste.fehler ?? "Fehler"}` : `Letzter Abruf bei ${feeds.length} Werten fehlgeschlagen, z. B. ${erste.name}: ${erste.fehler ?? "Fehler"}`;
  return (
    <p className="mt-1 ml-12 flex items-start gap-1.5 text-[12px] text-warnung">
      <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
      <span>{text}</span>
    </p>
  );
}

function NewsBereich({ d }: { d: EinrichtungDaten }) {
  const n = d.einstellungen.news;
  const [aktiv, setAktiv] = useState(n.aktiv);
  const [intervall, setIntervall] = useState(String(n.intervall_minuten));
  // Gespeicherte Kennungen, die es als Standard-Feed nicht mehr gibt (z. B. nach einem Update), fallen weg.
  const [deaktiviert, setDeaktiviert] = useState<string[]>(n.deaktiviert.filter((id) => d.optionen.news_feeds.some((f) => !f.eigen && f.id === id)));
  const [eigene, setEigene] = useState<EigenerFeed[]>(n.eigene);
  const [agent, setAgent] = useState(n.user_agent);
  const [neuName, setNeuName] = useState("");
  const [neuUrl, setNeuUrl] = useState("");
  const [neuTicker, setNeuTicker] = useState("");
  const standard = d.optionen.news_feeds.filter((f) => !f.eigen);
  const speichern = useAktion(
    () => api("/api/einrichtung/news", { methode: "PUT", daten: { aktiv, intervall_minuten: Number(intervall), deaktiviert, eigene, user_agent: agent } }),
    () => "News-Einstellungen gespeichert.",
  );
  // Ein fehlgeschlagener Test ist ein Fehler und kein Erfolg: Ursache und Abhilfe stehen in der Meldung.
  const test = useAktion((url: string) => api<{ status: string; meldung: string | null; ergebnis: { beispiele?: string[] } | null }>("/api/einrichtung/news/test", { daten: { url } }), (e) => ({
    text: [e.meldung ?? "Test abgeschlossen.", ...(e.ergebnis?.beispiele ?? []).map((b) => `„${b}“`)].join(" "),
    ok: e.status !== "fehler",
  }));
  const abruf = useAktion(
    () => api<{ status: string; meldung: string | null; ergebnis: { fehlerhaft?: number } | null }>("/api/einrichtung/news/abrufen", { daten: {} }),
    (e) => ({ text: e.meldung ?? "Abruf beauftragt.", warnung: e.status === "fehler" || (e.ergebnis?.fehlerhaft ?? 0) > 0 }),
  );
  // Ausgefallene Feeds nach Kennung der Konfiguration; je Wert aufgelöste Vorlagen ("yahoo-ticker:SAP.DE") laufen unter der Vorlage.
  const ausfaelle = new Map<string, NewsFeedStatus[]>();
  for (const f of d.news_status.feeds) {
    if (f.ok) continue;
    const basis = f.id.split(":")[0];
    ausfaelle.set(basis, [...(ausfaelle.get(basis) ?? []), f]);
  }
  const hinzufuegen = () => {
    if (!neuName.trim() || !/^https?:\/\//.test(neuUrl.trim())) return;
    const ticker = neuTicker.split(/[\s,;]+/).map((t) => t.trim().toUpperCase()).filter(Boolean);
    setEigene([...eigene, { id: kennung(neuName), name: neuName.trim(), url: neuUrl.trim(), aktiv: true, ticker }]);
    setNeuName("");
    setNeuUrl("");
    setNeuTicker("");
  };
  return (
    <Bereich
      id="news"
      titel="News"
      icon={<Newspaper className="size-4" />}
      untertitel="RSS-Feeds als datierte Quelle für Sessions und Cockpit. Gespeichert werden nur Titel, Kurztext und Link (news/ im Datenverzeichnis)."
    >
      <div className="grid gap-4 sm:grid-cols-[1fr_200px]">
        <Schalter an={aktiv} setAn={setAktiv} label="News-Abruf aktiv" beschreibung="Der Hintergrunddienst ruft alle aktiven Feeds ab und dedupliziert die Meldungen." />
        <Feld id="n-intervall" label="Intervall (Minuten)">
          <Eingabe id="n-intervall" inputMode="numeric" value={intervall} onChange={(e) => setIntervall(e.target.value.replace(/\D/g, ""))} />
        </Feld>
      </div>
      <NewsAbrufstatus status={d.news_status} />
      <div>
        <div className="mb-2 text-[13px] font-medium text-text-2">Standard-Feeds (config/news.json)</div>
        <ul className="divide-y divide-rand rounded-xl border border-rand">
          {standard.map((f) => {
            const an = !deaktiviert.includes(f.id);
            return (
              <li key={f.id} className="flex flex-wrap items-center gap-3 px-3.5 py-2.5">
                <div className="min-w-0 flex-1">
                  <Schalter an={an} setAn={(a) => setDeaktiviert(a ? deaktiviert.filter((x) => x !== f.id) : [...deaktiviert, f.id])} label={f.name} beschreibung={f.je_ticker ? "je Wert im Universum und in den Portfolios" : f.url} />
                  {an && <FeedAusfall feeds={ausfaelle.get(f.id)} />}
                </div>
                {!f.je_ticker && (
                  <Knopf klein variante="geist" onClick={() => test.mutate(f.url)} laedt={test.isPending && test.variables === f.url}>
                    Feed testen
                  </Knopf>
                )}
              </li>
            );
          })}
        </ul>
      </div>
      <div>
        <div className="mb-2 text-[13px] font-medium text-text-2">Eigene Feeds</div>
        {eigene.length > 0 && (
          <ul className="mb-3 divide-y divide-rand rounded-xl border border-rand">
            {eigene.map((f, i) => (
              <li key={f.id} className="flex flex-wrap items-center gap-3 px-3.5 py-2.5">
                <div className="min-w-0 flex-1">
                  <Schalter an={f.aktiv} setAn={(a) => setEigene(eigene.map((x, j) => (j === i ? { ...x, aktiv: a } : x)))} label={f.name} beschreibung={`${f.url}${f.ticker.length ? ` · ${f.ticker.join(", ")}` : ""}`} />
                  {f.aktiv && <FeedAusfall feeds={ausfaelle.get(f.id)} />}
                </div>
                <Knopf klein variante="geist" onClick={() => test.mutate(f.url)} laedt={test.isPending && test.variables === f.url}>
                  Feed testen
                </Knopf>
                <Knopf klein variante="geist" onClick={() => setEigene(eigene.filter((_, j) => j !== i))} aria-label={`${f.name} entfernen`}>
                  <X className="size-4" />
                </Knopf>
              </li>
            ))}
          </ul>
        )}
        <div className="grid gap-2 sm:grid-cols-[1fr_1.4fr_0.8fr_auto]">
          <Eingabe aria-label="Name des Feeds" value={neuName} onChange={(e) => setNeuName(e.target.value)} placeholder="Name" />
          <Eingabe aria-label="Adresse des Feeds" value={neuUrl} onChange={(e) => setNeuUrl(e.target.value)} placeholder="https://…/rss" />
          <Eingabe aria-label="Ticker (optional)" value={neuTicker} onChange={(e) => setNeuTicker(e.target.value)} placeholder="Ticker, optional" />
          <div className="flex gap-2">
            <Knopf onClick={() => test.mutate(neuUrl.trim())} disabled={!/^https?:\/\//.test(neuUrl.trim())} laedt={test.isPending && test.variables === neuUrl.trim()}>
              Testen
            </Knopf>
            <Knopf onClick={hinzufuegen} disabled={!neuName.trim() || !/^https?:\/\//.test(neuUrl.trim())}>
              <Plus className="size-4" /> Hinzufügen
            </Knopf>
          </div>
        </div>
      </div>
      <Feld id="n-agent" label="User-Agent (optional)" hinweis="Die SEC verlangt eine Kontaktangabe im User-Agent; ohne sie antwortet SEC EDGAR mit 403. Die Angabe bleibt in der App-Konfiguration, nie im Spielstand.">
        <Eingabe id="n-agent" value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="StockMaster3000/1.0 (Kontakt)" />
      </Feld>
      <div className="flex flex-wrap items-center gap-2">
        <Knopf variante="primaer" onClick={() => speichern.mutate()} laedt={speichern.isPending}>
          Speichern
        </Knopf>
        <Knopf variante="geist" onClick={() => abruf.mutate()} laedt={abruf.isPending}>
          <RefreshCw className="size-4" /> Jetzt abrufen
        </Knopf>
      </div>
      <Rueckmeldung meldung={speichern.meldung ?? test.meldung ?? abruf.meldung} />
    </Bereich>
  );
}

// --------------------------------------------------------------------------
// 4 Sessions und Zeitplan

function ZeitplanBereich({ d }: { d: EinrichtungDaten }) {
  const z = d.einstellungen.zeitplan;
  const [automatik, setAutomatik] = useState(z.automatik);
  const [zone, setZone] = useState(z.zeitzone);
  const [auftraggeber, setAuftraggeber] = useState(z.auftraggeber);
  const [termine, setTermine] = useState<ZeitplanTermin[]>(z.termine);
  const speichern = useAktion(() => api("/api/einrichtung/zeitplan", { methode: "PUT", daten: { automatik, zeitzone: zone, auftraggeber, termine } }), () => "Zeitplan gespeichert.");
  const aendern = (i: number, neu: Partial<ZeitplanTermin>) => setTermine(termine.map((t, j) => (j === i ? { ...t, ...neu } : t)));
  return (
    <Bereich
      id="zeitplan"
      titel="Sessions & Zeitplan"
      icon={<CalendarClock className="size-4" />}
      untertitel="Sessions laufen im Container. Automatisch nur an Handelstagen (Xetra oder NYSE), nie parallel zu einer Session-Sperre. Unabhängig davon bucht der Hintergrunddienst jede Nacht um 00:30 Uhr alle Tage bis gestern nach (vorgemerkte Orders, Stops, Tagesabschluss)."
      status={automatik ? <Abzeichen ton="gut">Automatik an</Abzeichen> : <Abzeichen>Automatik aus</Abzeichen>}
    >
      <Schalter an={automatik} setAn={setAutomatik} label="Sessions automatisch starten" beschreibung="Mit den Voreinstellungen aus dem Bereich Claude; manueller Start jederzeit unter Claude-Läufe." />
      <div className="grid gap-3 sm:grid-cols-2">
        <Feld id="z-zone" label="Zeitzone">
          <Eingabe id="z-zone" value={zone} onChange={(e) => setZone(e.target.value)} />
        </Feld>
        <Feld id="z-auftraggeber" label="Auftraggeber der geplanten Sessions" hinweis="Kennung aus config/projekt.json; steht in Sperre und Journal.">
          <Auswahl id="z-auftraggeber" wert={auftraggeber} setWert={setAuftraggeber} optionen={d.optionen.auftraggeber.map((a) => ({ wert: a, name: a }))} />
        </Feld>
      </div>
      <div className="space-y-2">
        {termine.map((t, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2 rounded-xl border border-rand bg-flaeche-2/50 p-2.5">
            <div className="flex gap-1" role="group" aria-label="Wochentage">
              {WOCHENTAGE.map((tag, n) => {
                const an = t.wochentage.includes(n);
                return (
                  <button
                    key={tag}
                    type="button"
                    aria-pressed={an}
                    onClick={() => aendern(i, { wochentage: an ? t.wochentage.filter((x) => x !== n) : [...t.wochentage, n].sort() })}
                    className={cn("h-8 w-9 rounded-md text-[12.5px] font-medium", an ? "bg-text text-bg" : "bg-flaeche-3 text-text-3 hover:text-text")}
                  >
                    {tag}
                  </button>
                );
              })}
            </div>
            <Eingabe aria-label="Uhrzeit" type="time" value={t.uhrzeit} onChange={(e) => aendern(i, { uhrzeit: e.target.value })} className="h-8 w-28" />
            <Auswahl id={`z-art-${i}`} wert={t.art} setWert={(w) => aendern(i, { art: w as ZeitplanTermin["art"] })} optionen={[{ wert: "trading", name: "Trading-Session" }, { wert: "review", name: "Reviews und Bericht" }]} className="h-8 w-48" />
            <Knopf klein variante="geist" onClick={() => setTermine(termine.filter((_, j) => j !== i))} aria-label="Termin entfernen">
              <Trash2 className="size-4" />
            </Knopf>
          </div>
        ))}
        <Knopf klein onClick={() => setTermine([...termine, { wochentage: [0, 1, 2, 3, 4], uhrzeit: "09:35", art: "trading" }])}>
          <Plus className="size-4" /> Termin hinzufügen
        </Knopf>
        <p className="text-[12.5px] text-text-3">Vorschlag: werktags 09:35 (nach Xetra-Eröffnung) und 21:30 (vor US-Börsenschluss um 22:00 deutscher Zeit).</p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Knopf variante="primaer" onClick={() => speichern.mutate()} laedt={speichern.isPending}>
          Speichern
        </Knopf>
        <Link to="/laeufe" className="text-[13px] font-medium text-akzent hover:underline">
          Session jetzt starten → Claude-Läufe
        </Link>
      </div>
      <Rueckmeldung meldung={speichern.meldung} />
    </Bereich>
  );
}

// --------------------------------------------------------------------------
// 5 Spielstart

function SpielstartBereich({ d }: { d: EinrichtungDaten }) {
  const s = d.spielstart;
  const [freigabe, setFreigabe] = useState(s.auftraggeber[0] ?? "");
  const [bestaetigt, setBestaetigt] = useState(false);
  const [dialog, setDialog] = useState(false);
  const [passwort, setPasswort] = useState("");
  const [vorziehenDialog, setVorziehenDialog] = useState(false);
  const vorziehen = useAktion(
    () => api<{ meldungen: string[] }>("/api/einrichtung/spielstart/vorziehen", { daten: { startdatum: s.vorziehen.ziel, passwort } }),
    (e) => {
      setVorziehenDialog(false);
      setPasswort("");
      return e.meldungen.slice(-1).join(" ") || "Startdatum vorgezogen.";
    },
  );
  const start = useAktion(
    () => api<{ meldungen: string[] }>("/api/einrichtung/spielstart", { daten: { freigabe_durch: freigabe, freigabe_ap12_bestaetigt: bestaetigt, passwort } }),
    (e) => {
      setDialog(false);
      setPasswort("");
      return e.meldungen.slice(-3).join(" ");
    },
  );
  return (
    <Bereich
      id="spielstart"
      titel="Spielstart"
      icon={<Rocket className="size-4" />}
      untertitel="Legt die drei Portfolios mit je 1.000 EUR an (tools/init.py). Es gibt weder ein festes Start- noch ein Enddatum: Das Spiel beginnt beim Start (heute). Ein früher gesetztes, noch unberührtes Startdatum lässt sich auf heute vorziehen – nie rückwirkend. Voraussetzung ist die Freigabe nach AP12 durch einen Auftraggeber (regeln.md Abschnitt 2)."
      status={s.gestartet ? <Abzeichen ton="gut">gestartet {s.spiel.startdatum}</Abzeichen> : <Abzeichen ton="warnung">nicht gestartet</Abzeichen>}
    >
      <ul className="space-y-1.5">
        {s.punkte.map((p) => (
          <li key={p.id} className="flex items-start gap-2.5 text-[13px]">
            {p.ok ? <Check className="mt-0.5 size-4 shrink-0 text-gut" aria-label="erfüllt" /> : p.pflicht ? <X className="mt-0.5 size-4 shrink-0 text-schlecht" aria-label="fehlt" /> : <CircleDashed className="mt-0.5 size-4 shrink-0 text-warnung" aria-label="empfohlen" />}
            <span className={cn(p.ok ? "text-text-2" : "text-text")}>
              {p.text}
              {!p.pflicht && <span className="ml-1.5 text-[11.5px] text-text-3">(empfohlen)</span>}
            </span>
          </li>
        ))}
      </ul>
      {s.gestartet ? (
        <Hinweisbox>
          Gestartet am <b>{s.spiel.startdatum}</b>
          {s.spiel.freigabe_ap12 && <> · Freigabe nach AP12: <Mono>{s.spiel.freigabe_ap12}</Mono></>}
          {s.spiel.initialisiert && <> · initialisiert {zeit(s.spiel.initialisiert)}</>}. Ein Neustart braucht die Zustimmung aller Auftraggeber und ist hier nicht vorgesehen.
        </Hinweisbox>
      ) : null}
      {s.gestartet && s.vorziehen.ziel && (
        <div className="space-y-2">
          <p className="text-[13px] text-text-2">
            {s.vorziehen.moeglich
              ? `Es ist noch nichts gebucht: Das Startdatum lässt sich auf ${s.vorziehen.ziel} vorziehen, damit Trading-Läufe sofort handeln können. Rückwirkend geht es nie.`
              : `Vorziehen auf ${s.vorziehen.ziel} ist nicht möglich: ${s.vorziehen.grund ?? ""}`}
          </p>
          {s.vorziehen.moeglich && (
            <Knopf variante="primaer" onClick={() => setVorziehenDialog(true)}>
              <Rocket className="size-4" /> Startdatum auf {s.vorziehen.ziel} vorziehen …
            </Knopf>
          )}
          <Rueckmeldung meldung={vorziehen.meldung} />
        </div>
      )}
      {!s.gestartet && (
        <>
          <Feld id="s-freigabe" label="Freigabe nach AP12 durch">
            <Auswahl id="s-freigabe" wert={freigabe} setWert={setFreigabe} optionen={s.auftraggeber.map((a) => ({ wert: a, name: a }))} />
          </Feld>
          <p className="text-[12.5px] text-text-3">Das Spiel beginnt in dem Moment, in dem Sie es starten (Starttag: heute). Es gibt kein festes Start- oder Enddatum.</p>
          <label className="flex items-start gap-2.5 text-[13px] text-text">
            <input type="checkbox" className="mt-0.5 size-4 accent-[var(--akzent)]" checked={bestaetigt} onChange={(e) => setBestaetigt(e.target.checked)} />
            Der genannte Auftraggeber hat die Freigabe nach AP12 erteilt (Testsession, Anlagerichtlinien, Auslegungsfragen).
          </label>
          <Knopf variante="primaer" onClick={() => setDialog(true)} disabled={!s.bereit || !bestaetigt}>
            <Rocket className="size-4" /> Spiel jetzt starten …
          </Knopf>
        </>
      )}
      <Rueckmeldung meldung={start.meldung} />
      <Dialog offen={dialog} setOffen={setDialog} titel="Spiel jetzt starten?" beschreibung={`Das Spiel beginnt heute, Freigabe durch ${freigabe}. Das lässt sich nicht rückgängig machen.`}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            start.mutate();
          }}
          className="space-y-4"
        >
          <Feld id="s-pw" label="Eigenes Passwort zur Bestätigung">
            <Eingabe id="s-pw" type="password" autoComplete="current-password" value={passwort} onChange={(e) => setPasswort(e.target.value)} autoFocus />
          </Feld>
          <Rueckmeldung meldung={start.meldung?.ok === false ? start.meldung : null} />
          <div className="flex justify-end gap-2">
            <Knopf type="button" variante="geist" onClick={() => setDialog(false)}>
              Abbrechen
            </Knopf>
            <Knopf type="submit" variante="primaer" laedt={start.isPending} disabled={!passwort}>
              Endgültig starten
            </Knopf>
          </div>
        </form>
      </Dialog>
      <Dialog offen={vorziehenDialog} setOffen={setVorziehenDialog} titel="Startdatum vorziehen?" beschreibung={`Neues Startdatum ${s.vorziehen.ziel ?? ""}. Das geht nur, solange nichts gebucht oder bewertet wurde.`}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            vorziehen.mutate();
          }}
          className="space-y-4"
        >
          <Feld id="v-pw" label="Eigenes Passwort zur Bestätigung">
            <Eingabe id="v-pw" type="password" autoComplete="current-password" value={passwort} onChange={(e) => setPasswort(e.target.value)} autoFocus />
          </Feld>
          <Rueckmeldung meldung={vorziehen.meldung?.ok === false ? vorziehen.meldung : null} />
          <div className="flex justify-end gap-2">
            <Knopf type="button" variante="geist" onClick={() => setVorziehenDialog(false)}>
              Abbrechen
            </Knopf>
            <Knopf type="submit" variante="primaer" laedt={vorziehen.isPending} disabled={!passwort}>
              Vorziehen
            </Knopf>
          </div>
        </form>
      </Dialog>
    </Bereich>
  );
}

// --------------------------------------------------------------------------
// 6 Sicherung

function herunterladen(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

function SicherungBereich() {
  const [mitSecrets, setMitSecrets] = useState(false);
  const [sPw, setSPw] = useState("");
  const [sPw2, setSPw2] = useState("");
  const [datei, setDatei] = useState<File | null>(null);
  const [kontoPw, setKontoPw] = useState("");
  const [restorePw, setRestorePw] = useState("");
  const [einstellungen, setEinstellungen] = useState(true);
  const [dialog, setDialog] = useState(false);
  const exportieren = useAktion(async () => {
    const antwort = await rohAnfrage("/api/sicherung/export", { daten: { mit_geheimnissen: mitSecrets, sicherungs_passwort: mitSecrets ? sPw : null, bestaetigt: mitSecrets } });
    const name = /filename="?([^";]+)"?/.exec(antwort.headers.get("content-disposition") ?? "")?.[1] ?? "stockmaster-sicherung.tar.gz";
    herunterladen(await antwort.blob(), name);
    return name;
  }, (name) => `Sicherung ${name} heruntergeladen.`);
  const wiederherstellen = useAktion(async () => {
    const kopf: Record<string, string> = { "X-Bestaetigung-Passwort": kontoPw };
    if (restorePw) kopf["X-Sicherung-Passwort"] = restorePw;
    const antwort = await rohAnfrage(`/api/sicherung/wiederherstellen?einstellungen_uebernehmen=${einstellungen}`, { koerper: datei!, kopf });
    return (await antwort.json()) as { vorher_gesichert: string; geheimnisse: string[] };
  }, (e) => {
    setDialog(false);
    setKontoPw("");
    return `Wiederhergestellt. Der vorherige Stand liegt als ${e.vorher_gesichert} im App-Verzeichnis${e.geheimnisse.length ? `; ${e.geheimnisse.length} Secret(s) übernommen` : ""}.`;
  });
  const exportGesperrt = mitSecrets && (sPw.length < 12 || sPw !== sPw2);
  return (
    <Bereich
      id="sicherung"
      titel="Sicherung"
      icon={<ArchiveRestore className="size-4" />}
      untertitel="Export des Datenverzeichnisses als tar.gz inklusive lokalem Git (Prüfspur). Standardmäßig ohne Secrets und nie mit dem Master-Schlüssel."
    >
      <div className="grid gap-5 xl:grid-cols-2">
        <div className="space-y-3 rounded-xl border border-rand bg-flaeche-2/50 p-4">
          <div className="flex items-center gap-2 text-[13.5px] font-semibold text-text">
            <Download className="size-4 text-text-3" /> Export
          </div>
          <Schalter an={mitSecrets} setAn={setMitSecrets} label="Secrets beilegen (verschlüsselt)" beschreibung="Claude-Token und Kurs-Keys, mit einem eigenen Sicherungspasswort verschlüsselt (scrypt, AES-256-GCM)." />
          {mitSecrets && (
            <div className="grid gap-2 sm:grid-cols-2">
              <Eingabe type="password" aria-label="Sicherungspasswort" autoComplete="new-password" value={sPw} onChange={(e) => setSPw(e.target.value)} placeholder="Sicherungspasswort (mind. 12)" />
              <Eingabe type="password" aria-label="Sicherungspasswort wiederholen" autoComplete="new-password" value={sPw2} onChange={(e) => setSPw2(e.target.value)} placeholder="wiederholen" />
            </div>
          )}
          <Knopf variante="primaer" onClick={() => exportieren.mutate()} laedt={exportieren.isPending} disabled={exportGesperrt}>
            <Download className="size-4" /> {mitSecrets ? "Export mit Secrets" : "Export herunterladen"}
          </Knopf>
          <Rueckmeldung meldung={exportieren.meldung} />
        </div>
        <div className="space-y-3 rounded-xl border border-rand bg-flaeche-2/50 p-4">
          <div className="flex items-center gap-2 text-[13.5px] font-semibold text-text">
            <Upload className="size-4 text-text-3" /> Wiederherstellen
          </div>
          <input
            type="file"
            accept=".gz,.tgz,application/gzip"
            aria-label="Sicherungsdatei"
            onChange={(e) => setDatei(e.target.files?.[0] ?? null)}
            className="block w-full text-[12.5px] text-text-2 file:mr-3 file:rounded-lg file:border file:border-rand file:bg-flaeche-3 file:px-3 file:py-1.5 file:text-text"
          />
          <Schalter an={einstellungen} setAn={setEinstellungen} label="Einstellungen übernehmen" beschreibung="Claude-Voreinstellungen, Kursdaten, News und Zeitplan aus der Sicherung (ohne Secrets)." />
          <Eingabe type="password" aria-label="Sicherungspasswort (nur bei Sicherung mit Secrets)" value={restorePw} onChange={(e) => setRestorePw(e.target.value)} placeholder="Sicherungspasswort (nur mit Secrets)" />
          <Knopf variante="gefahr" onClick={() => setDialog(true)} disabled={!datei}>
            <ArchiveRestore className="size-4" /> Wiederherstellen …
          </Knopf>
          <Rueckmeldung meldung={wiederherstellen.meldung?.ok ? wiederherstellen.meldung : null} />
        </div>
      </div>
      <Dialog offen={dialog} setOffen={setDialog} titel="Datenverzeichnis ersetzen?" beschreibung={`${datei?.name ?? ""} ersetzt den gesamten Spielstand. Der aktuelle Stand wird vorher automatisch gesichert. Nicht während einer Session.`}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            wiederherstellen.mutate();
          }}
          className="space-y-4"
        >
          <Feld id="r-pw" label="Eigenes Passwort zur Bestätigung">
            <Eingabe id="r-pw" type="password" autoComplete="current-password" value={kontoPw} onChange={(e) => setKontoPw(e.target.value)} autoFocus />
          </Feld>
          <Rueckmeldung meldung={wiederherstellen.meldung?.ok === false ? wiederherstellen.meldung : null} />
          <div className="flex justify-end gap-2">
            <Knopf type="button" variante="geist" onClick={() => setDialog(false)}>
              Abbrechen
            </Knopf>
            <Knopf type="submit" variante="gefahr" laedt={wiederherstellen.isPending} disabled={!kontoPw}>
              Ersetzen
            </Knopf>
          </div>
        </form>
      </Dialog>
    </Bereich>
  );
}

// --------------------------------------------------------------------------
// 7 Systemstatus

const BANNER: Record<Ampel["stufe"], { rahmen: string; titel: string; text: string }> = {
  gruen: { rahmen: "border-gut/30 bg-gut-flaeche", titel: "text-gut", text: "Alles in Ordnung" },
  gelb: { rahmen: "border-warnung/30 bg-warnung-flaeche", titel: "text-warnung", text: "Es gibt Hinweise" },
  rot: { rahmen: "border-schlecht/30 bg-schlecht-flaeche", titel: "text-schlecht", text: "Handlungsbedarf" },
};

const ZEILE: Record<Ampel["stufe"], string> = {
  gruen: "border-l-transparent",
  gelb: "border-l-warnung bg-warnung-flaeche",
  rot: "border-l-schlecht bg-schlecht-flaeche",
};

/** „1 Problem: Hintergrunddienst · 2 Hinweise: Kursabruf, News“ – wer das Banner liest, weiß, wohin er schauen muss. */
function betroffene(liste: Ampel[]): string {
  const nenne = (stufe: Ampel["stufe"], eins: string, viele: string) => {
    const treffer = liste.filter((s) => s.stufe === stufe);
    return treffer.length ? `${treffer.length} ${treffer.length === 1 ? eins : viele}: ${treffer.map((s) => s.titel).join(", ")}` : null;
  };
  return [nenne("rot", "Problem", "Probleme"), nenne("gelb", "Hinweis", "Hinweise")].filter(Boolean).join(" · ");
}

export function SystemBereich({ d }: { d: EinrichtungDaten }) {
  const reihenfolge = useMemo(() => ["daten", "git", "kurse", "news", "beobachtung", "nachbuchung", "claude", "worker"], []);
  const liste = [...d.systemstatus].sort((a, b) => reihenfolge.indexOf(a.id) - reihenfolge.indexOf(b.id));
  const gesamt = gesamtstufe(liste);
  const banner = BANNER[gesamt];
  return (
    <Bereich
      id="system"
      titel="Systemstatus"
      icon={<Activity className="size-4" />}
      untertitel="Aktualisiert sich alle 30 Sekunden. Grün: in Ordnung · Gelb: Hinweis · Rot: Handlungsbedarf."
      status={gesamt === "gruen" ? <Abzeichen ton="gut">in Ordnung</Abzeichen> : <Abzeichen ton={gesamt === "gelb" ? "warnung" : "schlecht"} icon={<AlertTriangle className="size-3" />}>{STUFE_TEXT[gesamt]}</Abzeichen>}
    >
      <div role="status" data-stufe={gesamt} className={cn("flex items-start gap-3 rounded-xl border px-4 py-3", banner.rahmen)}>
        <span className="mt-1.5">
          <Punkt stufe={gesamt} />
        </span>
        <div className="min-w-0">
          <div className={cn("text-[13.5px] font-semibold", banner.titel)}>Gesamtstatus: {banner.text}</div>
          {gesamt !== "gruen" && <div className="text-[12.5px] text-text-2">{betroffene(liste)}</div>}
        </div>
      </div>
      <ul className="divide-y divide-rand overflow-hidden rounded-xl border border-rand">
        {liste.map((s) => {
          const ziel = s.stufe !== "gruen" ? BEREICHE.find((b) => `#${b.id}` === s.link) : undefined;
          return (
            <li key={s.id} data-stufe={s.stufe} className={cn("flex items-start gap-3 border-l-[3px] px-4 py-3", ZEILE[s.stufe])}>
              <span className="mt-1.5">
                <Punkt stufe={s.stufe} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[13.5px] font-medium text-text">{s.titel}</span>
                  {s.stufe !== "gruen" && (
                    <Abzeichen ton={s.stufe === "gelb" ? "warnung" : "schlecht"} icon={<AlertTriangle className="size-3" />}>
                      {STUFE_TEXT[s.stufe]}
                    </Abzeichen>
                  )}
                </div>
                <div className={cn("text-[12.5px]", s.stufe === "gruen" ? "text-text-3" : "text-text-2")}>{s.text}</div>
                {s.details.length > 0 && (
                  <ul className="mt-2 space-y-1.5" aria-label={`Einzelheiten zu ${s.titel}`}>
                    {s.details.map((detail, i) => (
                      <FehlerDetail key={`${detail.titel}-${i}`} detail={detail} />
                    ))}
                  </ul>
                )}
                {ziel && (
                  <a href={s.link ?? undefined} className="mt-1.5 inline-block text-[12.5px] font-medium text-akzent hover:underline">
                    Zum Bereich „{ziel.titel}“
                  </a>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      <KarteKopf
        titel="Verzeichnisse im Volume"
        untertitel={
          <>
            Spielstand <Mono>{d.pfade.daten}</Mono> (lokales Git ohne Remote) · App-Konfiguration und Secrets <Mono>{d.pfade.app}</Mono>
          </>
        }
      />
    </Bereich>
  );
}
