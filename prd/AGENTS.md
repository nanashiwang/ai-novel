# AGENTS.md

本文件用于指导 Codex / AI Coding Agent 在本仓库内工作。请在执行任何实现任务前阅读。

## 项目定位

本项目是一个面向长期商业化运营的 AI 小说自动生产 SaaS 平台，不是聊天机器人前端，也不是单机写作工具。

核心能力：

```text
SaaS 多租户系统
+ 会员套餐/权益/额度系统
+ 自动小说生成工作流
+ 故事圣经/人物/世界观/大纲/章节/场景/正文
+ 自动审稿/自动重写/长期记忆
+ 用户工作台 Web Studio
+ 平台管理后台 Admin Console
```

请优先阅读：

```text
docs/ai_novel_saas_final_architecture.md
docs/ai_novel_saas_ui_spec.md
```

## 技术栈约定

前端：

```text
Next.js App Router
React
TypeScript
Tailwind CSS
shadcn/ui
TanStack Query
Zustand
Tiptap 或 Markdown Editor
```

后端：

```text
FastAPI
PostgreSQL
pgvector
Redis
Temporal
OpenAI GPT API Gateway
```

基础设施：

```text
Docker Compose 起步
PostgreSQL
Redis
Temporal Server / Temporal UI
MinIO
```

## 架构约束

### 1. 多租户边界

所有业务数据必须以 `organization_id` 作为租户边界。

涉及以下资源时必须绑定 organization：

```text
projects
novel_specs
characters
world_items
plot_threads
chapters
scenes
draft_versions
generation_jobs
model_calls
memory_entries
continuity_issues
exports
```

不要只依赖 `user_id` 做数据归属。

### 2. 权限和套餐必须分离

权限控制：

```text
Role / Permission：用户能不能执行某个操作。
```

商业权益：

```text
Plan / Entitlement：用户所属组织买没买这个功能。
```

额度控制：

```text
Quota / Usage：用户还剩多少生成额度。
```

生成任务必须经过：

```text
Auth Check
Tenant Check
Permission Check
Entitlement Check
Quota Check
Quota Reservation
Generation Job Creation
Workflow Start
```

### 3. 自动写作必须是工作流

不要把自动写小说实现成一个普通同步 HTTP 请求。

生成任务应该是：

```text
Create generation_job
Start Temporal Workflow
Update job status
Write intermediate outputs to DB
Record model_calls
Record usage_events
Finalize quota settlement
```

### 4. 最小写作单位是 Scene

正文生成不要直接按整章/整本一次生成。

正确层级：

```text
Project
→ Story Bible
→ Outline
→ Chapter
→ Scene
→ Draft Version
```

### 5. 模型调用必须走 Model Gateway

不要在业务 service 中直接调用 OpenAI API。

所有模型调用必须统一经过：

```text
ModelGateway.generate_json(...)
ModelGateway.generate_text(...)
```

并写入：

```text
model_calls
```

## 前端实现规则

### 1. 不要做成聊天界面

核心页面应该是：

```text
Studio Dashboard
Project Overview
Story Bible
Characters
World Items
Outline
Writing Workspace
Memory
Issues
Generation Jobs
Exports
Billing / Usage
Admin Console
```

### 2. Layout 分离

必须拆分：

```text
PublicLayout
AuthLayout
StudioLayout
ProjectLayout
AdminLayout
```

### 3. 写作工作台布局

写作工作台必须是三栏 + 底部日志：

```text
左侧：章节/场景树
中间：正文编辑器
右侧：设定/记忆/审稿问题
底部：任务日志/模型调用/版本历史
```

### 4. 权限 UI

使用组件封装：

```text
PermissionGate
EntitlementGate
QuotaGuard
```

但不能只依赖前端判断，后端仍必须校验。

### 5. 长任务 UI

所有生成任务必须展示：

```text
任务状态
当前步骤
进度
失败原因
重试
取消
消耗额度
```

### 6. Admin Console

Admin Console 必须和用户端 Studio 分离。

后台至少包含：

```text
用户管理
组织管理
套餐管理
额度管理
生成任务
模型调用日志
审计日志
```

## 代码组织建议

前端：

```text
frontend/
├── app/
├── components/
├── features/
│   ├── auth/
│   ├── organizations/
│   ├── billing/
│   ├── projects/
│   ├── novel/
│   ├── generation/
│   └── admin/
├── hooks/
├── lib/
├── stores/
└── types/
```

后端：

```text
backend/app/
├── api/
├── core/
├── models/
├── schemas/
├── services/
├── workflows/
├── workers/
└── prompts/
```

## 命令约定

前端常用命令：

```bash
npm run dev
npm run lint
npm run typecheck
npm run test
```

后端常用命令：

```bash
pytest
ruff check .
ruff format .
mypy .
alembic upgrade head
```

Docker：

```bash
docker compose up -d
docker compose logs -f
```

如果命令不存在，请先补齐 package scripts 或 Makefile，再运行。

## 实现阶段建议

请按阶段实现，不要一次性生成全部复杂功能。

### Phase 1：前端脚手架和 UI 路由

```text
Next.js 项目结构
Layouts
Routes
Mock data
Studio Dashboard
Project Overview
Writing Workspace Mock
Admin Dashboard Mock
```

### Phase 2：SaaS 底座后端

```text
Auth
Users
Organizations
Membership
RBAC
Plans
Entitlements
Quotas
Usage
```

### Phase 3：小说业务后端

```text
Projects
Novel Specs
Characters
World Items
Chapters
Scenes
Draft Versions
Generation Jobs
Model Calls
```

### Phase 4：Model Gateway + Workflow

```text
OpenAI API Gateway
Prompt Manager
Temporal Workflow
Generate Bible
Generate Outline
Generate First Chapter
```

### Phase 5：前后端联调

```text
真实登录
真实项目创建
真实额度显示
真实生成任务
SSE / 轮询任务进度
```

## 安全与商业化约束

不要：

```text
硬编码 API Key
硬编码管理员账号
绕过权限校验
绕过额度校验
把套餐限制写死在前端
把长任务做成同步请求
把 prompt/response 无限制暴露给低权限用户
把不同 organization 的数据混在一起
```

必须：

```text
所有敏感操作记录 audit_logs
所有生成任务记录 generation_jobs
所有模型调用记录 model_calls
所有额度消耗记录 usage_events
所有长任务支持失败状态
所有破坏性操作二次确认
```

## 测试要求

至少覆盖：

```text
Auth guard
Admin route guard
Organization tenant guard
PermissionGate
EntitlementGate
QuotaGuard
Project creation form
Generation confirm dialog
Job progress display
Admin user table
Admin organization quota adjustment
```

## 输出要求

每次完成任务后，请提供：

```text
修改文件列表
实现摘要
运行过的命令
测试结果
未完成事项
后续建议
```
