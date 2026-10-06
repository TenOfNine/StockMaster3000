import { render, screen } from "@testing-library/react";

import { szenarienLesen } from "./diagramme/Szenarien";
import { Auslastungsbalken, Delta } from "./ui";

describe("Szenarien aus dem Journal", () => {
  it("liest Bull/Base/Bear mit Begründung", () => {
    const s = szenarienLesen("Bull 30 % (Ausbruch) / Base 50 % (seitwärts) / Bear 20 % (Rücksetzer)");
    expect(s).toEqual([
      { name: "Bull", prozent: 30, text: "Ausbruch" },
      { name: "Base", prozent: 50, text: "seitwärts" },
      { name: "Bear", prozent: 20, text: "Rücksetzer" },
    ]);
    expect(szenarienLesen("eher positiv")).toEqual([]);
  });
});

describe("Gewinn und Verlust nie nur über Farbe", () => {
  it("zeigt Vorzeichen", () => {
    render(<Delta wert={-0.05} />);
    expect(screen.getByText("−5,00 %")).toBeInTheDocument();
  });
});

describe("Auslastungsbalken", () => {
  it("nennt Istwert und Grenze", () => {
    render(<Auslastungsbalken label="Gesamt-Exposure" ist={2.23} grenze={4} art="max" einheit="x" />);
    expect(screen.getByText("2,23x")).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Gesamt-Exposure" })).toHaveAttribute("aria-valuenow", "56");
  });
});
