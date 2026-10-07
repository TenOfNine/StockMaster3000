// Deutsche Zahlen- und Datumsformate. Die Werte selbst kommen unverändert aus tools/.

const eur = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });
const zahl2 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const zahlFrei = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 6 });

export const STRICH = "–";

export function euro(wert: number | null | undefined): string {
  return wert == null || Number.isNaN(wert) ? STRICH : eur.format(wert);
}

export function zahl(wert: number | null | undefined, stellen = 2): string {
  if (wert == null || Number.isNaN(wert)) return STRICH;
  if (stellen === 2) return zahl2.format(wert);
  return new Intl.NumberFormat("de-DE", { minimumFractionDigits: stellen, maximumFractionDigits: stellen }).format(wert);
}

export function frei(wert: number | null | undefined): string {
  return wert == null || Number.isNaN(wert) ? STRICH : zahlFrei.format(wert);
}

/** Anteil (0,1234) als Prozent; mit Vorzeichen für Renditen. */
export function prozent(wert: number | null | undefined, vorzeichen = false, stellen = 2): string {
  if (wert == null || Number.isNaN(wert)) return STRICH;
  const text = new Intl.NumberFormat("de-DE", {
    minimumFractionDigits: stellen,
    maximumFractionDigits: stellen,
  }).format(wert * 100);
  if (!vorzeichen) return `${text} %`;
  if (wert > 0) return `+${text} %`;
  if (wert < 0) return `−${text.replace("-", "")} %`;
  return `±${text} %`;
}

export function faktor(wert: number | null | undefined): string {
  return wert == null ? STRICH : `${zahl2.format(wert)}x`;
}

const datumKurz = new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
const datumMonat = new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "short" });
const zeitpunkt = new Intl.DateTimeFormat("de-DE", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/Berlin",
});

/** Ungültige Zeitangaben ergeben null: Anzeigefunktionen dürfen eine Seite nie zum Absturz bringen. */
function alsDatum(wert: string): Date | null {
  const d = /^\d{4}-\d{2}-\d{2}$/.test(wert) ? new Date(`${wert}T12:00:00`) : new Date(wert);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function datum(wert: string | null | undefined): string {
  const d = wert ? alsDatum(wert) : null;
  return d ? datumKurz.format(d) : STRICH;
}

export function datumKompakt(wert: string | null | undefined): string {
  const d = wert ? alsDatum(wert) : null;
  return d ? datumMonat.format(d) : STRICH;
}

export function zeit(wert: string | null | undefined): string {
  const d = wert ? alsDatum(wert) : null;
  return d ? zeitpunkt.format(d) : STRICH;
}

export function relativ(wert: string | null | undefined): string {
  const d = wert ? alsDatum(wert) : null;
  if (!d) return STRICH;
  const sekunden = (Date.now() - d.getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat("de-DE", { numeric: "auto" });
  const stufen: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "second"],
    [3600, "minute"],
    [86400, "hour"],
    [604800, "day"],
    [2629800, "week"],
    [31557600, "month"],
  ];
  let vorher = 1;
  for (const [grenze, einheit] of stufen) {
    if (Math.abs(sekunden) < grenze) return rtf.format(-Math.round(sekunden / vorher), einheit);
    vorher = grenze;
  }
  return rtf.format(-Math.round(sekunden / 31557600), "year");
}
