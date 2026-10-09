import { automatischAusloeser, euro, prozent, zahl, faktor, datum } from "./format";

describe("deutsche Formate", () => {
  it("formatiert Geld und Zahlen", () => {
    expect(euro(1111.55).replace(/\s/g, " ")).toBe("1.111,55 €"); // Intl nutzt ein geschütztes Leerzeichen
    expect(zahl(0.5)).toBe("0,50");
    expect(faktor(2.234)).toBe("2,23x");
    expect(euro(null)).toBe("–");
  });
  it("zeigt Renditen mit Vorzeichen", () => {
    expect(prozent(0.1116, true)).toBe("+11,16 %");
    expect(prozent(-0.0286, true)).toBe("−2,86 %");
    expect(prozent(0, true)).toBe("±0,00 %");
    expect(prozent(0.5, false, 0)).toBe("50 %");
  });
  it("formatiert Datum ohne Zeitzonenversatz", () => {
    expect(datum("2026-10-05")).toBe("05.10.2026");
  });
});

describe("automatischAusloeser", () => {
  it("erkennt die Kennzeichnung automatisch ausgeführter Buchungen", () => {
    expect(automatischAusloeser("automatisch (Auslöser: Stop): Kurs 98 <= Stop 99")).toBe("Stop");
    expect(automatischAusloeser("Teilverkauf")).toBeNull();
    expect(automatischAusloeser(null)).toBeNull();
  });
});
