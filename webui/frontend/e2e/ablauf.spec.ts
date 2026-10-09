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

  await page.goto("/einrichtung");
  await expect(page.getByText("Nur für Administratoren")).toBeVisible();

  await page.goto("/roadmap");
  await expect(page.getByRole("heading", { name: "Roadmap & Status" })).toBeVisible();

  await page.goto("/analyse/kurse");
  await expect(page.getByRole("heading", { name: "Markt & Kurse" })).toBeVisible();
  await expect(page.getByText("Benchmark und Devisen")).toBeVisible();
  await expect(page.getByText("veraltet").first()).toBeVisible();
  await expect(page.getByText("Meldungen zu diesem Wert")).toBeVisible();

  // Beobachtungsliste (Screener): Kandidaten, Tabelle, Suche und Filter; nicht handelbare Werte sind gekennzeichnet.
  await page.getByRole("tab", { name: "Beobachtungsliste" }).click();
  await expect(page.getByText("Stärkste Tagesbewegung nach oben")).toBeVisible();
  await expect(page.getByText(/Gebucht wird zu protokollierten Kursen/)).toBeVisible();
  await page.getByRole("button", { name: "Alle Werte" }).click();
  const tabelle = page.getByRole("table");
  await expect(tabelle).toContainText("Allianz");
  await expect(tabelle).not.toContainText("Demo-Wert unter 1 USD");
  await page.getByRole("checkbox", { name: "Nur handelbare Werte" }).uncheck();
  await expect(tabelle).toContainText("Demo-Wert unter 1 USD");
  await expect(tabelle.getByText("nicht handelbar")).toBeVisible();
  await page.getByRole("searchbox", { name: "Suchen nach Kürzel oder Name" }).fill("nvidia");
  await expect(tabelle.getByRole("row")).toHaveCount(2); // Kopfzeile und ein Treffer
  await expect(tabelle).toContainText("NVDA");
});

test("Admin richtet ein: Hinweis im Cockpit führt zur Einrichtung, Secrets bleiben verborgen", async ({ page }) => {
  await anmelden(page, "admin@e2e.local", "Admin-Passwort-2026!");
  await expect(page.getByText("Einrichtung noch nicht abgeschlossen")).toBeVisible();
  await page.getByRole("link", { name: /Claude verbinden/ }).last().click();
  await expect(page.getByRole("heading", { name: "Einrichtung", exact: true })).toBeVisible();
  for (const bereich of ["Claude", "Kursdaten", "News", "Sessions & Zeitplan", "Vorgaben je Portfolio", "Spielstart", "Sicherung", "Systemstatus"]) {
    await expect(page.getByRole("heading", { name: bereich, exact: true })).toBeVisible();
  }
  // Anmeldung über den Container: Dialog öffnet sich; ohne Hintergrunddienst wartet er auf den Link.
  await page.getByRole("button", { name: "Mit Claude anmelden" }).click();
  await expect(page.getByRole("dialog", { name: "Mit dem Claude-Abo anmelden" })).toBeVisible();
  await expect(page.getByText(/Anmeldelink wird im Container erzeugt|bereitet die Anmeldung vor/)).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Abbrechen" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();

  await page.getByText("Oder Token manuell eintragen").click();
  const token = "sk-ant-oat01-e2e-geheim-0000000000000000000000abcd";
  await page.getByRole("textbox", { name: "Claude-Token" }).fill(token);
  await page.locator("#claude").getByRole("button", { name: "Speichern", exact: true }).click();
  await expect(page.getByText("Claude-Token gespeichert (verschlüsselt).")).toBeVisible();
  await expect(page.getByText("••••abcd")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Claude-Token" })).toHaveValue("");
  expect(await page.content()).not.toContain(token);
  await expect(page.getByText("Hintergrunddienst", { exact: true })).toBeVisible();
  // Systemstatus: Ohne laufenden Hintergrunddienst ist die Zeile rot, und das Banner darüber (wie der Punkt in der Navigation) auch.
  await expect(page.locator('#system li[data-stufe="rot"]').filter({ has: page.getByText("Hintergrunddienst", { exact: true }) })).toBeVisible();
  await expect(page.locator('#system [role="status"][data-stufe="rot"]')).toContainText("Gesamtstatus: Handlungsbedarf");
  await expect(page.locator('#system li[data-stufe="gruen"]').filter({ hasText: "Datenverzeichnis" })).toBeVisible();

  // Vorgaben je Portfolio: speichern (neue Version, Verlauf); im Portfolio sind sie nur lesbar.
  const vorgabe = "E2E: Traden, sobald nach Kosten ein kleiner Gewinn sichtbar ist.";
  await page.getByLabel("Vorgabe für Aggressiv").fill(vorgabe);
  await page.locator("#vorgaben").getByRole("button", { name: "Speichern", exact: true }).click();
  await expect(page.getByText("Gespeichert als Version 1; gilt ab dem nächsten Lauf.")).toBeVisible();
  await page.getByText(/Verlauf \(1 Änderung\)/).click();
  await expect(page.locator("#vorgaben li").filter({ hasText: vorgabe })).toBeVisible();
  await page.goto("/portfolios/aggressiv");
  await page.getByRole("tab", { name: /Anlagerichtlinie/ }).click();
  await expect(page.getByText("Vorgaben der Auftraggeber", { exact: true })).toBeVisible();
  await expect(page.getByText(vorgabe)).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveCount(0);
});

test("Admin meldet sich nur mit Passwort an und legt einen Benutzer mit Zwei-Faktor-Code an", async ({ page, browser }) => {
  await anmelden(page, "admin@e2e.local", "Admin-Passwort-2026!");
  await expect(page.getByText("Wertentwicklung")).toBeVisible();

  await page.goto("/admin");
  await page.getByRole("button", { name: "Benutzer anlegen" }).click();
  await page.getByLabel("E-Mail").fill("neu@e2e.local");
  await page.getByLabel("Anzeigename").fill("Neu");
  await page.getByLabel("Dein Passwort zur Bestätigung").fill("Admin-Passwort-2026!");
  // Ohne Code (oder mit falschem Code) wird nicht angelegt; die Anmeldung selbst brauchte keinen.
  await page.getByLabel("Zwei-Faktor-Code").fill("000000");
  await page.getByRole("dialog").getByRole("button", { name: "Benutzer anlegen" }).click();
  await expect(page.getByText("Zwei-Faktor-Code ungültig.")).toBeVisible();
  await page.getByLabel("Zwei-Faktor-Code").fill(totp("JBSWY3DPEHPK3PXP"));
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

test("Lauf-Seite zeigt Läufe und Zeitplan und verträgt jede Form von Daten", async ({ page }) => {
  const fehler: string[] = [];
  page.on("pageerror", (e) => fehler.push(e.message));
  await anmelden(page, "admin@e2e.local", "Admin-Passwort-2026!");
  await expect(page.getByText("Wertentwicklung")).toBeVisible();
  // Wie im Alltag: erst Einrichtung (füllt den Zwischenspeicher), dann per Navigation zu den Läufen.
  await page.getByRole("navigation", { name: "Hauptnavigation" }).getByRole("link", { name: "Claude-Läufe" }).click();
  await expect(page.getByRole("heading", { name: "Claude-Läufe" })).toBeVisible();
  await page.goto("/einrichtung");
  await expect(page.getByRole("heading", { name: "Einrichtung", exact: true })).toBeVisible();
  await page.getByRole("navigation", { name: "Hauptnavigation" }).getByRole("link", { name: "Claude-Läufe" }).click();
  await expect(page.getByRole("heading", { name: "Claude-Läufe" })).toBeVisible();
  await expect(page.getByText("Automatik an")).toBeVisible();
  await expect(page.getByText(/Nächster Lauf/)).toBeVisible();
  await page.getByRole("button", { name: /Trading-Session.*fertig/ }).click();
  await page.waitForTimeout(800);
  expect(await page.locator('[role="alert"]').allInnerTexts(), "Bereichsfehler in der Lauf-Ansicht").toEqual([]);
  await expect(page.getByText("Ich habe nicht gehandelt").first()).toBeVisible();
  await expect(page.getByText("Prüfung: Prüfung bestanden")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Claude-Läufe" })).toBeVisible();

  // Jede Form von Lauf-Daten und Zeitplan-Antworten (derselbe Login, damit die Anmeldebegrenzung nicht greift).
  const basis = { id: "x", art: "trading", status: "ok", meldung: null, modell: "sonnet", aufwand: "medium", auftraggeber: "auftraggeber-a", ausloeser: "manuell",
    erstellt: "2026-10-07T16:44:00+00:00", begonnen: "2026-10-07T16:44:05+00:00", beendet: "2026-10-07T16:45:00+00:00", pruefung_ok: true, abbrechen: false, ergebnis: null, parameter: null };
  const varianten = [
    { ...basis, ergebnis: { result: "**ok**", num_turns: 3, duration_ms: 1000, subtype: "success", rueckgabe: 0 } },
    { ...basis, ergebnis: { result: null, rueckgabe: 0 }, meldung: "text" },
    { ...basis, status: "fehler", meldung: "Fehler", pruefung_ok: null, begonnen: null, beendet: null, aufwand: null, modell: null, auftraggeber: null },
    { ...basis, status: "limit", ergebnis: { result: 5 } },
    { ...basis, status: "wartet", erstellt: "kaputt" },
    { ...basis, status: "abgebrochen", art: "unbekannt" },
    { ...basis, status: "laeuft", ausloeser: "zeitplan" },
  ];
  for (const [i, v] of varianten.entries()) {
    await page.route("**/api/laeufe?*", (r) => r.fulfill({ json: [{ ...v, id: `x${i}` }] }));
    await page.route("**/api/laeufe", (r) => (r.request().method() === "GET" ? r.fulfill({ json: [{ ...v, id: `x${i}` }] }) : r.continue()));
    await page.goto("/laeufe");
    await expect(page.getByRole("heading", { name: "Claude-Läufe" })).toBeVisible();
    await page.waitForTimeout(600);
    expect(await page.getByText(/konnte nicht angezeigt werden/).count(), `Variante ${i}: ${fehler.join("|")}`).toBe(0);
    await page.unrouteAll();
  }
  // Auch eine unvollständige oder fremde Antwort des Zeitplans darf die Seite nicht beeinträchtigen.
  const plan = { automatik: true, zeitzone: "Europe/Berlin", auftraggeber: "auftraggeber-a", naechste: [{ zeit: "kaputt", art: "x" }], token_gesetzt: true, letzte: [{ termin: 5, ergebnis: null }] };
  for (const [i, antwort] of [plan, { ...plan, naechste: undefined, letzte: undefined }, { detail: "fremd" }].entries()) {
    await page.route("**/api/laeufe/plan", (r) => r.fulfill({ json: antwort }));
    await page.goto("/laeufe");
    await expect(page.getByRole("heading", { name: "Claude-Läufe" })).toBeVisible();
    await page.waitForTimeout(600);
    expect(await page.getByText(/konnte nicht angezeigt werden/).allInnerTexts(), `Plan ${i}`).toEqual([]);
    await page.unrouteAll();
  }

  // Freigabe-Anfrage der Claude-CLI: Hinweis in der Kopfzeile (auf jeder Seite), Karte im Lauf, Entscheidung an die API.
  const befehl = "for t in ^GSPC ^GDAXI; do python tools/kurse.py historie $t | awk 'NR<=2'; done";
  const anfrage = { id: "f-1", lauf: "x", werkzeug: "Bash", befehl, beschreibung: "Kurse seit Juli holen", status: "offen", grund: null, erstellt: new Date().toISOString(),
    laeuft_ab: new Date(Date.now() + 150_000).toISOString(), entschieden: null, entscheidbar: true, sekunden_rest: 150 };
  let gesendet: unknown = null;
  await page.route("**/api/freigaben?*", (r) => r.fulfill({ json: [anfrage] }));
  await page.route("**/api/freigaben/f-1/entscheidung", async (r) => {
    gesendet = r.request().postDataJSON();
    await r.fulfill({ json: { ...anfrage, status: "erlaubt", entscheidbar: false } });
  });
  await page.goto("/");
  await page.getByRole("link", { name: "1 Freigabe offen" }).click();
  await expect(page.getByRole("heading", { name: "Claude-Läufe" })).toBeVisible();
  await expect(page.getByText("Freigabe angefragt: Bash")).toBeVisible();
  await expect(page.getByText(befehl)).toBeVisible();
  await expect(page.getByText(/Beschreibung von Claude \(ungeprüft\)/)).toBeVisible();
  await page.getByRole("button", { name: "Erlauben" }).click();
  await expect.poll(() => gesendet).toEqual({ entscheidung: "erlauben" });
  await page.unrouteAll();
  expect(fehler).toEqual([]);
});
