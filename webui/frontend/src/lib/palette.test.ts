import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { PROFIL_FARBE, PROFIL_NAME } from "@/components/ui";
import { PROFILE } from "./api";

// Profilfarben: Kontrast zum Hintergrund und Unterscheidbarkeit bei Farbsehschwäche (Simulation nach Machado et al. 2009,
// Abstand in CIELAB). Schwellen: die schwächsten Werte der ursprünglichen drei Profilfarben (Kontrast 2,8; Abstand 15).
const MIN_KONTRAST = 2.8;
const MIN_ABSTAND = 15;

const css = readFileSync(resolve(__dirname, "../styles.css"), "utf-8");

function token(block: RegExp, name: string): string {
  const treffer = block.exec(css);
  const wert = new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`).exec(treffer?.[0] ?? "");
  if (!wert) throw new Error(`Token --${name} fehlt`);
  return wert[1];
}

const DUNKEL = /:root,\s*:root\[data-theme="dark"\]\s*\{[^}]*\}/;
const HELL = /:root\[data-theme="light"\]\s*\{[^}]*\}/;

const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
const linear = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const luminanz = (hex: string) => {
  const [r, g, b] = rgb(hex).map(linear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const kontrast = (a: string, b: string) => {
  const [hoch, tief] = [luminanz(a), luminanz(b)].sort((x, y) => y - x);
  return (hoch + 0.05) / (tief + 0.05);
};

const MATRIZEN: Record<string, number[][]> = {
  normal: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
  protanopie: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
  deuteranopie: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.01182, 0.04294, 0.968881]],
  tritanopie: [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.3039]],
};

function lab(hex: string, matrix: number[][]): number[] {
  const lin = rgb(hex).map(linear);
  const [r, g, b] = matrix.map((zeile) => Math.min(1, Math.max(0, zeile[0] * lin[0] + zeile[1] * lin[1] + zeile[2] * lin[2])));
  const x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047;
  const y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))];
}

const abstand = (a: string, b: string, matrix: number[][]) => Math.hypot(...lab(a, matrix).map((v, i) => v - lab(b, matrix)[i]));

describe.each([
  ["dunkel", DUNKEL, "#0b0f14"],
  ["hell", HELL, "#ffffff"],
])("Profilfarben im %s Theme", (_name, block, hintergrund) => {
  const farben = Object.fromEntries(PROFILE.map((p) => [p, token(block, p)]));

  it("haben genug Kontrast zum Hintergrund", () => {
    for (const [profil, farbe] of Object.entries(farben)) {
      expect(kontrast(farbe, hintergrund), `${profil} ${farbe}`).toBeGreaterThanOrEqual(MIN_KONTRAST);
    }
  });

  it("sind auch bei Farbsehschwäche paarweise unterscheidbar", () => {
    for (const [art, matrix] of Object.entries(MATRIZEN)) {
      for (let i = 0; i < PROFILE.length; i++) {
        for (let j = i + 1; j < PROFILE.length; j++) {
          const d = abstand(farben[PROFILE[i]], farben[PROFILE[j]], matrix);
          expect(d, `${PROFILE[i]} / ${PROFILE[j]} (${art})`).toBeGreaterThanOrEqual(MIN_ABSTAND);
        }
      }
    }
  });
});

describe("Profile der Oberfläche", () => {
  it("decken alle Profile aus config/profile.json ab (Name, Farbe, Reihenfolge)", () => {
    const konfig = JSON.parse(readFileSync(resolve(__dirname, "../../../../config/profile.json"), "utf-8"));
    expect(PROFILE).toEqual(Object.keys(konfig.profile));
    for (const p of PROFILE) {
      expect(PROFIL_NAME[p]).toBeTruthy();
      expect(PROFIL_FARBE[p]).toBe(`var(--${p})`);
    }
  });
});
