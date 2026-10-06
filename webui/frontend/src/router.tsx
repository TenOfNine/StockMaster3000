import { createRootRoute, createRoute, createRouter, Link, Outlet } from "@tanstack/react-router";
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
import { Einrichtung, Pruefung, Regelwerk } from "./seiten/Projekt";
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
  createRoute({ getParentRoute: () => app, path: "/pruefung", component: Pruefung }),
  createRoute({ getParentRoute: () => app, path: "/konto", component: Konto }),
  createRoute({ getParentRoute: () => app, path: "/admin", component: NurAdmin }),
];

export const router = createRouter({
  routeTree: wurzel.addChildren([app.addChildren(seiten)]),
  defaultPreload: "intent",
  defaultNotFoundComponent: NichtGefunden,
  scrollRestoration: true,
});
