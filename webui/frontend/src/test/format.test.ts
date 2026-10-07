import { describe, expect, it } from "vitest";

import { datum, relativ, zeit } from "@/lib/format";

describe("Formatierer brechen bei ungültigen Zeitangaben nie ab", () => {
  it.each(["", "kein Datum", "2026-13-45", "2026-10-07 25:99"])("%j", (wert) => {
    expect(() => [datum(wert), zeit(wert), relativ(wert)]).not.toThrow();
    expect(zeit(wert)).toBe("–");
  });
  it("gültige Werte werden formatiert", () => {
    expect(datum("2026-10-07")).toBe("07.10.2026");
    expect(relativ(new Date().toISOString())).toMatch(/^(vor|in) |jetzt/);
  });
});
