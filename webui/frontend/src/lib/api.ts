// API-Client: gleiche Herkunft, Cookie-Sitzung, CSRF-Token im Header.

export type Profil = "defensiv" | "ausgewogen" | "aggressiv";
export const PROFILE: Profil[] = ["defensiv", "ausgewogen", "aggressiv"];
export type Schritt = "totp" | "passwort_aendern" | "zwei_faktor_einrichten" | "fertig";

export interface Benutzer {
  id: string;
  email: string;
  anzeigename: string;
  kennung: string;
  ist_admin: boolean;
  totp_aktiv: boolean;
}

export interface SitzungAntwort {
  benutzer: Benutzer | null;
  naechster_schritt: Schritt;
  csrf: string;
}

export interface Kennzahlen {
  stand: string;
  wert: number;
  rendite: number;
  bench_rendite: number | null;
  gegen_bench: number | null;
  max_dd: number;
  sharpe: number | null;
  handelstage: number;
  min_tage: number;
  geschlossen: number;
  trefferquote: number | null;
  payoff: number | null;
  kostenquote: number;
  exposure: number;
  cashquote: number;
  stufe: number;
  status: string;
  startdatum: string;
  verarbeitet_bis: string;
  hoechststand: string;
  anzahl_positionen: number;
  offene_orders: number;
}

export interface JournalEintrag {
  id: string;
  art: "J" | "S";
  datei: string;
  datum: string | null;
  person: string | null;
  portfolio: Profil | null;
  instrument: string | null;
  auftraggeber: string | null;
  zeit: string | null;
  felder: Record<string, string>;
  text: string;
  verweise: string[];
  trades?: string[];
  status?: string;
  ergebnis_eur?: number | null;
  ergebnis_art?: "realisiert" | "unrealisiert" | null;
}

export interface Termin {
  art: "woche" | "monat" | "quartal" | "stufe2";
  zeitraum: string;
  datei: string;
  text: string;
}

export interface Ueberblick {
  repo: { pfad_name: string; commit: string | null; commit_zeit: string | null; commit_text: string | null; branch: string | null; demo: boolean };
  status: { phase?: string; startdatum?: string; letzte_session?: string };
  sperre: { person: string; start: string; verwaist: boolean } | null;
  termine: Termin[];
  profile: Partial<Record<Profil, Kennzahlen>>;
  letzte_sessions: JournalEintrag[];
  letzte_entscheidungen: JournalEintrag[];
  gestartet: boolean;
}

export interface NavZeile {
  datum: string;
  cash: number;
  positionswert: number;
  portfoliowert: number;
  hoechststand: number;
  drawdown: number;
  drawdown_stufe: number;
  exposure: number;
  cashquote: number;
  zertifikate_anteil: number;
  status: string;
}

export interface NavDaten {
  profile: Partial<Record<Profil, NavZeile[]>>;
  benchmark: ({ datum: string; etf_kurs: number } & Partial<Record<Profil, number>>)[];
}

export interface Position {
  id: string;
  typ: "aktie" | "etf" | "ko" | "faktor";
  richtung: "long" | "short";
  ticker: string;
  basiswert: string;
  stueck: string;
  einstand: string;
  einsatz_eur: number | null;
  eroeffnet: string;
  parameter: Record<string, string | number>;
  stop: string | null;
  kursziel: string | null;
  journal_id: string;
  kurs: number | null;
  kurs_datum: string | null;
  wert_eur: number | null;
  hebel_aktuell: number | null;
}

export interface Order {
  id: string;
  art: "market" | "limit";
  aktion: "kauf" | "verkauf";
  typ: string;
  ticker: string;
  basiswert: string;
  einsatz?: string;
  limit?: string | null;
  stop?: string | null;
  kursziel?: string | null;
  erfasst: string;
  journal_id: string;
}

export interface Auslastung {
  regel: string;
  ist: number;
  grenze: number;
  art: "max" | "min";
  einheit: "%" | "x";
}

export interface PortfolioDetail {
  profil: Profil;
  portfolio: { cash: string; startdatum: string; verarbeitet_bis: string; drawdown_stufe: number; status: string; offene_orders: Order[]; hoechststand: string };
  positionen: Position[];
  bewertung: { cash: number; positionswert: number; nav: number; exposure: number; cashquote: number; zertifikate_anteil: number } | null;
  kennzahlen: Kennzahlen;
  grenzen: Record<string, number>;
  auslastung: Auslastung[];
  max_risiko_trade: number;
  letzter_tageswert: Partial<NavZeile>;
  strategie: string | null;
}

export interface Trade {
  trade_id: string;
  zeit: string;
  order_id: string;
  position_id: string;
  aktion: string;
  typ: string;
  richtung: string;
  ticker: string;
  basiswert: string;
  stueck: number | null;
  kurs: number | null;
  kurs_basiswert: number | null;
  hebel: number | null;
  spread_eur: number | null;
  gebuehr_eur: number | null;
  betrag_eur: number | null;
  cash_danach: number | null;
  kursquelle: string;
  kurs_zeit: string;
  journal_id: string;
  grund: string;
  devisenkurs: number | null;
  stop: number | null;
  kursziel: number | null;
  bemerkung: string;
  profil: Profil;
}

export interface Kerze {
  datum: string;
  open: number;
  high: number;
  low: number;
  close: number;
  dividende: number;
  split: number;
}

export interface Akte extends JournalEintrag {
  folge: Trade[];
  limit_schnappschuesse: { trade_id: string; profil: Profil; zeit: string; kennzahlen: Record<string, number | boolean>; grenzen: Record<string, number> }[];
  erwaehnt_in: { id: string; art: string; datei: string; zeit: string | null }[];
  reviews: Review[];
  lessons: Lesson[];
  basiswert: string | null;
  kerzen: Kerze[];
  position: Position | null;
}

export interface Review {
  pfad: string;
  titel: string;
  art: string;
  zeitraum: string;
}

export interface Lesson {
  id: string;
  titel: string;
  felder: Record<string, string>;
  text: string;
}

export interface Dokument {
  pfad: string;
  titel: string;
  inhalt: string;
}

export interface StatusDaten {
  kopf: { phase?: string; startdatum?: string; letzte_session?: string };
  arbeitspakete: { gruppe: string; kennung: string; titel: string; erledigt: boolean; offen_markiert: boolean }[];
  entscheidungen: { nummer: number; text: string }[];
  auslegungsfragen: { nummer: number; text: string; abschnitt: string; entschieden: boolean }[];
}

export interface Commit {
  hash: string;
  kurz: string;
  zeit: string;
  text: string;
  statistik: string;
}

export interface Befund {
  stufe: "FEHLER" | "WARNUNG";
  pruefung: string;
  text: string;
}

export interface AdminBenutzer {
  id: string;
  email: string;
  anzeigename: string;
  kennung: string;
  ist_admin: boolean;
  aktiv: boolean;
  totp_aktiv: boolean;
  passwortwechsel_noetig: boolean;
  gesperrt_bis: string | null;
  erstellt: string;
}

// --------------------------------------------------------------------------

export class ApiFehler extends Error {
  constructor(public status: number, nachricht: string, public felder?: string[]) {
    super(nachricht);
  }
}

let csrfToken = "";
export function csrfSetzen(token: string) {
  csrfToken = token;
}

type Hoerer = (status: number, nachricht: string) => void;
let aufAbmeldung: Hoerer = () => {};
export function beiAbmeldung(hoerer: Hoerer) {
  aufAbmeldung = hoerer;
}

export async function api<T>(pfad: string, optionen: { methode?: string; daten?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const methode = optionen.methode ?? (optionen.daten === undefined ? "GET" : "POST");
  const kopf: Record<string, string> = { Accept: "application/json" };
  if (optionen.daten !== undefined) kopf["Content-Type"] = "application/json";
  if (methode !== "GET") kopf["X-CSRF-Token"] = csrfToken;
  const antwort = await fetch(pfad, {
    method: methode,
    headers: kopf,
    body: optionen.daten === undefined ? undefined : JSON.stringify(optionen.daten),
    credentials: "same-origin",
    signal: optionen.signal,
  });
  const text = await antwort.text();
  let daten: any = null;
  try {
    daten = text ? JSON.parse(text) : null;
  } catch {
    daten = { detail: text };
  }
  if (!antwort.ok) {
    let nachricht = typeof daten?.detail === "string" ? daten.detail : `Fehler ${antwort.status}`;
    if (antwort.status === 422 && Array.isArray(daten?.felder) && daten.felder.length) nachricht += ` Bitte prüfen: ${daten.felder.join(", ")}.`;
    if (antwort.status === 401 && !pfad.startsWith("/api/auth/login") && !pfad.startsWith("/api/auth/totp")) {
      aufAbmeldung(401, nachricht);
    } else if (antwort.status === 403 && nachricht.startsWith("Anmeldung unvollständig")) {
      aufAbmeldung(403, nachricht);
    }
    throw new ApiFehler(antwort.status, nachricht, daten?.felder);
  }
  return daten as T;
}

export const holen = <T,>(pfad: string) => () => api<T>(pfad);
