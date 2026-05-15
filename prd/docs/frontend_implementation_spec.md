# 前端实现规格说明

> 用途：交给 Codex/前端生成 Agent，约束第一阶段前端 UI 壳的技术栈、路由、组件、状态、mock 数据和验收标准。  
> 建议位置：`docs/frontend_implementation_spec.md`

---

## 1. 第一阶段目标

第一阶段只实现**可运行的前端 UI 壳**，不接真实后端。

目标是让项目具备：

```text
完整路由
+ 用户端 Studio
+ Admin Console
+ Mock Auth
+ Mock 数据
+ 权限/套餐/额度/任务状态 UI
+ 所有核心页面可访问
+ 视觉风格尽量贴近 picture/ 下 UI 图片
```

第一阶段不要实现：

```text
真实数据库
真实登录注册
真实支付
真实 GPT API
真实 Temporal workflow
真实文件导出
真实权限后端校验
```

---

## 2. 技术栈

必须使用：

```text
Next.js App Router
React
TypeScript
Tailwind CSS
```

建议使用：

```text
lucide-react       # 图标
recharts           # 图表
clsx               # className 条件组合
sonner 或 shadcn toast # mock 操作反馈，可选
```

可以使用但不强制：

```text
shadcn/ui
Radix UI
Framer Motion
```

不要在第一阶段使用：

```text
真实数据库 SDK
真实支付 SDK
真实 OpenAI/GPT API
真实 Temporal client
真实后端 API client
```

---

## 3. 推荐前端目录结构

```text
frontend/
├── app/
│   ├── auth/
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   ├── studio/
│   │   ├── page.tsx
│   │   ├── projects/
│   │   │   ├── page.tsx
│   │   │   ├── new/page.tsx
│   │   │   └── [projectId]/
│   │   │       ├── page.tsx
│   │   │       ├── bible/page.tsx
│   │   │       ├── characters/page.tsx
│   │   │       ├── world/page.tsx
│   │   │       ├── outline/page.tsx
│   │   │       ├── write/page.tsx
│   │   │       ├── jobs/page.tsx
│   │   │       ├── versions/page.tsx
│   │   │       └── export/page.tsx
│   │   ├── billing/page.tsx
│   │   ├── usage/page.tsx
│   │   └── account/page.tsx
│   ├── admin/
│   │   ├── page.tsx
│   │   ├── users/page.tsx
│   │   ├── organizations/page.tsx
│   │   ├── plans/page.tsx
│   │   ├── quotas/page.tsx
│   │   ├── generation-jobs/page.tsx
│   │   ├── model-calls/page.tsx
│   │   ├── content-review/page.tsx
│   │   ├── settings/page.tsx
│   │   └── audit-logs/page.tsx
│   ├── layout.tsx
│   └── page.tsx
│
├── components/
│   ├── layout/
│   │   ├── studio-sidebar.tsx
│   │   ├── admin-sidebar.tsx
│   │   ├── topbar.tsx
│   │   └── shell.tsx
│   ├── ui/
│   │   ├── badge.tsx
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── data-table.tsx
│   │   ├── progress.tsx
│   │   ├── tabs.tsx
│   │   ├── stat-card.tsx
│   │   └── empty-state.tsx
│   ├── project/
│   ├── writing/
│   ├── admin/
│   └── billing/
│
├── lib/
│   ├── mock-auth.ts
│   ├── mock-data.ts
│   ├── routes.ts
│   ├── permissions.ts
│   ├── format.ts
│   └── cn.ts
│
├── types/
│   ├── auth.ts
│   ├── project.ts
│   ├── billing.ts
│   ├── generation.ts
│   └── admin.ts
│
└── public/
    └── mock-assets/
```

---

## 4. 全局视觉规范

### 色彩

建议 Tailwind 语义色：

```text
背景：slate-50 / zinc-50
卡片：white
边框：slate-200
主文字：slate-950
次文字：slate-500 / slate-600
侧边栏：#071327 / #0B1830
主色：indigo-600 / violet-600
成功：emerald-500
警告：amber-500
错误：rose-500 / red-500
信息：blue-500
```

### 形态

```text
卡片圆角：rounded-2xl
按钮圆角：rounded-xl
轻阴影：shadow-sm / shadow-md
边框：border border-slate-200
布局间距：gap-4 / gap-6
主体最大宽度：不要限制太窄，适合 1920 宽屏
```

### 字体

```text
中文 UI 文案为主
标题加粗
表格字体清晰
不要使用过小字号导致难读
```

---

## 5. Mock Auth 与角色切换

第一阶段不做真实登录，但要有 mock 身份。

建议实现两个 mock 用户：

```ts
const mockAdminUser = {
  id: 'user_admin',
  name: 'Admin',
  email: 'admin@novelflow.ai',
  platformRole: 'super_admin',
  organizationRole: 'owner',
  organizationId: 'org_personal',
  organizationName: 'personal-workspace',
  planCode: 'Pro'
}

const mockNormalUser = {
  id: 'user_writer',
  name: '玄夜',
  email: 'writer@example.com',
  platformRole: 'user',
  organizationRole: 'owner',
  organizationId: 'org_personal',
  organizationName: 'personal-workspace',
  planCode: 'Pro'
}
```

建议在开发阶段提供一个简单开关：

```text
Mock 当前身份：普通用户 / super_admin
```

用于测试：

- 普通用户不得看到 Admin 入口
- `super_admin` 可以看到 Admin 入口

---

## 6. 权限 UI 规则

前端第一阶段只做 mock 权限，不做真实安全校验。

权限判断建议：

```ts
function isPlatformAdmin(user: MockUser) {
  return ['admin', 'super_admin'].includes(user.platformRole)
}

function isSuperAdmin(user: MockUser) {
  return user.platformRole === 'super_admin'
}
```

UI 规则：

1. 普通用户侧边栏不得显示 Admin 导航。
2. 普通用户不得访问 `/admin/*`，可以显示 mock redirect 或权限不足页面。
3. Admin 页面顶部显示当前角色 badge。
4. 只有 `super_admin` 能看到“保存系统设置”按钮为 enabled。
5. 普通 `admin` 可查看但系统设置按钮 disabled。
6. Admin 操作需要显示“会写入 audit_logs”的提示。

---

## 7. 必须实现的路由

### Auth

```text
/auth/login
/auth/register
```

要求：

- 登录/注册 tab 或两个页面都可以。
- 登录成功 mock 跳转 `/studio`。
- 页面低调显示 Admin Console 入口。

### 用户端 Studio

```text
/studio
/studio/projects
/studio/projects/new
/studio/projects/[projectId]
/studio/projects/[projectId]/bible
/studio/projects/[projectId]/characters
/studio/projects/[projectId]/world
/studio/projects/[projectId]/outline
/studio/projects/[projectId]/write
/studio/projects/[projectId]/jobs
/studio/projects/[projectId]/versions
/studio/projects/[projectId]/export
/studio/billing
/studio/usage
/studio/account
```

### Admin Console

```text
/admin
/admin/users
/admin/organizations
/admin/plans
/admin/quotas
/admin/generation-jobs
/admin/model-calls
/admin/content-review
/admin/settings
/admin/audit-logs
```

---

## 8. 页面实现要求

### `/studio`

必须根据用户角色显示两种状态：

- `super_admin`：参考 `02_studio_dashboard_admin_visible.png`
- 普通用户：参考 `03_studio_dashboard_user_only.png`

必须包含：

```text
数据卡片
最近小说项目
生成任务
快捷操作
套餐/额度信息
```

`super_admin` 额外包含：

```text
管理员导航组
管理员控制中心
用户/组织管理入口
套餐权益配置入口
额度调整入口
任务队列控制入口
模型调用日志入口
```

### `/studio/projects/new`

参考 `04_project_create_wizard.png`。

必须包含：

```text
4 步 stepper
小说标题
一句话创意
小说类型
目标字数
目标章节数
叙事视角
文风
目标读者
禁忌内容
创建后自动生成预览
套餐和额度检查
保存草稿
取消
创建项目并生成故事圣经
```

### `/studio/projects/[projectId]`

参考 `05_project_overview.png`。

必须包含：

```text
项目标题：雾都归档人
项目归属组织
项目状态 drafting
生成控制按钮
状态机
章节进度
最近审稿问题
项目内 tabs
查看 Workflow 日志链接
```

### `/studio/projects/[projectId]/write`

参考 `06_writing_workspace.png`。

必须是三栏布局：

```text
左侧：章节 / 场景树
中间：正文编辑器
右侧：记忆 / 人物 / 世界观 / 审稿
底部：生成任务日志 / 模型调用摘要
```

必须体现最小生成单位是 `scene`。

### `/studio/projects/[projectId]/characters`

参考 `08_characters_relationships.png`。

必须包含：

```text
人物列表
人物详情
关系图或关系列表
角色状态时间线
Memory Engine 自动更新提示
```

### `/studio/projects/[projectId]/outline`

参考 `10_outline_planner.png`。

必须包含：

```text
大纲树
当前章节大纲
章节目标
核心冲突
人物变化
信息揭示
结尾钩子
关联伏笔
场景拆分
大纲生成控制
额度预估
权限 badge
```

### `/studio/projects/[projectId]/jobs`

参考 `12_generation_jobs.png`。

必须包含：

```text
任务队列表格
当前 Workflow 详情
模型调用日志摘要
额度结算卡片
取消任务
重试失败任务
查看完整日志
```

必须体现任务由 Workflow 驱动，不是普通 HTTP 请求。

### `/studio/projects/[projectId]/export`

参考 `14_export_center.png`。

必须包含：

```text
导出格式卡片
导出配置
套餐权益
最近导出文件
导出来源：final 版本
开始导出
预览目录
下载最新版本
```

### `/admin`

参考 `17_admin_dashboard.png`。

必须是平台级数据，不是单组织数据。

必须包含：

```text
注册用户
付费组织
今日生成字数
失败任务
近 7 日趋势图
运营告警
最新生成任务
系统状态
```

### `/admin/plans` 和 `/admin/quotas`

参考 `19_admin_plans_entitlements_quotas.png`。

必须包含：

```text
套餐列表
套餐详情
plan_features 表格
额度配置
手动额度调整工具
审计提示
权限 badge
```

### `/admin/settings` 和 `/admin/audit-logs`

参考 `22_admin_system_settings_audit_logs.png`。

必须包含：

```text
设置导航
模型配置
Prompt 版本表格
队列配置
audit_logs 表格
super_admin 修改权限
admin disabled 状态
```

---

## 9. 基础组件要求

必须实现或等价实现：

```text
AppShell
StudioSidebar
AdminSidebar
Topbar
StatCard
StatusBadge
PlanBadge
QuotaProgress
DataTable
ProgressBar
Tabs
ActionCard
WorkflowSteps
ModelCallTable
EditorMock
EmptyState
PermissionNotice
```

---

## 10. Mock Action 要求

所有按钮第一阶段只做 mock 操作。

示例：

```text
新建项目 → mock 添加项目或跳转项目页
继续生成下一章 → 显示 loading，然后任务状态变 running
取消任务 → running 改为 cancelled
重试失败任务 → failed 改为 queued
开始导出 → 生成一条 mock export file
保存系统设置 → 只有 super_admin 可点，显示 toast
```

---

## 11. 构建与验收

Codex 完成后必须提供：

```text
安装命令
启动命令
主要路由列表
mock 用户切换方式
已实现页面清单
未实现/占位页面清单
```

必须尝试运行：

```text
npm run lint
npm run typecheck
npm run build
```

如果项目命令不同，需要在 README 中说明。

---

## 12. 不允许事项

第一阶段不要：

1. 接真实后端 API。
2. 接真实 GPT API。
3. 接真实支付。
4. 接真实 Temporal。
5. 把 Admin 页面和用户 Studio 混成同一个侧边栏。
6. 让普通用户看到 Admin 控制入口。
7. 使用 lorem ipsum。
8. 使用英文乱码占位。
9. 生成不可运行的静态 HTML 拼图。
10. 牺牲路由完整性去追求单页视觉。
