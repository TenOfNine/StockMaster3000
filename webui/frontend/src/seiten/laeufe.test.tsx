import { render, screen } from "@testing-library/react";

import type { Lauf } from "@/lib/api";
import { api } from "@/lib/api";

import { Log } from "./Laeufe";

vi.mock("@/lib/api", async (original) => ({ ...(await original<typeof import("@/lib/api")>()), api: vi.fn() }));

describe("Log der Lauf-Seite", () => {
  const original = Element.prototype.scrollIntoView;
  afterEach(() => {
    Element.prototype.scrollIntoView = original;
    vi.restoreAllMocks();
  });

  it("verträgt ein scrollIntoView, das ein Promise liefert (Chrome 153)", async () => {
    // Neuere Browser geben von scrollIntoView() ein Promise zurück. Gäbe der Effekt es an React weiter, rief
    // React es beim Aufräumen als Funktion auf: "… is not a function", Absturz der ganzen Seite.
    Element.prototype.scrollIntoView = vi.fn(() => Promise.resolve()) as unknown as typeof Element.prototype.scrollIntoView;
    vi.mocked(api)
      .mockResolvedValueOnce({ text: "Claude: Hallo\n", naechstes: 14, fertig: true })
      .mockResolvedValue({ text: "", naechstes: 14, fertig: true });
    const fehler: string[] = [];
    const merken = (e: ErrorEvent) => {
      e.preventDefault();
      fehler.push(e.message);
    };
    window.addEventListener("error", merken);
    const meldungen = vi.spyOn(console, "error").mockImplementation(() => {});

    const { unmount } = render(<Log lauf={{ id: "lauf-1" } as Lauf} />);
    expect(await screen.findByText("Claude: Hallo")).toBeInTheDocument();
    unmount();
    window.removeEventListener("error", merken);

    expect(fehler).toEqual([]);
    expect(meldungen.mock.calls.map((a) => String(a[0]))).not.toContainEqual(expect.stringMatching(/must not return anything|is not a function/));
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });
});

describe("Effekte im Quelltext", () => {
  it("haben immer einen Block als Rumpf und geben nie einen Wert zurück", () => {
    // Ein Effekt darf nur eine Aufräumfunktion zurückgeben. Ein Ausdruck als Rumpf gibt seinen Wert zurück:
    // Liefert die aufgerufene Funktion in einem Browser etwas (z. B. ein Promise), ruft React es später auf.
    const quellen = import.meta.glob("/src/**/*.tsx", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
    const verdaechtig: string[] = [];
    for (const [pfad, text] of Object.entries(quellen)) {
      if (pfad.includes(".test.")) continue;
      for (const treffer of text.matchAll(/use(?:Layout|Insertion)?Effect\(\s*(?:async\s*)?\(\)\s*=>\s*(?=[^\s{])/g)) {
        const zeile = text.slice(0, treffer.index).split("\n").length;
        verdaechtig.push(`${pfad}:${zeile}`);
      }
    }
    expect(verdaechtig).toEqual([]);
  });
});
