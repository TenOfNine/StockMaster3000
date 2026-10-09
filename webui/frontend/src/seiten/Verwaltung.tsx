import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, KeyRound, LogOut, Monitor, MoreHorizontal, ShieldCheck, ShieldOff, UserPlus } from "lucide-react";
import { useState } from "react";

import {
  Abzeichen,
  Dialog,
  Eingabe,
  Feld,
  Fehleranzeige,
  Karte,
  KarteKopf,
  Knopf,
  Leer,
  Mono,
  Reiter,
  ReiterInhalt,
  ReiterKnopf,
  ReiterLeiste,
  Seitenkopf,
  Skelett,
} from "@/components/ui";
import { api, ApiFehler, type AdminBenutzer } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { datum, relativ, zeit } from "@/lib/format";

import { PasswortFormular, ZweiFaktorEinrichten } from "./Anmeldung";

// --------------------------------------------------------------------------
// Konto

export function Konto() {
  const { sitzung } = useAuth();
  const client = useQueryClient();
  const benutzer = sitzung?.benutzer;
  const sitzungen = useQuery({
    queryKey: ["sitzungen"],
    queryFn: () => api<{ erstellt: string; zuletzt_aktiv: string; user_agent: string; aktuell: boolean }[]>("/api/auth/sitzungen"),
  });
  const [gespeichert, setGespeichert] = useState<string | null>(null);
  const [deaktivieren, setDeaktivieren] = useState(false);
  const alleAbmelden = useMutation({
    mutationFn: () => api("/api/auth/logout-alle", { methode: "POST" }),
    onSuccess: () => {
      client.clear();
      client.setQueryData(["me"], null);
    },
  });

  return (
    <div className="einblenden">
      <Seitenkopf titel="Konto & Sicherheit" untertitel="Anmeldedaten, Zwei-Faktor (nur zum Anlegen neuer Benutzer) und aktive Sitzungen." />
      <div className="grid gap-4 xl:grid-cols-2">
        <Karte>
          <KarteKopf titel="Profil" />
          <dl className="divide-y divide-rand px-5 pb-3 text-[13px]">
            {[
              ["Anzeigename", benutzer?.anzeigename],
              ["E-Mail", benutzer?.email],
              ["Kennung im Repository", <Mono key="k">{benutzer?.kennung}</Mono>],
              ["Rolle", benutzer?.ist_admin ? <Abzeichen key="r" ton="akzent">Administrator</Abzeichen> : "Benutzer"],
            ].map(([l, w]) => (
              <div key={String(l)} className="flex items-center justify-between gap-4 py-2.5">
                <dt className="text-text-3">{l}</dt>
                <dd className="text-text">{w}</dd>
              </div>
            ))}
          </dl>
          <p className="px-5 pb-5 text-[12px] text-text-3">
            Im Spiel-Repository erscheinen Personen nur als neutrale Kennung; Name und E-Mail bleiben in der Datenbank der Web-UI.
          </p>
        </Karte>
        <Karte>
          <KarteKopf
            titel="Zwei-Faktor-Anmeldung"
            aktion={benutzer?.totp_aktiv ? <Abzeichen ton="gut" icon={<ShieldCheck className="size-3" />}>aktiv</Abzeichen> : <Abzeichen ton="warnung">nicht aktiv</Abzeichen>}
          />
          <div className="px-5 pb-5">
            {benutzer?.totp_aktiv ? (
              <div className="space-y-3 text-[13px] text-text-2">
                <p>
                  {benutzer.ist_admin
                    ? "Die Anmeldung braucht nur dein Passwort. Den Code aus deiner Authenticator-App fragt die Web-UI nur ab, wenn du einen neuen Benutzer anlegst."
                    : "Die Anmeldung braucht nur dein Passwort; der Code wird nur für das Anlegen neuer Benutzer durch Administratoren gebraucht."}
                </p>
                <Knopf klein onClick={() => setDeaktivieren(true)}>
                  <ShieldOff className="size-3.5" /> Deaktivieren
                </Knopf>
              </div>
            ) : benutzer?.ist_admin ? (
              <div className="space-y-3">
                <p className="text-[13px] text-text-2">Zwei-Faktor brauchst du nur, um neue Benutzer anzulegen. Die Anmeldung läuft ohne Code.</p>
                <ZweiFaktorEinrichten eingebettet fertig={() => setGespeichert("Zwei-Faktor ist jetzt aktiv.")} />
              </div>
            ) : (
              <p className="text-[13px] text-text-2">Für dein Konto ist kein Zwei-Faktor nötig. Er wird nur gebraucht, wenn ein Administrator neue Benutzer anlegt.</p>
            )}
          </div>
        </Karte>
        <Karte>
          <KarteKopf titel="Passwort ändern" icon={<KeyRound className="size-4" />} untertitel="Andere Sitzungen werden dabei abgemeldet." />
          <div className="px-5 pb-5">
            {gespeichert && <p className="mb-3 rounded-lg bg-gut-flaeche px-3 py-2 text-[13px] text-gut">{gespeichert}</p>}
            <PasswortFormular eingebettet fertig={() => setGespeichert("Passwort geändert.")} />
          </div>
        </Karte>
        <Karte>
          <KarteKopf
            titel="Aktive Sitzungen"
            icon={<Monitor className="size-4" />}
            untertitel="Leerlauf 30 Minuten, höchstens 12 Stunden"
            aktion={
              <Knopf klein variante="geist" onClick={() => alleAbmelden.mutate()} laedt={alleAbmelden.isPending}>
                <LogOut className="size-3.5" /> Überall abmelden
              </Knopf>
            }
          />
          <ul className="divide-y divide-rand px-5 pb-3">
            {sitzungen.data?.map((s, i) => (
              <li key={i} className="flex items-center justify-between gap-3 py-2.5 text-[13px]">
                <div className="min-w-0">
                  <div className="truncate text-text">{kurzerAgent(s.user_agent)}</div>
                  <div className="text-[12px] text-text-3">
                    angemeldet {zeit(s.erstellt)} · aktiv {relativ(s.zuletzt_aktiv)}
                  </div>
                </div>
                {s.aktuell && <Abzeichen ton="akzent">diese Sitzung</Abzeichen>}
              </li>
            ))}
          </ul>
        </Karte>
      </div>
      <TotpDeaktivieren offen={deaktivieren} setOffen={setDeaktivieren} />
    </div>
  );
}

function kurzerAgent(agent: string): string {
  if (!agent) return "Unbekanntes Gerät";
  const browser = /(Firefox|Edg|Chrome|Safari)\/[\d.]+/.exec(agent)?.[1]?.replace("Edg", "Edge") ?? "Browser";
  const system = /(Windows|Mac OS X|Android|iPhone|iPad|Linux)/.exec(agent)?.[1]?.replace("Mac OS X", "macOS") ?? "";
  return `${browser}${system ? ` auf ${system}` : ""}`;
}

function TotpDeaktivieren({ offen, setOffen }: { offen: boolean; setOffen: (o: boolean) => void }) {
  const client = useQueryClient();
  const [passwort, setPasswort] = useState("");
  const [code, setCode] = useState("");
  const aktion = useMutation({
    mutationFn: () => api("/api/auth/totp/deaktivieren", { daten: { passwort, code } }),
    onSuccess: () => {
      setOffen(false);
      void client.invalidateQueries({ queryKey: ["me"] });
    },
  });
  return (
    <Dialog offen={offen} setOffen={setOffen} titel="Zwei-Faktor deaktivieren" beschreibung="Zur Bestätigung Passwort und aktuellen Code eingeben.">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          aktion.mutate();
        }}
      >
        {aktion.isError && <p className="text-[13px] text-schlecht">{(aktion.error as Error).message}</p>}
        <Feld id="d-pw" label="Passwort">
          <Eingabe id="d-pw" type="password" value={passwort} onChange={(e) => setPasswort(e.target.value)} autoComplete="current-password" />
        </Feld>
        <Feld id="d-code" label="Code">
          <Eingabe id="d-code" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
        </Feld>
        <Knopf type="submit" variante="gefahr" laedt={aktion.isPending}>
          Deaktivieren
        </Knopf>
      </form>
    </Dialog>
  );
}

// --------------------------------------------------------------------------
// Administration

type AdminAktion =
  | { art: "anlegen" }
  | { art: "passwort"; b: AdminBenutzer }
  | { art: "zwei-faktor"; b: AdminBenutzer }
  | { art: "aktiv"; b: AdminBenutzer; aktiv: boolean }
  | { art: "admin"; b: AdminBenutzer; ist_admin: boolean };

export function Administration() {
  const benutzer = useQuery({ queryKey: ["admin", "benutzer"], queryFn: () => api<AdminBenutzer[]>("/api/admin/benutzer") });
  const audit = useQuery({ queryKey: ["admin", "audit"], queryFn: () => api<{ zeit: string; akteur: string | null; aktion: string; ziel: string | null }[]>("/api/admin/audit?anzahl=200") });
  const system = useQuery({ queryKey: ["admin", "system"], queryFn: () => api<{ benutzer: number; aktive_sitzungen: number; repository: { pfad_name: string; commit: string; branch: string; demo: boolean } }>("/api/admin/system") });
  const [aktion, setAktion] = useState<AdminAktion | null>(null);
  const namen = new Map((benutzer.data ?? []).map((b) => [b.id, b.anzeigename]));

  return (
    <div className="einblenden">
      <Seitenkopf
        titel="Administration"
        untertitel="Benutzer anlegen und verwalten. Kritische Aktionen verlangen die erneute Eingabe deines Passworts und landen im Audit-Log."
        aktionen={
          <Knopf variante="primaer" onClick={() => setAktion({ art: "anlegen" })}>
            <UserPlus className="size-4" /> Benutzer anlegen
          </Knopf>
        }
      />
      {system.data && (
        <div className="mb-4 grid gap-4 sm:grid-cols-3">
          {[
            ["Benutzer", String(system.data.benutzer)],
            ["Aktive Sitzungen", String(system.data.aktive_sitzungen)],
            ["Repository", `${system.data.repository.pfad_name} · ${system.data.repository.branch ?? "–"} · ${system.data.repository.commit ?? "–"}`],
          ].map(([l, w]) => (
            <Karte key={l} className="p-5">
              <div className="text-[12.5px] text-text-3">{l}</div>
              <div className="zahl mt-1 truncate text-[18px] font-semibold text-text">{w}</div>
            </Karte>
          ))}
        </div>
      )}
      <Reiter defaultValue="benutzer">
        <ReiterLeiste>
          <ReiterKnopf value="benutzer">Benutzer</ReiterKnopf>
          <ReiterKnopf value="audit">Audit-Log</ReiterKnopf>
        </ReiterLeiste>
        <ReiterInhalt value="benutzer">
          {benutzer.isError ? (
            <Fehleranzeige fehler={benutzer.error} />
          ) : !benutzer.data ? (
            <Skelett className="h-60 rounded-2xl" />
          ) : (
            <Karte className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="border-b border-rand text-left text-[12px] text-text-3">
                      <th className="px-5 py-2.5 font-medium">Benutzer</th>
                      <th className="px-5 py-2.5 font-medium">Kennung</th>
                      <th className="px-5 py-2.5 font-medium">Status</th>
                      <th className="px-5 py-2.5 font-medium">Angelegt</th>
                      <th className="px-5 py-2.5" />
                    </tr>
                  </thead>
                  <tbody>
                    {benutzer.data.map((b) => (
                      <tr key={b.id} className="border-b border-rand/70 last:border-0">
                        <td className="px-5 py-3">
                          <div className="font-medium text-text">{b.anzeigename}</div>
                          <div className="text-[12px] text-text-3">{b.email}</div>
                        </td>
                        <td className="px-5 py-3">
                          <Mono className="text-text-2">{b.kennung}</Mono>
                        </td>
                        <td className="px-5 py-3">
                          <div className="flex flex-wrap gap-1">
                            {b.ist_admin && <Abzeichen ton="akzent">Admin</Abzeichen>}
                            {!b.aktiv && <Abzeichen ton="schlecht">gesperrt</Abzeichen>}
                            {b.totp_aktiv ? <Abzeichen ton="gut">2FA</Abzeichen> : <Abzeichen>ohne 2FA</Abzeichen>}
                            {b.passwortwechsel_noetig && <Abzeichen ton="warnung">Erstanmeldung offen</Abzeichen>}
                          </div>
                        </td>
                        <td className="px-5 py-3 text-text-3">{datum(b.erstellt)}</td>
                        <td className="px-5 py-3 text-right">
                          <DropdownMenu.Root>
                            <DropdownMenu.Trigger className="rounded-md p-1.5 text-text-3 hover:bg-flaeche-3 hover:text-text" aria-label={`Aktionen für ${b.anzeigename}`}>
                              <MoreHorizontal className="size-4" />
                            </DropdownMenu.Trigger>
                            <DropdownMenu.Portal>
                              <DropdownMenu.Content align="end" className="z-50 min-w-[220px] rounded-xl border border-rand bg-flaeche p-1.5 shadow-2xl">
                                {[
                                  { text: "Passwort zurücksetzen", a: { art: "passwort", b } as AdminAktion },
                                  { text: "Zwei-Faktor zurücksetzen", a: { art: "zwei-faktor", b } as AdminAktion },
                                  { text: b.aktiv ? "Sperren" : "Entsperren", a: { art: "aktiv", b, aktiv: !b.aktiv } as AdminAktion },
                                  { text: b.ist_admin ? "Admin-Rolle entziehen" : "Admin-Rolle vergeben", a: { art: "admin", b, ist_admin: !b.ist_admin } as AdminAktion },
                                ].map((m) => (
                                  <DropdownMenu.Item
                                    key={m.text}
                                    onSelect={() => setAktion(m.a)}
                                    className="cursor-pointer rounded-lg px-2.5 py-2 text-[13px] text-text-2 outline-none data-[highlighted]:bg-flaeche-3 data-[highlighted]:text-text"
                                  >
                                    {m.text}
                                  </DropdownMenu.Item>
                                ))}
                              </DropdownMenu.Content>
                            </DropdownMenu.Portal>
                          </DropdownMenu.Root>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Karte>
          )}
        </ReiterInhalt>
        <ReiterInhalt value="audit">
          <Karte className="overflow-hidden">
            {!audit.data?.length ? (
              <Leer titel="Keine Einträge" />
            ) : (
              <ul className="divide-y divide-rand">
                {audit.data.map((a, i) => (
                  <li key={i} className="flex flex-wrap items-center justify-between gap-2 px-5 py-2.5 text-[13px]">
                    <span className="text-text">
                      <span className="font-medium">{a.aktion.replaceAll("_", " ")}</span>
                      <span className="text-text-3">
                        {" "}· {a.akteur ? (namen.get(a.akteur) ?? "Benutzer") : "System"}
                        {a.ziel && a.ziel !== a.akteur && ` → ${namen.get(a.ziel) ?? a.ziel}`}
                      </span>
                    </span>
                    <span className="text-[12px] text-text-3">{zeit(a.zeit)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Karte>
        </ReiterInhalt>
      </Reiter>
      {aktion && <AdminDialog aktion={aktion} schliessen={() => setAktion(null)} />}
    </div>
  );
}

function AdminDialog({ aktion, schliessen }: { aktion: AdminAktion; schliessen: () => void }) {
  const client = useQueryClient();
  const { sitzung } = useAuth();
  const [passwort, setPasswort] = useState("");
  const [email, setEmail] = useState("");
  const [anzeigename, setAnzeigename] = useState("");
  const [code, setCode] = useState("");
  const [einmal, setEinmal] = useState<string | null>(null);
  const [kopiert, setKopiert] = useState(false);

  const titel = {
    anlegen: "Benutzer anlegen",
    passwort: "Passwort zurücksetzen",
    "zwei-faktor": "Zwei-Faktor zurücksetzen",
    aktiv: "aktiv" in aktion && aktion.aktiv ? "Benutzer entsperren" : "Benutzer sperren",
    admin: "ist_admin" in aktion && aktion.ist_admin ? "Admin-Rolle vergeben" : "Admin-Rolle entziehen",
  }[aktion.art];

  const ausfuehren = useMutation({
    mutationFn: async () => {
      if (aktion.art === "anlegen") return api<{ einmalpasswort: string }>("/api/admin/benutzer", { daten: { email, anzeigename, passwort, code } });
      const basis = `/api/admin/benutzer/${aktion.b.id}`;
      if (aktion.art === "passwort") return api<{ einmalpasswort: string }>(`${basis}/passwort-zuruecksetzen`, { daten: { passwort } });
      if (aktion.art === "zwei-faktor") return api(`${basis}/zwei-faktor-zuruecksetzen`, { daten: { passwort } });
      if (aktion.art === "aktiv") return api(`${basis}/aktiv`, { daten: { passwort, aktiv: aktion.aktiv } });
      return api(`${basis}/admin`, { daten: { passwort, ist_admin: aktion.ist_admin } });
    },
    onSuccess: (antwort: any) => {
      void client.invalidateQueries({ queryKey: ["admin"] });
      if (antwort?.einmalpasswort) setEinmal(antwort.einmalpasswort);
      else schliessen();
    },
  });

  return (
    <Dialog offen setOffen={(o) => !o && schliessen()} titel={titel} beschreibung={"b" in aktion ? `${aktion.b.anzeigename} · ${aktion.b.email}` : "Der neue Benutzer erhält ein Einmalpasswort und muss es bei der ersten Anmeldung ändern."}>
      {einmal ? (
        <div className="space-y-4">
          <p className="text-[13px] text-text-2">Einmalpasswort – wird nur jetzt angezeigt. Bitte sicher weitergeben.</p>
          <div className="flex items-center gap-2 rounded-lg border border-rand bg-flaeche-2 p-3">
            <code className="flex-1 font-mono text-[15px] tracking-wide text-text select-all">{einmal}</code>
            <Knopf
              klein
              onClick={() => {
                void navigator.clipboard?.writeText(einmal);
                setKopiert(true);
              }}
            >
              {kopiert ? <Check className="size-3.5" /> : <Copy className="size-3.5" />} {kopiert ? "Kopiert" : "Kopieren"}
            </Knopf>
          </div>
          <Knopf variante="primaer" onClick={schliessen}>
            Fertig
          </Knopf>
        </div>
      ) : (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            ausfuehren.mutate();
          }}
        >
          {ausfuehren.isError && <p className="rounded-lg bg-schlecht-flaeche px-3 py-2 text-[13px] text-schlecht">{ausfuehren.error instanceof ApiFehler ? ausfuehren.error.message : "Fehlgeschlagen"}</p>}
          {aktion.art === "anlegen" && (
            <>
              <Feld id="n-email" label="E-Mail">
                <Eingabe id="n-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
              </Feld>
              <Feld id="n-name" label="Anzeigename" hinweis="Erscheint nur in der Web-UI, nie im Spiel-Repository.">
                <Eingabe id="n-name" required maxLength={80} value={anzeigename} onChange={(e) => setAnzeigename(e.target.value)} />
              </Feld>
              {sitzung?.benutzer?.totp_aktiv ? (
                <Feld id="n-code" label="Zwei-Faktor-Code" hinweis="Sechsstelliger Code aus deiner Authenticator-App; nur zum Anlegen neuer Benutzer nötig.">
                  <Eingabe id="n-code" inputMode="numeric" autoComplete="one-time-code" required maxLength={7} pattern="[0-9 ]{6,7}" value={code} onChange={(e) => setCode(e.target.value.replace(/[^\d ]/g, ""))} />
                </Feld>
              ) : (
                <div className="space-y-3 rounded-xl border border-rand bg-flaeche-2/50 p-3.5">
                  <p className="text-[13px] text-text">Zum Anlegen neuer Benutzer brauchst du Zwei-Faktor. Richte ihn jetzt ein; danach trägst du hier den Code ein.</p>
                  <ZweiFaktorEinrichten eingebettet />
                </div>
              )}
            </>
          )}
          <Feld id="b-pw" label="Dein Passwort zur Bestätigung">
            <Eingabe id="b-pw" type="password" required value={passwort} onChange={(e) => setPasswort(e.target.value)} autoComplete="current-password" />
          </Feld>
          <div className="flex justify-end gap-2">
            <Knopf type="button" variante="geist" onClick={schliessen}>
              Abbrechen
            </Knopf>
            <Knopf type="submit" variante={aktion.art === "aktiv" && !aktion.aktiv ? "gefahr" : "primaer"} laedt={ausfuehren.isPending} disabled={aktion.art === "anlegen" && !sitzung?.benutzer?.totp_aktiv}>
              {titel}
            </Knopf>
          </div>
        </form>
      )}
    </Dialog>
  );
}
