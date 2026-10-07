import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useQuery } from "@tanstack/react-query";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import {
  BookOpenText,
  Bot,
  Calculator,
  ChevronDown,
  CircleUserRound,
  FileClock,
  FlaskConical,
  Gauge,
  GitCommitHorizontal,
  LineChart,
  ListChecks,
  Lock,
  LogOut,
  Menu,
  Moon,
  NotebookPen,
  Scale,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  Trophy,
  Unlock,
  Users,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { api, PROFILE, type Ueberblick } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { relativ } from "@/lib/format";

import { FreigabeHinweis } from "../Freigaben";
import { Abzeichen, PROFIL_FARBE, PROFIL_NAME, Taste } from "../ui";
import { Befehlspalette } from "./Befehlspalette";

interface NavEintrag {
  zu: string;
  text: string;
  icon: ReactNode;
  farbe?: string;
}

const GRUPPEN: { titel?: string; eintraege: NavEintrag[] }[] = [
  { eintraege: [{ zu: "/", text: "Cockpit", icon: <Gauge className="size-4" /> }] },
  {
    titel: "Portfolios",
    eintraege: PROFILE.map((p) => ({ zu: `/portfolios/${p}`, text: PROFIL_NAME[p], icon: null, farbe: PROFIL_FARBE[p] })),
  },
  {
    titel: "Entscheidungen",
    eintraege: [
      { zu: "/entscheidungen", text: "Zeitachse & Trade-Akten", icon: <NotebookPen className="size-4" /> },
      { zu: "/sessions", text: "Sessions & Abwägungen", icon: <FileClock className="size-4" /> },
      { zu: "/laeufe", text: "Claude-Läufe", icon: <Bot className="size-4" /> },
    ],
  },
  {
    titel: "Analyse",
    eintraege: [
      { zu: "/analyse/ranking", text: "Ranking & Benchmark", icon: <Trophy className="size-4" /> },
      { zu: "/analyse/reviews", text: "Reviews & Lessons", icon: <BookOpenText className="size-4" /> },
      { zu: "/analyse/kurse", text: "Markt & Kurse", icon: <LineChart className="size-4" /> },
      { zu: "/analyse/rechner", text: "Zertifikatsrechner", icon: <Calculator className="size-4" /> },
    ],
  },
  {
    titel: "Projekt",
    eintraege: [
      { zu: "/regelwerk", text: "Regelwerk", icon: <Scale className="size-4" /> },
      { zu: "/roadmap", text: "Roadmap & Status", icon: <ListChecks className="size-4" /> },
      { zu: "/pruefung", text: "Prüfung & Audit", icon: <GitCommitHorizontal className="size-4" /> },
    ],
  },
];

export function useUeberblick() {
  return useQuery({ queryKey: ["ueberblick"], queryFn: () => api<Ueberblick>("/api/spiel/ueberblick"), refetchInterval: 60_000 });
}

function useTheme() {
  const [theme, setTheme] = useState<string>(() => document.documentElement.getAttribute("data-theme") ?? "dark");
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("sm-theme", theme);
    } catch {
      /* Speicher nicht verfügbar */
    }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))] as const;
}

function Navigation({ beiKlick }: { beiKlick?: () => void }) {
  const pfad = useRouterState({ select: (s) => s.location.pathname });
  const { sitzung } = useAuth();
  const aktiv = (zu: string) => (zu === "/" ? pfad === "/" : pfad === zu || pfad.startsWith(`${zu}/`));
  const gruppen: { titel?: string; eintraege: NavEintrag[] }[] = sitzung?.benutzer?.ist_admin
    ? [
        ...GRUPPEN,
        {
          titel: "Verwaltung",
          eintraege: [
            { zu: "/einrichtung", text: "Einrichtung", icon: <SlidersHorizontal className="size-4" /> },
            { zu: "/admin", text: "Administration", icon: <Users className="size-4" /> },
          ],
        },
      ]
    : GRUPPEN;
  return (
    <nav className="space-y-5" aria-label="Hauptnavigation">
      {gruppen.map((gruppe, i) => (
        <div key={gruppe.titel ?? i}>
          {gruppe.titel && <div className="mb-1.5 px-3 text-[11px] font-semibold tracking-[0.06em] text-text-3 uppercase">{gruppe.titel}</div>}
          <ul className="space-y-0.5">
            {gruppe.eintraege.map((e) => (
              <li key={e.zu}>
                <Link
                  to={e.zu}
                  onClick={beiKlick}
                  className={cn(
                    "group flex items-center gap-2.5 rounded-lg px-3 py-[7px] text-[13.5px] font-medium transition-colors",
                    aktiv(e.zu) ? "bg-flaeche-3 text-text" : "text-text-2 hover:bg-flaeche-2 hover:text-text",
                  )}
                >
                  {e.farbe ? (
                    <span className="grid size-4 place-items-center">
                      <span className="size-2.5 rounded-[3px]" style={{ background: e.farbe }} />
                    </span>
                  ) : (
                    <span className={cn("text-text-3 transition-colors group-hover:text-text-2", aktiv(e.zu) && "text-text")}>{e.icon}</span>
                  )}
                  {e.text}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Marke() {
  return (
    <Link to="/" className="flex items-center gap-2.5 px-2">
      <img src="/favicon.svg" alt="" className="size-8 rounded-[9px]" />
      <div className="leading-tight">
        <div className="text-[14px] font-semibold tracking-[-0.01em] text-text">StockMaster 3000</div>
        <div className="text-[11.5px] text-text-3">Börsenexperiment</div>
      </div>
    </Link>
  );
}

export function AppRahmen() {
  const [menueOffen, setMenueOffen] = useState(false);
  const [paletteOffen, setPaletteOffen] = useState(false);
  const pfad = useRouterState({ select: (s) => s.location.pathname });

  useEffect(() => {
    setMenueOffen(false);
  }, [pfad]);
  useEffect(() => {
    const taste = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOffen((o) => !o);
      }
    };
    window.addEventListener("keydown", taste);
    return () => window.removeEventListener("keydown", taste);
  }, []);

  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 flex-col border-r border-rand bg-flaeche/60 px-3 py-4 backdrop-blur lg:flex">
        <Marke />
        <div className="mt-6 flex-1 overflow-y-auto pr-1">
          <Navigation />
        </div>
        <ArbeitsbereichInfo />
      </aside>

      {menueOffen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMenueOffen(false)} aria-hidden />
          <aside className="einblenden absolute inset-y-0 left-0 flex w-[280px] flex-col border-r border-rand bg-flaeche px-3 py-4">
            <div className="flex items-center justify-between">
              <Marke />
              <button className="rounded-md p-2 text-text-3 hover:bg-flaeche-3" onClick={() => setMenueOffen(false)} aria-label="Menü schließen">
                <X className="size-4" />
              </button>
            </div>
            <div className="mt-6 flex-1 overflow-y-auto">
              <Navigation beiKlick={() => setMenueOffen(false)} />
            </div>
            <ArbeitsbereichInfo />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <Kopfzeile oeffneMenue={() => setMenueOffen(true)} oeffnePalette={() => setPaletteOffen(true)} />
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 pt-6 pb-16 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
      <Befehlspalette offen={paletteOffen} setOffen={setPaletteOffen} />
    </div>
  );
}

function ArbeitsbereichInfo() {
  const { data } = useUeberblick();
  if (!data) return null;
  return (
    <div className="mt-4 rounded-xl border border-rand bg-flaeche-2 p-3 text-[12px]">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-medium text-text">{data.repo.demo ? "Demo-Arbeitsbereich" : "Spiel-Repository"}</span>
        {data.repo.demo && <Abzeichen ton="akzent">Demo</Abzeichen>}
      </div>
      <div className="mt-1 truncate text-text-3">
        {data.repo.commit ? (
          <>
            <span className="font-mono">{data.repo.commit}</span> · {relativ(data.repo.commit_zeit)}
          </>
        ) : (
          "kein Commit"
        )}
      </div>
    </div>
  );
}

function Sperrstatus() {
  const { data } = useUeberblick();
  if (!data) return null;
  if (!data.sperre)
    return (
      <span className="hidden items-center gap-1.5 rounded-full border border-rand px-2.5 py-1 text-[12px] text-text-3 md:inline-flex">
        <Unlock className="size-3.5" /> Keine Session aktiv
      </span>
    );
  return (
    <span
      className={cn(
        "hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-medium md:inline-flex",
        data.sperre.verwaist ? "bg-warnung-flaeche text-warnung" : "bg-gut-flaeche text-gut",
      )}
    >
      <Lock className="size-3.5" />
      {data.sperre.verwaist ? "Verwaiste Sperre" : "Session läuft"} · {data.sperre.person} · {relativ(data.sperre.start)}
    </span>
  );
}

function Kopfzeile({ oeffneMenue, oeffnePalette }: { oeffneMenue: () => void; oeffnePalette: () => void }) {
  const { sitzung, abmelden } = useAuth();
  const [theme, umschalten] = useTheme();
  const benutzer = sitzung?.benutzer;
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-rand bg-bg/80 px-4 backdrop-blur-md sm:px-6 lg:px-8">
      <button className="rounded-md p-2 text-text-2 hover:bg-flaeche-3 lg:hidden" onClick={oeffneMenue} aria-label="Menü öffnen">
        <Menu className="size-5" />
      </button>
      <button
        onClick={oeffnePalette}
        className="flex h-9 w-full max-w-[340px] items-center gap-2 rounded-lg border border-rand bg-flaeche-2 px-3 text-[13px] text-text-3 transition-colors hover:border-rand-stark"
      >
        <Search className="size-4" />
        <span className="flex-1 truncate text-left">Suchen und springen …</span>
        <span className="hidden sm:inline">
          <Taste>Strg</Taste> <Taste>K</Taste>
        </span>
      </button>
      <div className="ml-auto flex items-center gap-2">
        <FreigabeHinweis />
        <Sperrstatus />
        <button onClick={umschalten} className="rounded-lg p-2 text-text-2 hover:bg-flaeche-3 hover:text-text" aria-label="Darstellung umschalten">
          {theme === "dark" ? <Sun className="size-[18px]" /> : <Moon className="size-[18px]" />}
        </button>
        <DropdownMenu.Root>
          <DropdownMenu.Trigger className="flex items-center gap-2 rounded-lg py-1 pr-2 pl-1 hover:bg-flaeche-3" aria-label="Konto-Menü">
            <span className="grid size-7 place-items-center rounded-full bg-gradient-to-br from-defensiv via-ausgewogen to-aggressiv text-[12px] font-semibold text-white">
              {benutzer?.anzeigename.charAt(0).toUpperCase()}
            </span>
            <span className="hidden text-[13px] font-medium text-text sm:inline">{benutzer?.anzeigename}</span>
            <ChevronDown className="size-3.5 text-text-3" />
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content align="end" sideOffset={8} className="z-50 min-w-[220px] rounded-xl border border-rand bg-flaeche p-1.5 shadow-2xl">
              <div className="px-2.5 py-2">
                <div className="text-[13px] font-medium text-text">{benutzer?.anzeigename}</div>
                <div className="truncate text-[12px] text-text-3">{benutzer?.email}</div>
                <div className="mt-1 flex gap-1">
                  <Abzeichen>Kennung {benutzer?.kennung}</Abzeichen>
                  {benutzer?.ist_admin && <Abzeichen ton="akzent">Admin</Abzeichen>}
                </div>
              </div>
              <DropdownMenu.Separator className="my-1 h-px bg-rand" />
              <MenueLink zu="/konto" icon={<CircleUserRound className="size-4" />}>Konto & Sicherheit</MenueLink>
              {benutzer?.ist_admin && <MenueLink zu="/admin" icon={<ShieldCheck className="size-4" />}>Administration</MenueLink>}
              {benutzer?.ist_admin && <MenueLink zu="/einrichtung" icon={<SlidersHorizontal className="size-4" />}>Einrichtung</MenueLink>}
              <MenueLink zu="/roadmap" icon={<FlaskConical className="size-4" />}>Roadmap & Status</MenueLink>
              <DropdownMenu.Separator className="my-1 h-px bg-rand" />
              <DropdownMenu.Item
                onSelect={() => void abmelden()}
                className="flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] text-text-2 outline-none data-[highlighted]:bg-flaeche-3 data-[highlighted]:text-text"
              >
                <LogOut className="size-4" /> Abmelden
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>
    </header>
  );
}

function MenueLink({ zu, icon, children }: { zu: string; icon: ReactNode; children: ReactNode }) {
  return (
    <DropdownMenu.Item asChild>
      <Link to={zu} className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] text-text-2 outline-none data-[highlighted]:bg-flaeche-3 data-[highlighted]:text-text">
        {icon}
        {children}
      </Link>
    </DropdownMenu.Item>
  );
}
