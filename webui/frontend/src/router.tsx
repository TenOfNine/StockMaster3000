import { createRootRoute, createRoute, createRouter, type ErrorComponentProps, Link, Outlet } from "@tanstack/react-router";
import { Compass, Loader2 } from "lucide-react";

import { AppRahmen } from "./components/layout/AppRahmen";
import { Karte, Leer } from "./components/ui";
import { useAuth } from "./lib/auth";
import { Akte } from "./seiten/Akte";
import { Kurse, Ranking, ReviewsLessons } from "./seiten/Analyse";
import { Anmeldung } from "./seiten/Anmeldung";
import { Cockpit } from "./seiten/Cockpit";
import { Entscheidungen, Sessions } from "./seiten/Entscheidungen";
import { Portfolio } from "./seiten/Portfolio";
import { Einrichtung } from "./seiten/Einrichtung";
import { Laeufe } from "./seiten/Laeufe";
import { Pruefung, Regelwerk, RoadmapStatus } from "./seiten/Projekt";
import { Rechner } from "./seiten/Rechner";
import { Administration, Konto } from "./seiten/Verwaltung";

function Wurzel() {
  const { sitzung, laedt } = useAuth();
  if (laedt)
    return (
      <div className="grid h-full place-items-center">
        <Loader2 className="size-6 animate-spin text-text-3" aria-label="Lädt" />
      </div>
    );
  if (!sitzung || sitzung.naechster_schritt !== "fertig") return <Anmeldung />;
  return <Outlet />;
}

function NurAdmin() {
  const { sitzung } = useAuth();
  return sitzung?.benutzer?.ist_admin ? <Administration /> : <NichtGefunden />;
}

function NichtGefunden() {
  return (
    <Karte className="mt-6">
      <Leer
        icon={<Compass className="size-5" />}
        titel="Seite nicht gefunden"
        aktion={
          <Link to="/" className="text-[13px] font-medium text-akzent hover:underline">
            Zum Cockpit
          </Link>
        }
      />
    </Karte>
  );
}

function Fehlerseite({ error }: ErrorComponentProps) {
  return (
    <Karte className="mt-6">
      <Leer
        icon={<Compass className="size-5" />}
        titel="Diese Seite konnte nicht angezeigt werden"
        text={`Technische Meldung: ${(error as Error | undefined)?.message || "unbekannt"}`}
        aktion={
          <div className="flex flex-col items-center gap-2 text-[13px] font-medium">
            <details className="max-w-xl text-[11px] font-normal text-text-3">
              <summary className="cursor-pointer">Einzelheiten</summary>
              <pre className="mt-1 max-h-40 overflow-auto text-left font-mono whitespace-pre-wrap">{String((error as Error | undefined)?.stack ?? "").split("\n").slice(0, 8).join("\n")}</pre>
            </details>
            <button type="button" onClick={() => window.location.reload()} className="text-akzent hover:underline">
              Seite neu laden
            </button>
            <Link to="/" className="text-akzent hover:underline">
              Zum Cockpit
            </Link>
          </div>
        }
      />
    </Karte>
  );
}

const wurzel = createRootRoute({ component: Wurzel });
const app = createRoute({ getParentRoute: () => wurzel, id: "app", component: AppRahmen, notFoundComponent: NichtGefunden });

const seiten = [
  createRoute({ getParentRoute: () => app, path: "/", component: Cockpit }),
  createRoute({ getParentRoute: () => app, path: "/portfolios/$profil", component: Portfolio }),
  createRoute({ getParentRoute: () => app, path: "/entscheidungen", component: Entscheidungen }),
  createRoute({ getParentRoute: () => app, path: "/entscheidungen/$id", component: Akte }),
  createRoute({ getParentRoute: () => app, path: "/sessions", component: Sessions }),
  createRoute({ getParentRoute: () => app, path: "/analyse/ranking", component: Ranking }),
  createRoute({
    getParentRoute: () => app,
    path: "/analyse/reviews",
    component: ReviewsLessons,
    validateSearch: (s: Record<string, unknown>): { datei?: string } => (typeof s.datei === "string" ? { datei: s.datei } : {}),
  }),
  createRoute({ getParentRoute: () => app, path: "/analyse/kurse", component: Kurse }),
  createRoute({ getParentRoute: () => app, path: "/analyse/rechner", component: Rechner }),
  createRoute({ getParentRoute: () => app, path: "/regelwerk", component: Regelwerk }),
  createRoute({ getParentRoute: () => app, path: "/einrichtung", component: Einrichtung }),
  createRoute({ getParentRoute: () => app, path: "/roadmap", component: RoadmapStatus }),
  createRoute({ getParentRoute: () => app, path: "/laeufe", component: Laeufe }),
  createRoute({ getParentRoute: () => app, path: "/pruefung", component: Pruefung }),
  createRoute({ getParentRoute: () => app, path: "/konto", component: Konto }),
  createRoute({ getParentRoute: () => app, path: "/admin", component: NurAdmin }),
];

export const router = createRouter({
  routeTree: wurzel.addChildren([app.addChildren(seiten)]),
  defaultPreload: "intent",
  defaultNotFoundComponent: NichtGefunden,
  defaultErrorComponent: Fehlerseite,
  scrollRestoration: true,
});
