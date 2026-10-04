import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";
export default defineConfig({
  testDir: "./e2e",
  timeout: 90000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8877",
    viewport: { width: 1440, height: 1000 },
    locale: "ru-RU",
    launchOptions: process.env.STAGEOS_CHROMIUM
      ? {
          executablePath: process.env.STAGEOS_CHROMIUM,
          args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        }
      : {},
  },
  webServer: {
    command: `${process.env.STAGEOS_PYTHON || "python"} -m backend.launcher --test-no-auth --port 8877`,
    cwd: "..",
    url: "http://127.0.0.1:8877/api/bootstrap",
    reuseExistingServer: false,
    timeout: 90000,
    env: {
      STAGEOS_ENABLE_DEMO: process.env.STAGEOS_ENABLE_DEMO || "1",
      STAGEOS_HOME:
        process.env.STAGEOS_UI_HOME ||
        join(tmpdir(), "stageos-ui-" + Date.now()),
    },
  },
  reporter: [["list"], ["json", { outputFile: "../ui-results.json" }]],
});
