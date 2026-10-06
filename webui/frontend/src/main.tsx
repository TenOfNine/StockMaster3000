import "./styles.css";

import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { ApiFehler } from "./lib/api";
import { AuthAnbieter } from "./lib/auth";
import { router } from "./router";

const client = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: true,
      retry: (anzahl, fehler) => !(fehler instanceof ApiFehler && fehler.status < 500) && anzahl < 2,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <AuthAnbieter>
        <TooltipPrimitive.Provider>
          <RouterProvider router={router} />
        </TooltipPrimitive.Provider>
      </AuthAnbieter>
    </QueryClientProvider>
  </StrictMode>,
);
