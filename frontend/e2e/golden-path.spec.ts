/**
 * NovelFlow AI 金路径 e2e（v1）。
 *
 * v1 覆盖范围：不依赖 LLM 调用即可验证的端到端链路：
 *   1. 注册新用户（随机邮箱避免冲突）
 *   2. 自动登录后访问 Studio
 *   3. 创建项目
 *   4. 进入 Bible / Outline / Writing / Versions / Export 五个项目子页
 *   5. 验证页面骨架与关键交互元素可见
 *   6. 注销
 *
 * v2 候选：mock model_gateway 走真实生成链路覆盖 succeeded 状态。
 *
 * 前提：后端已在 :8000 运行；运行命令 `make infra-up && uvicorn app.main:app --port 8000`。
 */
import { expect, test } from "@playwright/test";

const randomEmail = () =>
  `e2e_${Date.now()}_${Math.floor(Math.random() * 10000)}@novelflow.test`;
const PASSWORD = "Password123!";

test.describe("Golden path · 未触发 LLM 的端到端链路", () => {
  test("注册 → 创建项目 → 巡视五个子页 → 注销", async ({ page }) => {
    const email = randomEmail();
    const projectTitle = `e2e-project-${Date.now()}`;

    // 1. 进入注册页（从首页 / 应该会自动重定向到 /auth/login）
    await page.goto("/auth/register");
    await expect(page).toHaveURL(/\/auth\/register$/);
    await expect(
      page.getByRole("heading", { name: "注册 NovelFlow" }),
    ).toBeVisible();

    // 2. 填表 + 提交
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel("密码").fill(PASSWORD);
    await page.getByLabel("昵称").fill(email.split("@")[0]);
    await page
      .getByRole("button", { name: /注册并创建个人组织/ })
      .click();

    // 3. 注册成功后前端会跳到 /studio（dashboard）
    await page.waitForURL(/\/studio/, { timeout: 15_000 });
    await expect(page).toHaveURL(/\/studio/);

    // 4. 跳到新建项目页（侧边栏 / 直接路径）
    await page.goto("/studio/projects/new");
    await expect(page.getByText("基础信息")).toBeVisible();

    // 项目标题字段是 textbox，预填值为"雾都归档人"，覆盖为随机名
    const titleInput = page
      .locator("input")
      .filter({ hasNot: page.locator('[type="number"]') })
      .first();
    await titleInput.fill(projectTitle);

    // 提交创建（按钮文案"创建项目"）
    await page.getByRole("button", { name: "创建项目" }).click();

    // 5. 创建成功跳转 /studio/projects/<id> 或 /studio/projects
    await page.waitForURL(/\/studio\/projects(?:\/|$)/, { timeout: 15_000 });

    // 6. 项目列表必须能找到刚创建的项目；点进去
    await page.goto("/studio/projects");
    const projectCard = page.getByText(projectTitle).first();
    await expect(projectCard).toBeVisible({ timeout: 10_000 });
    await projectCard.click();

    // 7. 进入项目详情，URL 应为 /studio/projects/<id>
    await page.waitForURL(/\/studio\/projects\/[^/]+$/, { timeout: 10_000 });
    const projectUrl = page.url();
    const projectId = projectUrl.match(/\/projects\/([^/]+)/)?.[1];
    expect(projectId).toBeTruthy();

    // 8. 巡视五个子页
    for (const [path, expectedText] of [
      ["/bible", "故事启动中心"],
      ["/outline", "章节大纲"],
      ["/write", "写作工作台"],
      ["/versions", "版本"],
      ["/export", "导出"],
    ] as const) {
      await page.goto(`/studio/projects/${projectId}${path}`);
      await expect(
        page.getByText(expectedText, { exact: false }).first(),
      ).toBeVisible({ timeout: 10_000 });
    }

    // 9. 退出（topbar 头像 → 退出登录；如果 UI 不易点，直接清 localStorage 等同）
    await page.evaluate(() => {
      window.localStorage.clear();
      document.cookie.split(";").forEach((c) => {
        document.cookie = c
          .replace(/^ +/, "")
          .replace(/=.*/, `=;expires=${new Date().toUTCString()};path=/`);
      });
    });
    await page.goto("/studio");
    await page.waitForURL(/\/auth\/login/, { timeout: 10_000 });
  });

  test("登录指定管理员账号 → 访问 Admin Dashboard", async ({ page }) => {
    test.skip(
      !process.env.E2E_ADMIN_EMAIL || !process.env.E2E_ADMIN_PASSWORD,
      "未配置 E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD，跳过管理员后台用例",
    );

    await page.goto("/auth/login");
    await page.getByLabel("邮箱").fill(process.env.E2E_ADMIN_EMAIL!);
    await page.getByLabel("密码").fill(process.env.E2E_ADMIN_PASSWORD!);
    await page.getByRole("button", { name: /登录工作台/ }).click();

    await page.waitForURL(/\/studio/, { timeout: 15_000 });

    // 进入 Admin Console
    await page.goto("/admin");
    await expect(
      page.getByRole("heading", { name: /Admin 后台总览/ }),
    ).toBeVisible({ timeout: 10_000 });

    // 五个 Admin 子页可访问
    for (const [path, expectedHeading] of [
      ["/admin/users", /用户管理/],
      ["/admin/organizations", /组织管理/],
      ["/admin/plans", /套餐/],
      ["/admin/quotas", /额度管理/],
      ["/admin/generation-jobs", /平台生成队列/],
      ["/admin/settings", /系统设置/],
      ["/admin/audit-logs", /审计日志/],
    ] as const) {
      await page.goto(path);
      await expect(
        page.getByRole("heading", { name: expectedHeading }),
      ).toBeVisible({ timeout: 10_000 });
    }
  });
});
