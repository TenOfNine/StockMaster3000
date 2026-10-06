import { CandlestickSeries, ColorType, createChart, createSeriesMarkers, LineStyle, type SeriesMarker, type Time } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import type { Kerze } from "@/lib/api";

export interface Preislinie {
  preis: number;
  titel: string;
  art: "einstieg" | "stop" | "ziel" | "barriere";
}

export interface Markierung {
  datum: string;
  text: string;
  art: "kauf" | "verkauf" | "ereignis";
}

function datumAusZeit(zeit: Time, format: Intl.DateTimeFormatOptions): string {
  const d = typeof zeit === "string" ? new Date(`${zeit}T12:00:00`) : typeof zeit === "number" ? new Date(zeit * 1000) : new Date(zeit.year, zeit.month - 1, zeit.day, 12);
  return d.toLocaleDateString("de-DE", format);
}

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}

function useThemaZaehler(): number {
  const [zaehler, setZaehler] = useState(0);
  useEffect(() => {
    const beobachter = new MutationObserver(() => setZaehler((z) => z + 1));
    beobachter.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => beobachter.disconnect();
  }, []);
  return zaehler;
}

/** Kursverlauf (Tageskerzen aus data/historie/) mit Einstieg, Stop, Ziel und Ausführungen. */
export function Kerzendiagramm({ kerzen, linien = [], markierungen = [], hoehe = 340 }: { kerzen: Kerze[]; linien?: Preislinie[]; markierungen?: Markierung[]; hoehe?: number }) {
  const behaelter = useRef<HTMLDivElement>(null);
  const thema = useThemaZaehler();

  useEffect(() => {
    if (!behaelter.current || kerzen.length === 0) return;
    const gut = token("--gut");
    const schlecht = token("--schlecht");
    const diagramm = createChart(behaelter.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: token("--text-3"),
        fontFamily: "Inter Variable, ui-sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: token("--raster") } },
      rightPriceScale: { borderVisible: false },
      timeScale: {
        borderVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
        tickMarkFormatter: (zeit: Time) => datumAusZeit(zeit, { day: "numeric", month: "short" }),
      },
      crosshair: { horzLine: { labelBackgroundColor: token("--flaeche-3") }, vertLine: { labelBackgroundColor: token("--flaeche-3") } },
      localization: {
        locale: "de-DE",
        priceFormatter: (p: number) => p.toLocaleString("de-DE", { maximumFractionDigits: 2 }),
        timeFormatter: (zeit: Time) => datumAusZeit(zeit, { day: "2-digit", month: "2-digit", year: "numeric" }),
      },
    });
    const serie = diagramm.addSeries(CandlestickSeries, {
      upColor: gut,
      downColor: schlecht,
      borderUpColor: gut,
      borderDownColor: schlecht,
      wickUpColor: gut,
      wickDownColor: schlecht,
      priceLineVisible: false,
    });
    serie.setData(kerzen.map((k) => ({ time: k.datum as Time, open: k.open, high: k.high, low: k.low, close: k.close })));
    const farben = { einstieg: token("--text-2"), stop: schlecht, ziel: gut, barriere: token("--warnung") };
    for (const l of linien) {
      serie.createPriceLine({
        price: l.preis,
        color: farben[l.art],
        lineWidth: 1,
        lineStyle: l.art === "einstieg" ? LineStyle.Solid : LineStyle.Dashed,
        axisLabelVisible: true,
        title: l.titel,
      });
    }
    const vorhanden = new Set(kerzen.map((k) => k.datum));
    const marker: SeriesMarker<Time>[] = markierungen
      .filter((m) => vorhanden.has(m.datum))
      .sort((a, b) => a.datum.localeCompare(b.datum))
      .map((m) => ({
        time: m.datum as Time,
        position: m.art === "kauf" ? "belowBar" : "aboveBar",
        shape: m.art === "kauf" ? "arrowUp" : m.art === "verkauf" ? "arrowDown" : "circle",
        color: m.art === "kauf" ? token("--akzent") : m.art === "verkauf" ? token("--text") : token("--warnung"),
        text: m.text,
      }));
    createSeriesMarkers(serie, marker);
    diagramm.timeScale().fitContent();
    return () => diagramm.remove();
  }, [kerzen, linien, markierungen, thema]);

  if (kerzen.length === 0) return <div className="grid h-[200px] place-items-center text-[13px] text-text-3">Keine gespeicherten Kurse.</div>;
  return <div ref={behaelter} style={{ height: hoehe }} className="w-full" role="img" aria-label="Kursverlauf als Tageskerzen" />;
}
