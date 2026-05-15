# NovelFlow AI Frontend

第一阶段前端 UI 壳：Next.js App Router + React + TypeScript + Tailwind CSS。

## 安装与启动

```bash
cd frontend
npm install
npm run dev
```

## 验证命令

```bash
npm run lint
npm run typecheck
npm run build
```

## 主要路由

- Auth：`/auth/login`、`/auth/register`
- Studio：`/studio`、`/studio/projects`、`/studio/projects/new`
- 项目：`/studio/projects/demo-project`、`/bible`、`/characters`、`/world`、`/outline`、`/write`、`/jobs`、`/versions`、`/export`
- 账号与套餐：`/studio/billing`、`/studio/usage`、`/studio/account`
- Admin：`/admin`、`/admin/users`、`/admin/organizations`、`/admin/plans`、`/admin/quotas`、`/admin/generation-jobs`、`/admin/model-calls`、`/admin/content-review`、`/admin/settings`、`/admin/audit-logs`

## Mock 身份切换

顶部栏按钮可在两种身份间切换：

- 普通用户：`writer@example.com`
- 管理员：`admin@novelflow.ai`（`super_admin`）

普通用户不会看到 Admin 导航；访问 `/admin/*` 会显示无权限页。

## 阶段边界

本阶段不接真实后端、数据库、GPT API、支付、Temporal 或真实导出。所有数据、按钮反馈和状态变化均为 mock。
