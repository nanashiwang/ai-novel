# Codex 第一阶段前端 UI 实现任务

请根据当前仓库文件实现第一阶段前端 UI 壳。

---

## 必须先阅读并遵守

1. `AGENTS.md`
2. `docs/ai_novel_saas_final_architecture.md`
3. `docs/ai_novel_saas_ui_spec.md`
4. `docs/ui_image_manifest.md`
5. `docs/frontend_implementation_spec.md`
6. `docs/mock_data_schema.md`
7. `picture/` 目录下所有 UI 图片

如果 `docs/` 下文件名略有不同，请先根据仓库实际文件名识别对应内容，不要忽略架构和 UI 规格文档。

---

## 本阶段目标

只实现前端 UI 壳，不接真实后端。

需要完成：

```text
Next.js App Router 项目
+ React
+ TypeScript
+ Tailwind CSS
+ 用户端 Studio
+ Admin Console
+ Mock Auth
+ Mock 数据
+ Mock Action
+ 页面路由完整
+ 视觉尽量贴近 picture/ 下 UI 图片
```

---

## 禁止事项

本阶段不要实现：

```text
真实后端 API
真实数据库
真实 GPT API
真实支付
真实 Temporal workflow
真实文件导出
真实登录注册
```

所有数据都使用 mock data。所有按钮都使用 mock action。

---

## 技术要求

必须使用：

```text
Next.js App Router
React
TypeScript
Tailwind CSS
```

可以使用：

```text
lucide-react
recharts
clsx
sonner 或 toast 组件
shadcn/ui 或自定义 UI 组件
```

---

## 必须实现的页面

### Auth

```text
/auth/login
/auth/register
```

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

## 视觉参考

请按照 `docs/ui_image_manifest.md` 中的图片与路由映射实现页面。

重点参考：

```text
picture/01_auth_login_register.png
picture/02_studio_dashboard_admin_visible.png
picture/03_studio_dashboard_user_only.png
picture/04_project_create_wizard.png
picture/05_project_overview.png
picture/06_writing_workspace.png
picture/07_story_bible.png
picture/08_characters_relationships.png
picture/09_world_lorebook.png
picture/10_outline_planner.png
picture/11_scene_context_builder.png
picture/12_generation_jobs.png
picture/13_versions_and_audit_issues.png
picture/14_export_center.png
picture/15_billing_usage.png
picture/16_account_organization_settings.png
picture/17_admin_dashboard.png
picture/18_admin_users_organizations.png
picture/19_admin_plans_entitlements_quotas.png
picture/20_admin_jobs_model_calls.png
picture/22_admin_system_settings_audit_logs.png
picture/登录页插图.png
```

如果实际文件名不同，请根据图片内容匹配，不要中断任务。

特别注意：`docs/ui_image_manifest.md` 是图片与路由映射的最终依据；若本任务文件的重点参考图片列表与 manifest 不一致，以 manifest 为准。

---

## 核心实现要求

1. 用户端和 Admin 端要有不同侧边栏。
2. 普通用户页面不得显示 Admin 控制入口。
3. `super_admin` mock 用户可以显示 Admin 导航和管理员控制中心。
4. 所有数据先使用 mock data。
5. 所有按钮先做 mock action，可以显示 loading、toast、状态变化。
6. 写作工作台必须是三栏布局：
   - 左侧：章节 / 场景树
   - 中间：正文编辑器
   - 右侧：设定 / 记忆 / 审稿问题
7. 生成任务中心必须体现：
   - workflow
   - 队列
   - 状态
   - 额度预留
   - 额度结算
   - 模型调用摘要
8. 套餐/额度页面必须体现：
   - Plan
   - Feature
   - Entitlement
   - Quota
   - Usage
9. Admin 页面必须体现平台级：
   - 用户
   - 组织
   - 套餐
   - 额度
   - 任务
   - 模型日志
   - 审计日志
10. 代码结构要方便后续接真实 API。

---

## Mock 用户要求

请实现至少两个 mock 用户状态：

```text
普通用户：writer@example.com
- platformRole: user
- organizationRole: owner
- organization: personal-workspace
- plan: Pro

管理员：admin@novelflow.ai
- platformRole: super_admin
- organizationRole: owner
- organization: personal-workspace
- plan: Pro
```

建议提供一个开发阶段切换按钮或配置，用于在普通用户和 super_admin 间切换，以验证 UI 权限显示。

---

## 必须实现的基础组件

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

可以根据项目实际拆分，但功能必须覆盖。

---

## 交付要求

完成后请提供：

1. 项目启动命令。
2. 页面路由清单。
3. Mock 用户切换方式。
4. 已实现页面列表。
5. 未实现或占位页面列表。
6. 主要组件结构说明。
7. 运行结果说明。

请尝试运行并修复错误：

```text
npm run lint
npm run typecheck
npm run build
```

如果项目命令不同，请说明原因并提供实际命令。

---

## 验收标准

1. 所有 P0 路由能访问。
2. 首页普通用户版和管理员版能区分显示。
3. 页面视觉接近 `picture/` 图片。
4. 所有中文 UI 文案清晰可读。
5. 普通用户无法看到 Admin 入口。
6. Admin 页面能显示平台级数据。
7. 写作工作台为三栏布局。
8. 生成任务中心显示 workflow 和 model call 摘要。
9. 套餐/额度页面显示 plan_features 和 quota 调整。
10. 系统设置页面显示 Prompt 版本和 audit_logs。
11. 项目可以正常启动和构建。
