import { defineConfig } from "@playwright/test";

// The app runs in fixture mode: recorded HKEXnews responses, no network (docs/SPEC.md §10.7).
export default defineConfig({
  testDir: "e2e",
  use: { baseURL: "http://127.0.0.1:8765" },
  webServer: {
    command:
      "npm run build && rm -rf ../backend/static && cp -r dist ../backend/static && cd ../backend && HKEX_MODE=fixtures uv run uvicorn app.main:app --port 8765",
    url: "http://127.0.0.1:8765/api/health",
    reuseExistingServer: false,
  },
});
