import { render, screen, within } from "@testing-library/react";

import type { Ampel, EinrichtungDaten, NewsStatus } from "@/lib/api";

import { gesamtstufe, NewsAbrufstatus, SystemBereich } from "./Einrichtung";

function zeile(id: string, titel: string, stufe: Ampel["stufe"], text: string, zusatz: Partial<Ampel> = {}): Ampel {
  return { id, titel, stufe, text, details: [], link: null, ...zusatz };
}

const FEED_FEHLER = {
  titel: "SEC 8-K",
  text: "Zugriff verweigert (HTTP 403).",
  hinweis: "Der Anbieter sperrt den Abruf, oft wegen des User-Agent.",
  seit: "2026-10-07T08:00:00+02:00",
  anzahl: 3,
  url: "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&output=atom",
};

function daten(systemstatus: Ampel[]): EinrichtungDaten {
  return { systemstatus, pfade: { daten: "/data", app: "/data-app" } } as EinrichtungDaten;
}

const GRUEN = [
  zeile("daten", "Datenverzeichnis", "gruen", "/data vorhanden und beschreibbar."),
  zeile("git", "Lokales Git", "gruen", "12 Commits. Ohne Remote."),
];

describe("Systemstatus", () => {
  it("färbt Hinweise gelb und Probleme rot, grüne Zeilen bleiben unauffällig", () => {
    const news = zeile("news", "Letzter News-Abruf", "gelb", "gerade eben: 3 neue Meldungen, 1 von 18 Feeds mit Fehler.", { details: [FEED_FEHLER], link: "#news" });
    const worker = zeile("worker", "Hintergrunddienst", "rot", "Der Dienst 'worker' meldet sich nicht.");
    render(<SystemBereich d={daten([...GRUEN, news, worker])} />);

    const reihe = (titel: string) => screen.getByText(titel, { exact: true }).closest("li") as HTMLElement;
    expect(reihe("Letzter News-Abruf")).toHaveAttribute("data-stufe", "gelb");
    expect(reihe("Letzter News-Abruf")).toHaveClass("bg-warnung-flaeche", "border-l-warnung");
    expect(reihe("Hintergrunddienst")).toHaveClass("bg-schlecht-flaeche", "border-l-schlecht");
    for (const titel of ["Datenverzeichnis", "Lokales Git"]) {
      expect(reihe(titel)).toHaveAttribute("data-stufe", "gruen");
      expect(reihe(titel).className).not.toMatch(/bg-(warnung|schlecht)-flaeche/);
    }
    // Nie nur über Farbe: Beschriftung an der Zeile.
    expect(within(reihe("Letzter News-Abruf")).getByText("Hinweis")).toBeInTheDocument();
    expect(within(reihe("Hintergrunddienst")).getByText("Problem")).toBeInTheDocument();
  });

  it("zeigt oben den Gesamtstatus passend zum Punkt in der Navigation und nennt die betroffenen Zeilen", () => {
    const gelb = zeile("news", "Letzter News-Abruf", "gelb", "x");
    const rot = zeile("worker", "Hintergrunddienst", "rot", "y");
    const { container, rerender } = render(<SystemBereich d={daten([...GRUEN, gelb])} />);
    const banner = () => container.querySelector('[role="status"]') as HTMLElement;
    expect(banner()).toHaveAttribute("data-stufe", "gelb");
    expect(banner()).toHaveTextContent("Gesamtstatus: Es gibt Hinweise");
    expect(banner()).toHaveTextContent("1 Hinweis: Letzter News-Abruf");
    rerender(<SystemBereich d={daten([...GRUEN, gelb, rot])} />);
    expect(banner()).toHaveAttribute("data-stufe", "rot");
    expect(banner()).toHaveTextContent("Gesamtstatus: Handlungsbedarf");
    expect(banner()).toHaveTextContent("1 Problem: Hintergrunddienst · 1 Hinweis: Letzter News-Abruf");
    rerender(<SystemBereich d={daten(GRUEN)} />);
    expect(banner()).toHaveAttribute("data-stufe", "gruen");
    expect(banner()).toHaveTextContent("Gesamtstatus: Alles in Ordnung");
    expect(banner()).not.toHaveTextContent("Hinweis:");
  });

  it("nennt bei einem Hinweis die Ursache: Feed, Grund, Dauer, Abhilfe und Link zum Bereich", () => {
    const news = zeile("news", "Letzter News-Abruf", "gelb", "gerade eben: 3 neue Meldungen, 1 von 18 Feeds mit Fehler.", { details: [FEED_FEHLER], link: "#news" });
    render(<SystemBereich d={daten([...GRUEN, news])} />);
    const einzelheiten = screen.getByRole("list", { name: "Einzelheiten zu Letzter News-Abruf" });
    expect(einzelheiten).toHaveTextContent("SEC 8-K: Zugriff verweigert (HTTP 403).");
    expect(einzelheiten).toHaveTextContent("Der Anbieter sperrt den Abruf, oft wegen des User-Agent.");
    expect(einzelheiten).toHaveTextContent(/seit .*2026.* · 3 Abrufe in Folge/);
    expect(einzelheiten).toHaveTextContent("https://www.sec.gov/cgi-bin/browse-edgar");
    expect(screen.getByRole("link", { name: "Zum Bereich „News“" })).toHaveAttribute("href", "#news");
  });

  it("verlinkt nur Zeilen mit Hinweis oder Problem", () => {
    render(<SystemBereich d={daten([zeile("news", "Letzter News-Abruf", "gruen", "ok", { link: "#news" })])} />);
    expect(screen.queryByRole("link", { name: /Zum Bereich/ })).not.toBeInTheDocument();
  });

  it("die Gesamtstufe ist die schlechteste aller Zeilen", () => {
    expect(gesamtstufe([])).toBe("gruen");
    expect(gesamtstufe(GRUEN)).toBe("gruen");
    expect(gesamtstufe([...GRUEN, zeile("a", "A", "gelb", "")])).toBe("gelb");
    expect(gesamtstufe([zeile("a", "A", "gelb", ""), zeile("b", "B", "rot", "")])).toBe("rot");
  });
});

describe("Abrufstatus der News", () => {
  const feed = (id: string, ok: boolean, zusatz = {}) => ({
    id,
    name: id.toUpperCase(),
    url: `https://${id}.example/rss`,
    ok,
    fehler: ok ? null : "Zugriff verweigert (HTTP 403).",
    art: ok ? null : "zugriff",
    hinweis: ok ? null : "Hinweis zur Behebung.",
    seit: ok ? null : "2026-10-07T08:00:00+02:00",
    in_folge: ok ? 0 : 2,
    letzter_erfolg: null,
    anzahl: ok ? 10 : 0,
    neu: ok ? 2 : 0,
    ...zusatz,
  });
  const status = (feeds: ReturnType<typeof feed>[]): NewsStatus => ({
    zeit: new Date().toISOString(),
    neu: 4,
    anzahl_feeds: feeds.length,
    fehlerhaft: feeds.filter((f) => !f.ok).length,
    feeds,
  });

  it("ohne Abruf erklärt er, wie einer startet", () => {
    render(<NewsAbrufstatus status={{ zeit: null, neu: 0, anzahl_feeds: 0, fehlerhaft: 0, feeds: [] }} />);
    expect(screen.getByText(/Noch kein Abruf/)).toBeInTheDocument();
  });

  it("listet ausgefallene Feeds mit Ursache und alle Feeds zum Aufklappen", () => {
    const { container } = render(<NewsAbrufstatus status={status([feed("sec-8k", false), feed("ezb", true), feed("fed", true)])} />);
    expect(container.firstElementChild).toHaveAttribute("data-stufe", "gelb");
    expect(screen.getByText("1 von 3 mit Fehler")).toBeInTheDocument();
    const fehler = screen.getByRole("list", { name: "Feeds mit Fehler" });
    expect(fehler).toHaveTextContent("SEC-8K: Zugriff verweigert (HTTP 403).");
    expect(fehler).toHaveTextContent("Hinweis zur Behebung.");
    expect(fehler).toHaveTextContent("2 Abrufe in Folge");
    expect(screen.getByText("Alle 3 Feeds im letzten Abruf")).toBeInTheDocument();
    expect(screen.getAllByText("2 neu von 10")).toHaveLength(2);
    expect(screen.getByText("Fehler", { selector: "span" })).toBeInTheDocument();
  });

  it("ist rot, wenn jeder Feed ausfiel, und grün, wenn keiner", () => {
    const rot = render(<NewsAbrufstatus status={status([feed("a", false), feed("b", false)])} />);
    expect(rot.container.firstElementChild).toHaveAttribute("data-stufe", "rot");
    rot.unmount();
    const gruen = render(<NewsAbrufstatus status={status([feed("a", true)])} />);
    expect(gruen.container.firstElementChild).toHaveAttribute("data-stufe", "gruen");
    expect(screen.getByText("alle Feeds erreichbar")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Feeds mit Fehler" })).not.toBeInTheDocument();
  });
});
