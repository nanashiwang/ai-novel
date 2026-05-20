# NovelFlow AI Frontend

生产版前端：Next.js App Router + React + TypeScript + Tailwind CSS，默认连接真实后端 API。

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

## 阶段边界

当前前端直接调用后端 API。登录、项目、故事圣经、章节、场景、任务和 Admin 页面都以真实接口为准；模型生成依赖后端 Model Gateway 的真实 Key 配置。
