import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Beobachtung, BeobachtungKandidaten, BeobachtungWert } from "@/lib/api";
import { api } from "@/lib/api";

import { Beobachtungsliste, KennzahlWert } from "./Beobachtungsliste";

vi.mock("@/lib/api", async (original) => ({ ...(await original<typeof import("@/lib/api")>()), api: vi.fn() }));

function wert(ticker: string, zusatz: Partial<BeobachtungWert> = {}): BeobachtungWert {
  return {
    ticker, name: null, listen: ["dax40"], waehrung: "EUR", handelbar: true, grund: null, datum: "2026-10-12", kurs: 100, tage: 252,
    rendite_1t: 0.0123, rendite_5t: 0.02, rendite_20t: -0.03, rendite_60t: 0.04, abstand_hoch: -0.05, abstand_tief: 0.3,
    sma20_abstand: 0.01, sma50_abstand: 0.02, gap_1t: 0, volumen_relativ_1t: 2.5, volatilitaet_20t: 0.25, ...zusatz,
  };
}

const KENNZAHLEN: Beobachtung["kennzahlen"] = [
  { id: "kurs", titel: "Kurs", art: "preis" },
  { id: "rendite_1t", titel: "1 Tag", art: "prozent" },
  { id: "rendite_5t", titel: "5 Tage", art: "prozent" },
  { id: "rendite_20t", titel: "20 Tage", art: "prozent" },
  { id: "rendite_60t", titel: "60 Tage", art: "prozent" },
  { id: "abstand_hoch", titel: "zum 52-Wochen-Hoch", art: "prozent" },
  { id: "volumen_relativ_1t", titel: "Volumen zum 20-Tage-Schnitt", art: "faktor" },
  { id: "volatilitaet_20t", titel: "Schwankung (20 Tage, p. a.)", art: "prozent_abs" },
];

function liste(eintraege: BeobachtungWert[], zusatz: Partial<Beobachtung> = {}): Beobachtung {
  return {
    zeit: new Date().toISOString(), quelle: "yfinance", anzahl: 603, mit_daten: 590, aktuell: 590,
    listen: [{ id: "dax40", name: "DAX 40", anzahl: 41, mit_daten: 40 }, { id: "sp500", name: "S&P 500", anzahl: 502, mit_daten: 500 }],
    ohne_daten: ["X.DE"], veraltet: [], gesamt: eintraege.length, kennzahlen: KENNZAHLEN, eintraege, ...zusatz,
  };
}

const KANDIDATEN: BeobachtungKandidaten = {
  zeit: new Date().toISOString(),
  bloecke: [{ titel: "Stärkste Tagesbewegung nach oben", kennzahl: "rendite_1t", werte: [wert("SAP.DE", { name: "SAP SE", rendite_1t: 0.05 })] }],
};

function anzeigen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Beobachtungsliste />
    </QueryClientProvider>,
  );
}

function antworten(daten: Beobachtung) {
  vi.mocked(api).mockImplementation(async (pfad: string) => (pfad.includes("/kandidaten") ? KANDIDATEN : daten) as never);
}

afterEach(() => vi.resetAllMocks());

describe("Beobachtungsliste", () => {
  it("erklärt, wenn noch keine Daten vorliegen", async () => {
    antworten(liste([], { zeit: null, quelle: null, anzahl: 0, mit_daten: 0, listen: [], ohne_daten: [] }));
    anzeigen();
    expect(await screen.findByText("Noch keine Beobachtungsliste")).toBeInTheDocument();
    expect(screen.getByText(/ab 23:15 Uhr/)).toBeInTheDocument();
  });

  it("zeigt Kandidaten mit Hinweis, dass nur zu protokollierten Kursen gebucht wird", async () => {
    antworten(liste([wert("SAP.DE")]));
    anzeigen();
    expect(await screen.findByText("Stärkste Tagesbewegung nach oben")).toBeInTheDocument();
    expect(screen.getByText("SAP SE")).toBeInTheDocument();
    expect(screen.getByText(/Gebucht wird zu protokollierten Kursen/)).toBeInTheDocument();
    expect(screen.getByText(/590 von 603 Aktien und ETFs/)).toBeInTheDocument();
    expect(screen.getByText(/Ohne Kursdaten \(1\): X\.DE/)).toBeInTheDocument();
  });

  it("ruft die Tabelle mit Sortierung, Suche und Seite ab und sortiert per Klick auf die Spalte", async () => {
    const nutzer = userEvent.setup();
    antworten(liste([wert("SAP.DE", { name: "SAP SE" }), wert("PENNY", { handelbar: false, grund: "Kurs unter 1 USD", waehrung: "USD", kurs: 0.5 })], { gesamt: 120 }));
    anzeigen();
    await nutzer.click(await screen.findByRole("button", { name: "Alle Werte" }));
    const tabelle = await screen.findByRole("table");
    expect(within(tabelle).getByText("SAP SE")).toBeInTheDocument();
    expect(within(tabelle).getByText("nicht handelbar")).toHaveAttribute("title", "Kurs unter 1 USD");
    expect(within(tabelle).getAllByText("+1,23 %")).toHaveLength(2);  // zwei Zeilen
    expect(within(tabelle).getAllByText("2,50x")).toHaveLength(2);
    expect(within(tabelle).getAllByText("25,0 %")).toHaveLength(2);
    expect(screen.getByText("120 Werte · Seite 1 von 3")).toBeInTheDocument();

    await nutzer.click(within(tabelle).getByRole("button", { name: /5 Tage/ }));
    await waitFor(() => expect(vi.mocked(api).mock.calls.some(([p]) => String(p).includes("sortiert=rendite_5t&aufsteigend=false"))).toBe(true));
    await nutzer.click(within(await screen.findByRole("table")).getByRole("button", { name: /5 Tage/ }));
    await waitFor(() => expect(vi.mocked(api).mock.calls.some(([p]) => String(p).includes("sortiert=rendite_5t&aufsteigend=true"))).toBe(true));

    await nutzer.click(screen.getByRole("button", { name: "Nächste Seite" }));
    await waitFor(() => expect(vi.mocked(api).mock.calls.some(([p]) => String(p).includes("offset=50"))).toBe(true));
    expect(screen.getByRole("button", { name: "Vorherige Seite" })).toBeEnabled();

    await nutzer.type(screen.getByRole("searchbox", { name: "Suchen nach Kürzel oder Name" }), "sap");
    await waitFor(() => expect(vi.mocked(api).mock.calls.some(([p]) => String(p).includes("suche=sap") && String(p).includes("offset=0"))).toBe(true));

    await nutzer.click(screen.getByRole("checkbox", { name: "Nur handelbare Werte" }));
    await waitFor(() => expect(vi.mocked(api).mock.calls.some(([p]) => String(p).includes("nur_handelbar=false"))).toBe(true));
  });

  it("filtert nach Liste", async () => {
    const nutzer = userEvent.setup();
    antworten(liste([wert("AAPL", { listen: ["sp500"] })]));
    anzeigen();
    await nutzer.selectOptions(await screen.findByRole("combobox", { name: "Liste" }), "sp500");
    await waitFor(() => expect(vi.mocked(api).mock.calls.some(([p]) => String(p).includes("/kandidaten?liste=sp500"))).toBe(true));
  });

  it("zeigt Fehler der Abfrage", async () => {
    vi.mocked(api).mockRejectedValue(new Error("Server nicht erreichbar"));
    anzeigen();
    expect(await screen.findByText("Server nicht erreichbar")).toBeInTheDocument();
  });
});

describe("KennzahlWert", () => {
  it("formatiert je Art und kennzeichnet fehlende Werte", () => {
    const e = wert("X", { rendite_60t: null });
    render(
      <>
        <KennzahlWert id="rendite_20t" art="prozent" e={e} />
        <KennzahlWert id="abstand_hoch" art="prozent" e={e} />
        <KennzahlWert id="rendite_60t" art="prozent" e={e} />
        <KennzahlWert id="kurs" art="preis" e={wert("Y", { kurs: 4.5 })} />
      </>,
    );
    expect(screen.getByText("−3,00 %")).toBeInTheDocument();  // Rendite mit Vorzeichen und Symbol
    expect(screen.getByText("−5,00 %")).toBeInTheDocument();  // Abstand zum Hoch: Prozent ohne Farbwertung
    expect(screen.getByText("–")).toBeInTheDocument();
    expect(screen.getByText("4,500")).toBeInTheDocument();
  });
});
