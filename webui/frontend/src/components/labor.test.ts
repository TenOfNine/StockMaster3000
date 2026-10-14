import { describe, expect, it } from "vitest";

import { mitIntervall } from "@/components/Labor";

describe("mitIntervall", () => {
  it("zeigt Wert und 95-%-Intervall mit Dezimalkomma", () => {
    expect(mitIntervall({ wert: 0.021, ci: [-0.03, 0.072] }, "prozent", true)).toBe("+2,1 % [−3,0 %; +7,2 %]");
    expect(mitIntervall({ wert: 1.234, ci: [0.5, 2] }, "zahl")).toBe("1,23 [0,50; 2,00]");
  });
  it("zeigt einen Strich ohne Wert und nur den Wert ohne Intervall", () => {
    expect(mitIntervall(undefined, "zahl")).toBe("–");
    expect(mitIntervall({ wert: null, ci: null }, "zahl")).toBe("–");
    expect(mitIntervall({ wert: 0.5, ci: null }, "prozent")).toBe("50,0 %");
  });
});
