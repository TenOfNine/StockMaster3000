import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";

import type { Freigabe, Lauf } from "@/lib/api";
import { api, ApiFehler } from "@/lib/api";

import { FreigabePanel, hinweisText, Restzeit } from "./Freigaben";

vi.mock("@/lib/api", async (original) => ({ ...(await original<typeof import("@/lib/api")>()), api: vi.fn() }));

const lauf = { id: "lauf-1", status: "laeuft" } as Lauf;
const AWK = "for t in ^GSPC ^GDAXI; do python tools/kurse.py historie $t | awk 'NR<=2'; done";

function freigabe(zusatz: Partial<Freigabe> = {}): Freigabe {
  return {
    id: "f-1", lauf: "lauf-1", werkzeug: "Bash", befehl: AWK, beschreibung: "Kurse seit Juli holen", status: "offen", grund: null,
    erstellt: "2026-10-07T10:00:00+00:00", laeuft_ab: "2026-10-07T10:03:00+00:00", entschieden: null, entscheidbar: true, sekunden_rest: 150, ...zusatz,
  };
}

function zeigen(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function antworten(liste: Freigabe[], entscheidung?: () => Promise<unknown>) {
  const aufrufe: { pfad: string; daten?: unknown }[] = [];
  vi.mocked(api).mockImplementation(async (pfad: string, optionen?: { daten?: unknown }) => {
    aufrufe.push({ pfad, daten: optionen?.daten });
    if (pfad.endsWith("/entscheidung")) return (await entscheidung?.()) ?? freigabe({ status: "erlaubt", entscheidbar: false });
    return liste;
  });
  return aufrufe;
}

afterEach(() => vi.restoreAllMocks());

describe("Freigabe-Karte im Lauf", () => {
  it("zeigt Befehl, Beschreibung und Restzeit und schickt die Entscheidung", async () => {
    const aufrufe = antworten([freigabe()]);
    zeigen(<FreigabePanel lauf={lauf} admin />);
    expect(await screen.findByText("Freigabe angefragt: Bash")).toBeInTheDocument();
    expect(screen.getByText(AWK)).toBeInTheDocument();
    // Der Mensch muss den Befehl exakt lesen können: keine Ligaturen wie "<=" oder "==".
    expect(screen.getByText(AWK)).toHaveClass("[font-variant-ligatures:none]");
    expect(screen.getByText(/Beschreibung von Claude \(ungeprüft\): Kurse seit Juli holen/)).toBeInTheDocument();
    expect(screen.getByText(/dann automatisch abgelehnt/)).toHaveTextContent(/Noch 2:\d\d Min\./);
    fireEvent.click(screen.getByRole("button", { name: "Erlauben" }));
    await waitFor(() => expect(aufrufe).toContainEqual({ pfad: "/api/freigaben/f-1/entscheidung", daten: { entscheidung: "erlauben" } }));
    fireEvent.click(screen.getByRole("button", { name: "Ablehnen" }));
    await waitFor(() => expect(aufrufe).toContainEqual({ pfad: "/api/freigaben/f-1/entscheidung", daten: { entscheidung: "ablehnen" } }));
  });

  it("zeigt Nicht-Administratoren die Anfrage ohne Knöpfe", async () => {
    antworten([freigabe()]);
    zeigen(<FreigabePanel lauf={lauf} admin={false} />);
    expect(await screen.findByText(AWK)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Erlauben" })).not.toBeInTheDocument();
    expect(screen.getByText("Ein Administrator entscheidet in der Web-UI.")).toBeInTheDocument();
  });

  it("meldet, wenn die Anfrage inzwischen nicht mehr offen ist", async () => {
    antworten([freigabe()], () => Promise.reject(new ApiFehler(409, "Die Anfrage ist nicht mehr offen (entschieden, abgelaufen oder der Lauf wurde beendet).")));
    zeigen(<FreigabePanel lauf={lauf} admin />);
    fireEvent.click(await screen.findByRole("button", { name: "Erlauben" }));
    expect(await screen.findByText(/nicht mehr offen/)).toBeInTheDocument();
  });

  it("listet bereits Entschiedenes mit Status und Grund, auch das nie Freigebbare", async () => {
    antworten([
      freigabe({ id: "f-2", status: "gesperrt", entscheidbar: false, befehl: "echo x > /data/trades/x", grund: "Umleitung in eine Datei (>) ist nicht freigebbar" }),
      freigabe({ id: "f-3", status: "abgelaufen", entscheidbar: false, befehl: "awk '{print}' x", grund: "Keine Entscheidung in 180 s" }),
      freigabe({ id: "f-4", status: "erlaubt", entscheidbar: false, befehl: "ls", entschieden: "2026-10-07T10:01:00+00:00" }),
    ]);
    zeigen(<FreigabePanel lauf={{ ...lauf, status: "ok" }} admin />);
    expect(await screen.findByText("Freigaben dieses Laufs (3)")).toBeInTheDocument();
    expect(screen.getByText("nie freigebbar, automatisch abgelehnt")).toBeInTheDocument();
    expect(screen.getByText("abgelaufen, automatisch abgelehnt")).toBeInTheDocument();
    expect(screen.getByText("erlaubt")).toBeInTheDocument();
    expect(screen.getByText(/Umleitung in eine Datei/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Erlauben" })).not.toBeInTheDocument();
  });

  it("bleibt unsichtbar, solange es keine Freigaben gibt", async () => {
    antworten([]);
    const { container } = zeigen(<FreigabePanel lauf={lauf} admin />);
    await waitFor(() => expect(api).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});

describe("Hilfen", () => {
  it("Restzeit zählt als Minuten:Sekunden und geht nie unter null", () => {
    const { rerender } = render(<Restzeit sekunden={125} seit={Date.now()} />);
    expect(screen.getByText("2:05")).toBeInTheDocument();
    rerender(<Restzeit sekunden={5} seit={Date.now() - 60_000} />);
    expect(screen.getByText("0:00")).toBeInTheDocument();
  });

  it("Hinweis in der Kopfzeile nennt die Anzahl", () => {
    expect(hinweisText(1)).toBe("1 Freigabe offen");
    expect(hinweisText(3)).toBe("3 Freigaben offen");
  });
});
