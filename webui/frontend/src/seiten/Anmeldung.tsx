import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound, LockKeyhole, ShieldCheck, Smartphone } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Eingabe, Feld, Knopf, PROFIL_FARBE } from "@/components/ui";
import { api, ApiFehler, PROFILE, type SitzungAntwort } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function fehlertext(fehler: unknown): string {
  return fehler instanceof ApiFehler ? fehler.message : "Verbindung fehlgeschlagen.";
}

export function Anmeldung() {
  const { sitzung } = useAuth();
  const schritt = sitzung?.naechster_schritt;
  return (
    <div className="grid min-h-full lg:grid-cols-[1.05fr_1fr]">
      <Markenflaeche />
      <main className="flex items-center justify-center px-5 py-12 sm:px-10">
        <div className="einblenden w-full max-w-[400px]">
          {!sitzung && <LoginFormular />}
          {schritt === "totp" && <TotpFormular />}
          {schritt === "passwort_aendern" && <PasswortFormular />}
          {schritt === "zwei_faktor_einrichten" && <ZweiFaktorEinrichten />}
          <p className="mt-10 text-center text-[12px] text-text-3">
            Nur im Heimnetz erreichbar · Simulation mit Spielgeld, keine Anlageberatung
          </p>
        </div>
      </main>
    </div>
  );
}

function Markenflaeche() {
  return (
    <aside className="relative hidden overflow-hidden border-r border-rand bg-flaeche lg:flex lg:flex-col lg:gap-14 lg:p-12">
      <div className="hintergrund-raster absolute inset-0 opacity-70" aria-hidden />
      <div className="glanz absolute inset-0" aria-hidden />
      <svg className="absolute right-0 bottom-0 left-0 h-[45%] w-full opacity-90" viewBox="0 0 600 300" preserveAspectRatio="none" aria-hidden>
        <defs>
          {PROFILE.map((p) => (
            <linearGradient key={p} id={`verlauf-${p}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={PROFIL_FARBE[p]} stopOpacity="0.22" />
              <stop offset="100%" stopColor={PROFIL_FARBE[p]} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>
        <path d="M0 230 C 80 220, 120 200, 180 205 S 300 170, 360 160 S 480 120, 600 110 L600 300 L0 300 Z" fill="url(#verlauf-aggressiv)" />
        <path d="M0 230 C 80 220, 120 200, 180 205 S 300 170, 360 160 S 480 120, 600 110" fill="none" stroke={PROFIL_FARBE.aggressiv} strokeWidth="2" />
        <path d="M0 240 C 90 236, 150 222, 210 220 S 330 205, 400 196 S 520 178, 600 170" fill="none" stroke={PROFIL_FARBE.ausgewogen} strokeWidth="2" />
        <path d="M0 250 C 100 248, 170 242, 240 240 S 360 232, 430 228 S 540 220, 600 216" fill="none" stroke={PROFIL_FARBE.defensiv} strokeWidth="2" />
      </svg>
      <div className="relative flex items-center gap-3">
        <img src="/favicon.svg" alt="" className="size-10 rounded-xl shadow-lg" />
        <div>
          <div className="text-[15px] font-semibold tracking-[-0.01em] text-text">StockMaster 3000</div>
          <div className="text-[12.5px] text-text-3">Claude-Börsenexperiment</div>
        </div>
      </div>
      <div className="relative max-w-md">
        <h2 className="text-[30px] leading-tight font-semibold tracking-[-0.025em] text-text">
          Drei Portfolios. Jede Entscheidung begründet, jede Buchung nachrechenbar.
        </h2>
        <p className="mt-4 text-[14.5px] leading-relaxed text-text-2">
          Rechnen macht Code, Entscheiden macht Claude. Hier verfolgt ihr Kennzahlen, Trade-Akten und das Reasoning hinter
          jeder Abwägung – auch hinter begründetem Nichtstun.
        </p>
        <div className="mt-6 flex gap-2">
          {PROFILE.map((p) => (
            <span key={p} className="inline-flex items-center gap-2 rounded-full border border-rand bg-flaeche-2/80 px-3 py-1 text-[12.5px] text-text-2 backdrop-blur">
              <span className="size-2 rounded-full" style={{ background: PROFIL_FARBE[p] }} />
              {p.charAt(0).toUpperCase() + p.slice(1)}
            </span>
          ))}
        </div>
      </div>
    </aside>
  );
}

function Kopf({ icon, titel, text }: { icon: React.ReactNode; titel: string; text: string }) {
  return (
    <div className="mb-7">
      <div className="mb-5 flex items-center gap-3 lg:hidden">
        <img src="/favicon.svg" alt="" className="size-9 rounded-xl" />
        <span className="text-[15px] font-semibold text-text">StockMaster 3000</span>
      </div>
      <div className="mb-4 grid size-11 place-items-center rounded-xl border border-rand bg-flaeche-2 text-text-2">{icon}</div>
      <h1 className="text-[22px] font-semibold tracking-[-0.02em] text-text">{titel}</h1>
      <p className="mt-1.5 text-[13.5px] text-text-2">{text}</p>
    </div>
  );
}

function Fehlerzeile({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <div role="alert" className="rounded-lg border border-schlecht/30 bg-schlecht-flaeche px-3 py-2 text-[13px] text-schlecht">
      {text}
    </div>
  );
}

const loginSchema = z.object({
  email: z.string().trim().min(3, "Bitte E-Mail-Adresse eingeben.").max(254),
  passwort: z.string().min(1, "Bitte Passwort eingeben.").max(200),
});

function LoginFormular() {
  const { setzen } = useAuth();
  const [fehler, setFehler] = useState<string | null>(null);
  const form = useForm<z.infer<typeof loginSchema>>({ resolver: zodResolver(loginSchema), defaultValues: { email: "", passwort: "" } });
  const senden = form.handleSubmit(async (daten) => {
    setFehler(null);
    try {
      setzen(await api<SitzungAntwort>("/api/auth/login", { daten }));
    } catch (e) {
      setFehler(fehlertext(e));
    }
  });
  return (
    <form onSubmit={senden} className="space-y-4" noValidate>
      <Kopf icon={<LockKeyhole className="size-5" />} titel="Anmelden" text="Mit dem Konto, das ein Administrator für dich angelegt hat." />
      <Fehlerzeile text={fehler} />
      <Feld id="email" label="E-Mail" fehler={form.formState.errors.email?.message}>
        <Eingabe id="email" type="email" autoComplete="username" autoFocus {...form.register("email")} />
      </Feld>
      <Feld id="passwort" label="Passwort" fehler={form.formState.errors.passwort?.message}>
        <Eingabe id="passwort" type="password" autoComplete="current-password" {...form.register("passwort")} />
      </Feld>
      <Knopf type="submit" variante="primaer" className="w-full" laedt={form.formState.isSubmitting}>
        Anmelden
      </Knopf>
    </form>
  );
}

function CodeEingabe(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <Eingabe
      inputMode="numeric"
      autoComplete="one-time-code"
      maxLength={6}
      placeholder="000000"
      className="h-12 text-center font-mono text-[20px] tracking-[0.5em]"
      {...props}
    />
  );
}

function TotpFormular() {
  const { setzen, abmelden } = useAuth();
  const [code, setCode] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [laedt, setLaedt] = useState(false);
  const senden = async (e: React.FormEvent) => {
    e.preventDefault();
    setLaedt(true);
    setFehler(null);
    try {
      setzen(await api<SitzungAntwort>("/api/auth/totp", { daten: { code } }));
    } catch (err) {
      setFehler(fehlertext(err));
      setCode("");
    } finally {
      setLaedt(false);
    }
  };
  return (
    <form onSubmit={senden} className="space-y-4">
      <Kopf icon={<Smartphone className="size-5" />} titel="Zwei-Faktor-Code" text="Gib den sechsstelligen Code aus deiner Authenticator-App ein." />
      <Fehlerzeile text={fehler} />
      <Feld id="code" label="Code">
        <CodeEingabe id="code" autoFocus value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
      </Feld>
      <Knopf type="submit" variante="primaer" className="w-full" laedt={laedt} disabled={code.length !== 6}>
        Bestätigen
      </Knopf>
      <Knopf type="button" variante="geist" className="w-full" onClick={() => void abmelden()}>
        Abbrechen
      </Knopf>
    </form>
  );
}

const passwortSchema = z
  .object({
    alt: z.string().min(1, "Bitte das bisherige Passwort eingeben."),
    neu: z.string().min(12, "Mindestens 12 Zeichen.").max(200),
    wiederholung: z.string(),
  })
  .refine((d) => d.neu === d.wiederholung, { message: "Die Passwörter stimmen nicht überein.", path: ["wiederholung"] });

export function PasswortFormular({ eingebettet, fertig }: { eingebettet?: boolean; fertig?: () => void }) {
  const { setzen } = useAuth();
  const [fehler, setFehler] = useState<string | null>(null);
  const form = useForm<z.infer<typeof passwortSchema>>({ resolver: zodResolver(passwortSchema), defaultValues: { alt: "", neu: "", wiederholung: "" } });
  const senden = form.handleSubmit(async ({ alt, neu }) => {
    setFehler(null);
    try {
      setzen(await api<SitzungAntwort>("/api/auth/passwort", { daten: { alt, neu } }));
      form.reset();
      fertig?.();
    } catch (e) {
      setFehler(fehlertext(e));
    }
  });
  return (
    <form onSubmit={senden} className="space-y-4" noValidate>
      {!eingebettet && (
        <Kopf icon={<KeyRound className="size-5" />} titel="Neues Passwort festlegen" text="Bei der ersten Anmeldung ersetzt du das Einmalpasswort durch ein eigenes." />
      )}
      <Fehlerzeile text={fehler} />
      <Feld id="alt" label={eingebettet ? "Bisheriges Passwort" : "Einmalpasswort"} fehler={form.formState.errors.alt?.message}>
        <Eingabe id="alt" type="password" autoComplete="current-password" {...form.register("alt")} />
      </Feld>
      <Feld id="neu" label="Neues Passwort" hinweis="Mindestens 12 Zeichen; ein Satz aus mehreren Wörtern ist ideal." fehler={form.formState.errors.neu?.message}>
        <Eingabe id="neu" type="password" autoComplete="new-password" {...form.register("neu")} />
      </Feld>
      <Feld id="wiederholung" label="Neues Passwort wiederholen" fehler={form.formState.errors.wiederholung?.message}>
        <Eingabe id="wiederholung" type="password" autoComplete="new-password" {...form.register("wiederholung")} />
      </Feld>
      <Knopf type="submit" variante="primaer" className={eingebettet ? "" : "w-full"} laedt={form.formState.isSubmitting}>
        Passwort speichern
      </Knopf>
    </form>
  );
}

export function ZweiFaktorEinrichten({ eingebettet, fertig }: { eingebettet?: boolean; fertig?: () => void }) {
  const { setzen } = useAuth();
  const [daten, setDaten] = useState<{ uri: string; geheimnis: string } | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [laedt, setLaedt] = useState(false);

  useEffect(() => {
    if (!daten) return;
    void QRCode.toDataURL(daten.uri, { margin: 1, width: 220, color: { dark: "#0b0f14", light: "#ffffff" } }).then(setQr);
  }, [daten]);

  const starten = async () => {
    setLaedt(true);
    setFehler(null);
    try {
      setDaten(await api("/api/auth/totp/einrichten", { methode: "POST" }));
    } catch (e) {
      setFehler(fehlertext(e));
    } finally {
      setLaedt(false);
    }
  };
  const bestaetigen = async (e: React.FormEvent) => {
    e.preventDefault();
    setLaedt(true);
    setFehler(null);
    try {
      setzen(await api<SitzungAntwort>("/api/auth/totp/aktivieren", { daten: { code } }));
      fertig?.();
    } catch (err) {
      setFehler(fehlertext(err));
    } finally {
      setLaedt(false);
    }
  };

  return (
    <div className="space-y-4">
      {!eingebettet && (
        <Kopf
          icon={<ShieldCheck className="size-5" />}
          titel="Zwei-Faktor einrichten"
          text="Für Administratoren Pflicht. Du brauchst eine Authenticator-App (z. B. Aegis, 2FAS, Google Authenticator)."
        />
      )}
      <Fehlerzeile text={fehler} />
      {!daten ? (
        <Knopf variante="primaer" className={eingebettet ? "" : "w-full"} onClick={starten} laedt={laedt}>
          Einrichtung starten
        </Knopf>
      ) : (
        <form onSubmit={bestaetigen} className="space-y-4">
          <div className="flex flex-col items-center gap-3 rounded-xl border border-rand bg-flaeche-2 p-4 sm:flex-row sm:items-start">
            {qr ? <img src={qr} alt="QR-Code für die Authenticator-App" className="size-[148px] rounded-lg bg-white p-1" /> : <div className="skelett size-[148px] rounded-lg" />}
            <div className="min-w-0 text-[13px] text-text-2">
              <p>1. QR-Code mit der App scannen.</p>
              <p className="mt-2">Oder Schlüssel manuell eingeben:</p>
              <code className="mt-1 block font-mono text-[12px] break-all text-text select-all">{daten.geheimnis.match(/.{1,4}/g)?.join(" ")}</code>
              <p className="mt-2">2. Den angezeigten Code unten bestätigen.</p>
            </div>
          </div>
          <Feld id="neuer-code" label="Code aus der App">
            <CodeEingabe id="neuer-code" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
          </Feld>
          <Knopf type="submit" variante="primaer" className={eingebettet ? "" : "w-full"} laedt={laedt} disabled={code.length !== 6}>
            Aktivieren
          </Knopf>
        </form>
      )}
    </div>
  );
}
