import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";

import { api, ApiFehler, beiAbmeldung, csrfSetzen, type SitzungAntwort } from "./api";

interface AuthKontext {
  sitzung: SitzungAntwort | null;
  laedt: boolean;
  setzen: (s: SitzungAntwort | null) => void;
  abmelden: () => Promise<void>;
}

const Kontext = createContext<AuthKontext | null>(null);

async function meLaden(): Promise<SitzungAntwort | null> {
  try {
    return await api<SitzungAntwort>("/api/auth/me");
  } catch (fehler) {
    if (fehler instanceof ApiFehler && fehler.status === 401) return null;
    throw fehler;
  }
}

export function AuthAnbieter({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const abfrage = useQuery({ queryKey: ["me"], queryFn: meLaden, staleTime: 60_000, retry: false });

  const setzen = useCallback(
    (s: SitzungAntwort | null) => {
      if (s) csrfSetzen(s.csrf);
      client.setQueryData(["me"], s);
      if (!s || s.naechster_schritt !== "fertig") {
        client.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
      }
    },
    [client],
  );

  useEffect(() => {
    if (abfrage.data) csrfSetzen(abfrage.data.csrf);
  }, [abfrage.data]);

  useEffect(() => {
    beiAbmeldung(() => {
      void client.invalidateQueries({ queryKey: ["me"] });
    });
  }, [client]);

  const abmelden = useCallback(async () => {
    try {
      await api("/api/auth/logout", { methode: "POST" });
    } finally {
      client.clear();
      client.setQueryData(["me"], null);
    }
  }, [client]);

  const wert = useMemo(
    () => ({ sitzung: abfrage.data ?? null, laedt: abfrage.isPending, setzen, abmelden }),
    [abfrage.data, abfrage.isPending, setzen, abmelden],
  );
  return <Kontext.Provider value={wert}>{children}</Kontext.Provider>;
}

export function useAuth(): AuthKontext {
  const wert = useContext(Kontext);
  if (!wert) throw new Error("AuthAnbieter fehlt");
  return wert;
}
