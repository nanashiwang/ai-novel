# E2E 金路径测试

Playwright 端到端测试，覆盖 NovelFlow AI 的关键用户旅程：注册 → 创建项目 → 巡视五个项目子页 → 注销，以及 admin 控制台子页可访问性。

## 前提

后端 + 基础设施已在运行：

```bash
# 项目根
make infra-up                           # 启动 postgres / redis / temporal / minio
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

默认 admin 账号 `admin@novelflow.ai` / `admin123456`（参见 `infra/postgres/seed`），e2e 第二个用例会用它。

## 运行

```bash
cd frontend
npm run e2e                  # headless 跑全部
npm run e2e:ui               # 打开 Playwright UI 调试
npx playwright test --headed # 显式开浏览器看跑的过程
```

首次运行需要先装浏览器：

```bash
npx playwright install chromium
```

## 范围

**v1（当前）**：不依赖 LLM 调用
- 注册 / 登录 / 注销
- 创建项目
- Bible / Outline / Writing / Versions / Export 五子页路由 + 关键文本可见
- Admin Console 七子页路由

**v2（计划）**：mock model_gateway 走完整生成链路
- generate_bible → succeeded（fake provider 返回固定 StoryBibleContract）
- generate_outline → 验证 chapters 表落库
- 写作 + 审稿 + 重写完整闭环
- 导出 Markdown 验证内容

## CI 集成

`playwright.config.ts` 已配置：
- `forbidOnly: true` 在 CI 环境强制（避免 `.only` 进 CI）
- `retries: 2` CI 容错
- `webServer.reuseExistingServer: false` 强制启动新 dev server
- `reporter: "github"` GitHub Actions 友好格式

CI 启动栈推荐：

```yaml
- run: cd frontend && npx playwright install chromium --with-deps
- run: docker compose up -d postgres redis temporal
- run: cd backend && pip install -e '.[dev]' && uvicorn app.main:app --port 8000 &
- run: cd frontend && npm ci && npm run e2e
```
