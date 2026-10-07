import { defineConfig } from "@playwright/test";

const chromium = process.env.PW_CHROMIUM;

export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:4173",
    locale: "de-DE",
    timezoneId: "Europe/Berlin",
    launchOptions: chromium ? { executablePath: chromium } : {},
    screenshot: "only-on-failure",
  },
  webServer: [
    { command: "bash e2e/starten.sh", url: "http://127.0.0.1:8000/api/health", timeout: 120_000, reuseExistingServer: false },
    { command: "pnpm exec vite preview --host 127.0.0.1 --port 4173 --strictPort", url: "http://127.0.0.1:4173", timeout: 60_000, reuseExistingServer: false },
  ],
});
