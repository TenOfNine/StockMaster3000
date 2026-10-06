import { createHmac } from "node:crypto";

import { expect, test, type Page } from "@playwright/test";

/** TOTP (RFC 6238) für das Test-Geheimnis JBSWY3DPEHPK3PXP. */
function totp(geheimnis: string): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const z of geheimnis) bits += alphabet.indexOf(z).toString(2).padStart(5, "0");
  const schluessel = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
  const zaehler = Buffer.alloc(8);
  zaehler.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const hmac = createHmac("sha1", schluessel).update(zaehler).digest();
  const versatz = hmac[hmac.length - 1] & 0xf;
  const code = (hmac.readUInt32BE(versatz) & 0x7fffffff) % 1_000_000;
  return code.toString().padStart(6, "0");
}

async function anmelden(page: Page, email: string, passwort: string) {
  await page.goto("/");
  await page.getByLabel("E-Mail").fill(email);
  await page.getByLabel("Passwort").fill(passwort);
  await page.getByRole("button", { name: "Anmelden" }).click();
}

test("Benutzer sieht Cockpit, Portfolio, Trade-Akte und Prüfung", async ({ page }) => {
  await anmelden(page, "kim@e2e.local", "Kim-Passwort-2026!");
  await expect(page.getByRole("heading", { name: /Kim/ })).toBeVisible();
  await expect(page.getByText("Wertentwicklung")).toBeVisible();
  await expect(page.getByRole("link", { name: /Defensiv/ }).first()).toBeVisible();

  await page.getByRole("navigation", { name: "Hauptnavigation" }).getByRole("link", { name: "Aggressiv" }).click();
  await expect(page.getByRole("heading", { name: /Aggressiv/ })).toBeVisible();
  await page.getByRole("tab", { name: /Limits/ }).click();
  await expect(page.getByRole("meter", { name: "Gesamt-Exposure" })).toBeVisible();

  await page.goto("/entscheidungen");
  const ersteAkte = page.locator('a[href^="/entscheidungen/J-"]').first();
  await ersteAkte.click();
  await expect(page.getByText("These", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("Ausführung und Verlauf", { exact: false })).toBeVisible();

  await page.goto("/pruefung");
  await page.getByRole("button", { name: "Prüfung ausführen" }).click();
  await expect(page.getByText(/Prüfung bestanden/)).toBeVisible({ timeout: 30_000 });

  await page.goto("/admin");
  await expect(page.getByText("Seite nicht gefunden")).toBeVisible();
});

test("Admin meldet sich mit Zwei-Faktor an und legt einen Benutzer an", async ({ page, browser }) => {
  await anmelden(page, "admin@e2e.local", "Admin-Passwort-2026!");
  await page.getByLabel("Code").fill(totp("JBSWY3DPEHPK3PXP"));
  await page.getByRole("button", { name: "Bestätigen" }).click();
  await expect(page.getByText("Wertentwicklung")).toBeVisible();

  await page.goto("/admin");
  await page.getByRole("button", { name: "Benutzer anlegen" }).click();
  await page.getByLabel("E-Mail").fill("neu@e2e.local");
  await page.getByLabel("Anzeigename").fill("Neu");
  await page.getByLabel("Dein Passwort zur Bestätigung").fill("Admin-Passwort-2026!");
  await page.getByRole("dialog").getByRole("button", { name: "Benutzer anlegen" }).click();
  const einmal = (await page.locator("code").first().textContent())!.trim();
  expect(einmal).toMatch(/^[A-Za-z0-9]{5}(-[A-Za-z0-9]{5}){3}$/);

  const kontext = await browser.newContext();
  const neu = await kontext.newPage();
  await anmelden(neu, "neu@e2e.local", einmal);
  await expect(neu.getByRole("heading", { name: "Neues Passwort festlegen" })).toBeVisible();
  await neu.getByLabel("Einmalpasswort").fill(einmal);
  await neu.getByLabel("Neues Passwort", { exact: true }).fill("Ein-eigenes-Passwort-42");
  await neu.getByLabel("Neues Passwort wiederholen").fill("Ein-eigenes-Passwort-42");
  await neu.getByRole("button", { name: "Passwort speichern" }).click();
  await expect(neu.getByText("Wertentwicklung")).toBeVisible();
  await kontext.close();
});
