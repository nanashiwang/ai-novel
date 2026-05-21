import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright 配置 · NovelFlow AI 金路径 e2e。
 *
 * 运行前提（手动启动后端 + 基础设施）：
 *   make infra-up
 *   cd backend && uvicorn app.main:app --reload --port 8000
 *
 * Playwright 会自动启动 frontend dev 在 13000 端口，e2e 跑 against
 * http://localhost:13000，前端通过 same-origin /api/v1 转发到 8000。
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:13000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev -- --port 13000",
    url: "http://localhost:13000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  expect: {
    timeout: 10_000,
  },
});
