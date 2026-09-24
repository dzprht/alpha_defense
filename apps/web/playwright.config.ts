import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath, URL } from "node:url";

const python =
  process.env.ALPHA_DEFENSE_PYTHON ?? "/Users/Shared/github/MachineLearning/ml_venv/bin/python";
const backendSource = fileURLToPath(new URL("../backend/src", import.meta.url));

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    ...devices["Desktop Chrome"],
    browserName: "chromium",
  },
  webServer: [
    {
      command: `${python} tests/e2e/serve_backend.py`,
      env: { PYTHONPATH: backendSource },
      reuseExistingServer: false,
      timeout: 30_000,
      url: "http://127.0.0.1:8000/api/v1/health/ready",
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
      reuseExistingServer: false,
      timeout: 30_000,
      url: "http://127.0.0.1:5173/welcome",
    },
  ],
});
