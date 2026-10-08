import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { VorgabenKarte } from "@/components/Vorgaben";
import type { VorgabenDaten } from "@/lib/api";
import { api } from "@/lib/api";

import { VorgabenBereich } from "./Einrichtung";

vi.mock("@/lib/api", async (original) => ({ ...(await original<typeof import("@/lib/api")>()), api: vi.fn() }));

const LEER = { text: "", version: 0, zeit: null, von: null };

function daten(zusatz: Partial<VorgabenDaten["profile"]> = {}, historie: VorgabenDaten["historie"] = []): VorgabenDaten {
  return { profile: { defensiv: LEER, ausgewogen: LEER, aggressiv: LEER, ...zusatz }, max_zeichen: 4000, historie };
}

function anzeigen(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

afterEach(() => vi.resetAllMocks());

describe("Vorgaben je Portfolio (Einrichtung)", () => {
  it("zeigt Stand und Verlauf, speichert eine neue Version und meldet, ab wann sie gilt", async () => {
    const nutzer = userEvent.setup();
    const aggressiv = { text: "Alt.", version: 1, zeit: "2026-10-08T10:00:00+00:00", von: "a-adm1" };
    const vorher = daten({ aggressiv }, [{ profil: "aggressiv", ...aggressiv }]);
    const nachher = daten({ aggressiv: { ...aggressiv, text: "Neu gefasst.", version: 2 } }, [
      { profil: "aggressiv", ...aggressiv, text: "Neu gefasst.", version: 2 },
      { profil: "aggressiv", ...aggressiv },
    ]);
    let stand = vorher; // wie der Server: nach dem Speichern liefert auch das Lesen die neue Version
    vi.mocked(api).mockImplementation(async (_pfad: string, optionen?: { methode?: string }) => {
      if (optionen?.methode === "PUT") stand = nachher;
      return (optionen?.methode === "PUT" ? { ok: true, geaendert: true, ...nachher } : stand) as never;
    });
    anzeigen(<VorgabenBereich />);

    const feld = await screen.findByLabelText("Vorgabe für Aggressiv");
    expect(feld).toHaveValue("Alt.");
    expect(screen.getByText("Version 1")).toBeInTheDocument();
    const speichern = screen.getByRole("button", { name: "Speichern" });
    expect(speichern).toBeDisabled(); // unverändert

    await nutzer.clear(feld);
    await nutzer.type(feld, "Neu gefasst.");
    expect(speichern).toBeEnabled();
    expect(screen.getByText("12 / 4000 Zeichen")).toBeInTheDocument();
    await nutzer.click(speichern);

    await waitFor(() => expect(vi.mocked(api)).toHaveBeenCalledWith("/api/einrichtung/vorgaben/aggressiv", { methode: "PUT", daten: { text: "Neu gefasst." } }));
    expect(await screen.findByText("Gespeichert als Version 2; gilt ab dem nächsten Lauf.")).toBeInTheDocument();
    expect(screen.getByLabelText("Vorgabe für Aggressiv")).toHaveValue("Neu gefasst.");
    expect(screen.getByText("Verlauf (2 Änderungen)")).toBeInTheDocument();
  });

  it("wechselt das Portfolio ohne Entwürfe zu verlieren und übernimmt eine alte Fassung in den Editor", async () => {
    const nutzer = userEvent.setup();
    const alt = { profil: "defensiv" as const, text: "Erste Fassung.", version: 1, zeit: "2026-10-07T09:00:00+00:00", von: "a-adm1" };
    const jetzt = { text: "", version: 2, zeit: "2026-10-08T09:00:00+00:00", von: "a-adm1" };
    vi.mocked(api).mockResolvedValue(daten({ defensiv: jetzt }, [{ profil: "defensiv", ...jetzt }, alt]) as never);
    anzeigen(<VorgabenBereich />);

    await nutzer.type(await screen.findByLabelText("Vorgabe für Aggressiv"), "Entwurf aggressiv");
    await nutzer.click(screen.getByRole("button", { name: /Defensiv/ }));
    expect(screen.getByLabelText("Vorgabe für Defensiv")).toHaveValue("");
    await nutzer.click(screen.getByText(/Verlauf \(2 Änderungen\)/));
    const eintraege = screen.getAllByRole("listitem");
    expect(within(eintraege[0]).getByText("(Vorgabe entfernt)")).toBeInTheDocument();
    await nutzer.click(within(eintraege[1]).getByRole("button", { name: "In den Editor übernehmen" }));
    expect(screen.getByLabelText("Vorgabe für Defensiv")).toHaveValue("Erste Fassung.");

    await nutzer.click(screen.getByRole("button", { name: /Aggressiv/ }));
    expect(screen.getByLabelText("Vorgabe für Aggressiv")).toHaveValue("Entwurf aggressiv");
    expect(screen.getByRole("button", { name: "Speichern" })).toBeEnabled();
  });

  it("sperrt Speichern bei zu langem Text", async () => {
    vi.mocked(api).mockResolvedValue(daten() as never);
    anzeigen(<VorgabenBereich />);
    const feld = await screen.findByLabelText("Vorgabe für Aggressiv");
    await userEvent.setup().click(feld);
    await userEvent.setup({ delay: null }).paste("x".repeat(4001));
    expect(screen.getByText("4001 / 4000 Zeichen")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Speichern" })).toBeDisabled();
  });

  it("zeigt Fehler beim Laden", async () => {
    vi.mocked(api).mockRejectedValue(new Error("Nur für Administratoren"));
    anzeigen(<VorgabenBereich />);
    expect(await screen.findByText("Nur für Administratoren")).toBeInTheDocument();
  });
});

describe("Vorgaben im Portfolio (nur lesen)", () => {
  it("zeigt die Vorgabe des Portfolios mit Version, sonst nichts", async () => {
    vi.mocked(api).mockResolvedValue({ profile: { defensiv: { text: "", version: 0, zeit: null }, ausgewogen: { text: "Mit Katalysator.\nZweite Zeile.", version: 3, zeit: "2026-10-08T10:00:00+00:00" }, aggressiv: { text: "", version: 0, zeit: null } } } as never);
    const { container, rerender } = anzeigen(<VorgabenKarte profil="ausgewogen" />);
    expect(await screen.findByText(/Mit Katalysator\./)).toBeInTheDocument();
    expect(screen.getByText(/Version 3/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <VorgabenKarte profil="defensiv" />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
