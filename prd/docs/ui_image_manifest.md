# UI 图片与路由映射清单

> 用途：交给 Codex / 前端生成 Agent，明确 `picture/` 目录下每张 UI 图片对应的页面、路由、角色状态、实现优先级与还原重点。  
> 建议位置：`docs/ui_image_manifest.md`  
> 图片建议位置：`picture/`，也可以改为 `docs/ui-mockups/`。  
> 当前版本：v2，已同步完整图片目录：`01` 至 `20`、`22`，以及 `登录页插图.png`。

---

## 1. 使用原则

1. 所有 UI 图片只作为**前端视觉、布局和信息架构参考**，第一阶段不接真实后端。
2. Codex 实现时应优先还原：
   - 页面结构
   - 左右布局
   - 卡片层级
   - 表格字段
   - 状态 badge
   - 进度条
   - 中文文案
   - 权限 / 套餐 / 额度 / 任务状态表现
   - 用户端 Studio 与 Admin Console 的视觉差异
3. 若图片和架构文档冲突，以 `docs/ai_novel_saas_final_architecture.md` 为准。
4. 若图片和 UI 规格文档冲突，以 `docs/ai_novel_saas_ui_spec.md` 为准。
5. 若图片和 `docs/frontend_implementation_spec.md` 冲突，以 `docs/frontend_implementation_spec.md` 的路由、权限和技术约束为准。
6. 若实际图片文件名不同，请先重命名为本清单中的建议文件名，或者在本文件中更新实际文件名。
7. 第一阶段只实现 UI 壳、mock 数据、mock auth、mock action，不接真实数据库、GPT API、支付、Temporal 或真实文件导出。
8. 所有普通用户页面不得显示 Admin 控制入口；`super_admin` mock 用户可以显示 Admin 导航和管理员控制中心。
9. `picture/登录页插图.png` 是素材图，不是独立页面，可用于登录页左侧小说氛围图。

---

## 2. 推荐图片目录结构

```text
picture/
├── 01_auth_login_register.png
├── 02_studio_dashboard_admin_visible.png
├── 03_studio_dashboard_user_only.png
├── 04_project_create_wizard.png
├── 05_project_overview.png
├── 06_writing_workspace.png
├── 07_story_bible.png
├── 08_characters_relationships.png
├── 09_world_lorebook.png
├── 10_outline_planner.png
├── 11_scene_context_builder.png
├── 12_generation_jobs.png
├── 13_versions_and_audit_issues.png
├── 14_export_center.png
├── 15_billing_usage.png
├── 16_account_organization_settings.png
├── 17_admin_dashboard.png
├── 18_admin_users_organizations.png
├── 19_admin_plans_entitlements_quotas.png
├── 20_admin_jobs_model_calls.png
├── 22_admin_system_settings_audit_logs.png
└── 登录页插图.png
```

说明：

```text
21_admin_content_review_risk_control.png
```

当前目录中没有该图片。第一阶段仍需要实现 `/admin/content-review` 路由，但可以先基于 `17_admin_dashboard.png`、`20_admin_jobs_model_calls.png` 和 `22_admin_system_settings_audit_logs.png` 的 Admin 风格做简版占位页。

---

## 3. 已完成图片与页面映射

| 优先级 | 图片文件名 | 路由 | 页面名称 | 角色 / 权限状态 | 实现重点 |
|---:|---|---|---|---|---|
| P0 | `01_auth_login_register.png` | `/auth/login`, `/auth/register` | 登录 / 注册页 | 访客；低调显示管理员入口 | 左右分屏、小说氛围图、登录注册表单、第三方登录 mock、注册后创建个人组织并绑定 Free 套餐说明 |
| Asset | `登录页插图.png` | `/auth/login`, `/auth/register` | 登录页左侧插图素材 | 访客 | 可作为登录页左侧背景素材或氛围图，不作为独立页面实现 |
| P0 | `02_studio_dashboard_admin_visible.png` | `/studio` | 创作工作台首页：管理员可见版 | `super_admin` + `organization.owner` | 普通创作入口 + 管理员控制中心；侧边栏分普通导航和管理员导航；顶部显示组织、角色、套餐、额度 |
| P0 | `03_studio_dashboard_user_only.png` | `/studio` | 创作工作台首页：普通用户版 | 普通用户，不是平台管理员 | 只显示项目、任务、套餐、额度和创作快捷操作；不得显示管理员入口 |
| P0 | `04_project_create_wizard.png` | `/studio/projects/new` | 新建小说项目向导 | 普通用户；可选管理员弱提示 | 4 步 stepper、项目表单、创建后自动生成预览、套餐额度检查、保存草稿、取消、创建并生成故事圣经 |
| P0 | `05_project_overview.png` | `/studio/projects/[projectId]` | 项目总览页 | 项目成员；管理员动作仅在更多菜单 | 项目状态、生成控制、章节进度、审稿问题、项目内 tabs、状态机、Workflow 日志入口 |
| P0 | `06_writing_workspace.png` | `/studio/projects/[projectId]/write` | 核心写作工作台 | 项目编辑者 | 三栏布局：章节 / 场景树、正文编辑器、设定 / 记忆 / 审稿栏；scene 级生成；底部任务日志 / 模型调用摘要 |
| P1 | `07_story_bible.png` | `/studio/projects/[projectId]/bible` | 故事圣经页 | 项目编辑者 | Premise、Theme、核心卖点、主线冲突、叙事规则、文风规则、禁忌内容、故事圣经版本与生成按钮 |
| P1 | `08_characters_relationships.png` | `/studio/projects/[projectId]/characters` | 人物关系与角色状态页 | 项目编辑者；管理员仅审核视图 | 人物卡、人物关系图、角色状态、章节时间线、Memory Engine 自动更新提示 |
| P1 | `09_world_lorebook.png` | `/studio/projects/[projectId]/world` | 世界观 / Lorebook 页 | 项目编辑者 | 世界观条目、地点、组织、规则、物品、能力体系、Lorebook 检索、相关人物与章节引用 |
| P1 | `10_outline_planner.png` | `/studio/projects/[projectId]/outline` | 大纲规划器 | 项目编辑者 | 卷 / 章 / 场景三级结构、章节详情、场景拆分、生成控制、额度预估、权限 badge |
| P1 | `11_scene_context_builder.png` | `/studio/projects/[projectId]/write` 或 `/studio/projects/[projectId]/memory` | 场景上下文构建页 / 写作上下文面板 | 项目编辑者 | Context Builder、人物状态、世界观召回、前文摘要、相关伏笔、生成上下文预览；可作为写作页右侧或底部面板实现 |
| P0 | `12_generation_jobs.png` | `/studio/projects/[projectId]/jobs` | 生成任务中心 | 项目成员；管理员可额外强制操作 | Workflow、队列、任务状态、额度预留 / 结算、模型调用摘要、取消任务、重试任务、查看完整日志 |
| P1 | `13_versions_and_audit_issues.png` | `/studio/projects/[projectId]/versions` | 版本历史 / 审稿问题页 | 项目编辑者 | draft_versions、final_versions、版本对比、回滚、审稿问题列表、问题状态、修复建议 |
| P1 | `14_export_center.png` | `/studio/projects/[projectId]/export` | 导出中心 | 项目编辑者 | Markdown、TXT、DOCX、EPUB、PDF；导出配置、套餐权益、最近导出文件、导出来源 final 版本 |
| P1 | `15_billing_usage.png` | `/studio/billing`, `/studio/usage` | 套餐与用量页 | 组织 owner / billing_manager；普通成员只读 | 当前套餐、Plan、Feature、Entitlement、Quota、Usage、额度进度、升级入口、用量趋势 |
| P1 | `16_account_organization_settings.png` | `/studio/account` | 账号 / 组织设置页 | 组织 owner / member；owner 可编辑更多设置 | 用户资料、组织信息、成员、组织角色、API Key 预留、通知设置、组织状态 |
| P0 | `17_admin_dashboard.png` | `/admin` | Admin 后台总览 | `admin` / `super_admin` | 平台级运营数据、注册用户、付费组织、今日生成字数、失败任务、趋势图、运营告警、最新生成任务、系统状态 |
| P0 | `18_admin_users_organizations.png` | `/admin/users`, `/admin/organizations` | Admin 用户与组织管理页 | `admin` / `super_admin`；support 可只读 | 用户列表、组织列表、状态、角色、封禁 / 恢复、套餐切换、额度查看、组织成员管理 |
| P0 | `19_admin_plans_entitlements_quotas.png` | `/admin/plans`, `/admin/quotas` | Admin 套餐 / 权益 / 额度管理 | `finance_admin` / `admin` / `super_admin` 可改；`operator` 只读 | 套餐列表、套餐详情、plan_features 表格、额度配置、手动额度调整、审计提示 |
| P0 | `20_admin_jobs_model_calls.png` | `/admin/generation-jobs`, `/admin/model-calls` | Admin 生成队列 / 模型调用日志页 | `admin` / `super_admin` | 平台级任务队列、强制取消、强制重试、model_calls、Prompt / Response 预览、组织用量入口 |
| P0 | `22_admin_system_settings_audit_logs.png` | `/admin/settings`, `/admin/audit-logs` | Admin 系统设置与审计日志 | `super_admin` 可改；普通 `admin` 只读或 disabled | 模型配置、Prompt 版本、队列配置、权限矩阵、audit_logs、系统设置权限边界 |

---

## 4. 同一路由的角色差异

### 4.1 `/studio`

`/studio` 有两个视觉版本：

| 用户状态 | 使用图片 | 说明 |
|---|---|---|
| 当前用户是 `super_admin` 或 `admin` | `02_studio_dashboard_admin_visible.png` | 显示管理员导航组和管理员控制中心 |
| 当前用户不是平台管理员 | `03_studio_dashboard_user_only.png` | 隐藏所有管理员入口，只显示创作功能 |

前端实现建议：

```ts
const isPlatformAdmin = ['admin', 'super_admin'].includes(currentUser.platformRole)
const isSuperAdmin = currentUser.platformRole === 'super_admin'
```

根据 `isPlatformAdmin` 控制：

```text
是否显示 Admin 导航组
是否显示管理员控制中心
是否显示 /admin 入口
是否显示平台级操作按钮
```

### 4.2 `/admin/settings`

`/admin/settings` 和 `/admin/audit-logs` 需要区分 `super_admin` 与普通 `admin`：

| 用户状态 | UI 行为 |
|---|---|
| `super_admin` | 可以点击保存系统设置、编辑模型配置、编辑队列配置 |
| `admin` | 可以查看设置，但保存按钮 disabled，并显示锁图标 |
| 非平台管理员 | 访问 `/admin/*` 显示权限不足或重定向到 `/studio` |

### 4.3 用户端项目页面的管理员动作

项目内页面可以为管理员提供低调的更多菜单，例如：

```text
查看 model_calls
查看 organization 用量
强制取消任务
查看完整 Prompt
标记内容审核
```

但这些动作必须放在更多菜单或审核视图中，不得影响普通用户主流程。

---

## 5. 当前没有单独图片但仍需实现的页面

以下页面没有独立图片，或图片只覆盖部分状态。第一阶段应基于已有图片和 UI 规格文档完成简版实现。

| 路由 | 页面 | 可参考图片 | 第一阶段实现要求 |
|---|---|---|---|
| `/studio/projects` | 项目列表页 | `03_studio_dashboard_user_only.png`, `05_project_overview.png` | 从首页“最近小说项目”扩展为完整项目列表；包含筛选、搜索、状态、操作 |
| `/studio/projects/[projectId]/memory` | 长期记忆页，可选 | `11_scene_context_builder.png`, `06_writing_workspace.png` | 如果实现该路由，展示 Memory Engine、记忆类型、召回内容、重要性；如果不实现，`11` 图用于写作页上下文面板 |
| `/studio/projects/[projectId]/issues` | 审稿问题页，可选 | `13_versions_and_audit_issues.png` | 如果实现该路由，展示 continuity_issues 筛选、详情、重写入口；第一阶段也可合并到 `/versions` |
| `/admin/content-review` | 内容审核 / 风控页 | `17_admin_dashboard.png`, `20_admin_jobs_model_calls.png`, `22_admin_system_settings_audit_logs.png` | 必须有路由；第一阶段可做简版：待审核内容、风险等级、处理动作、审核日志 |
| `/admin/subscriptions` | 订阅管理页，后续增强 | `19_admin_plans_entitlements_quotas.png` | 第一阶段可不实现或占位；后续显示订阅状态、支付渠道、发票 |
| `/admin/invoices` | 发票页，后续增强 | `19_admin_plans_entitlements_quotas.png` | 第一阶段可不实现或占位 |
| `/admin/payment-events` | 支付事件页，后续增强 | `22_admin_system_settings_audit_logs.png` | 第一阶段可不实现或占位 |

---

## 6. 页面实现优先级

### 6.1 P0：第一阶段必须实现并重点还原

```text
/auth/login
/auth/register
/studio
/studio/projects
/studio/projects/new
/studio/projects/[projectId]
/studio/projects/[projectId]/write
/studio/projects/[projectId]/jobs
/admin
/admin/users
/admin/organizations
/admin/plans
/admin/quotas
/admin/generation-jobs
/admin/model-calls
/admin/settings
/admin/audit-logs
```

### 6.2 P1：第一阶段必须实现，但可略低保真

```text
/studio/projects/[projectId]/bible
/studio/projects/[projectId]/characters
/studio/projects/[projectId]/world
/studio/projects/[projectId]/outline
/studio/projects/[projectId]/versions
/studio/projects/[projectId]/export
/studio/billing
/studio/usage
/studio/account
/admin/content-review
```

### 6.3 P2：后续增强或占位

```text
/studio/projects/[projectId]/memory
/studio/projects/[projectId]/issues
/admin/subscriptions
/admin/invoices
/admin/payment-events
/admin/system-health
/admin/risk-control
```

---

## 7. Codex 实现时的重点参考图片

第一阶段视觉重点优先参考以下图片：

```text
picture/01_auth_login_register.png
picture/02_studio_dashboard_admin_visible.png
picture/03_studio_dashboard_user_only.png
picture/04_project_create_wizard.png
picture/05_project_overview.png
picture/06_writing_workspace.png
picture/12_generation_jobs.png
picture/17_admin_dashboard.png
picture/19_admin_plans_entitlements_quotas.png
picture/20_admin_jobs_model_calls.png
picture/22_admin_system_settings_audit_logs.png
```

第二优先级参考：

```text
picture/07_story_bible.png
picture/08_characters_relationships.png
picture/09_world_lorebook.png
picture/10_outline_planner.png
picture/11_scene_context_builder.png
picture/13_versions_and_audit_issues.png
picture/14_export_center.png
picture/15_billing_usage.png
picture/16_account_organization_settings.png
picture/18_admin_users_organizations.png
```

登录页如需使用左侧氛围图，可参考：

```text
picture/登录页插图.png
```

---

## 8. 图片还原验收标准

Codex 完成第一阶段前端 UI 后，需要检查：

1. 所有 P0 路由能访问。
2. 所有 P1 路由能访问，至少有完整布局和 mock 数据。
3. 图片对应页面的主体布局基本一致。
4. 用户端和 Admin 端侧边栏明显不同。
5. 普通用户看不到 Admin 控制入口。
6. `super_admin` 能看到 Admin 导航和管理员控制中心。
7. 所有页面中文文案清晰、无乱码。
8. 所有数据来自 mock data，不接真实 API。
9. 按钮有 mock loading、mock toast 或 mock 状态变化。
10. 写作工作台必须是三栏布局。
11. 写作工作台必须体现 scene 是最小生成单位。
12. 生成任务中心必须体现 workflow，而不是普通 HTTP 请求列表。
13. 生成任务中心必须显示额度预留、实际消耗和释放额度。
14. 模型调用日志必须显示 task_type、model、input、output、latency、status。
15. 套餐/额度页面必须体现 Plan、Feature、Entitlement、Quota、Usage。
16. Admin 页面必须体现平台级数据，而不是单项目数据。
17. 系统设置页面必须显示 Prompt 版本、模型配置、队列配置和 audit_logs。
18. 所有管理员破坏性操作必须有二次确认或至少 mock confirm。
19. 额度调整、套餐修改、系统设置保存等管理员操作需要提示“将写入 audit_logs”。
20. 普通用户访问 `/admin/*` 应显示权限不足或自动重定向。

---

## 9. 给 Codex 的补充实现说明

Codex 实现 UI 时必须注意：

```text
1. 不要把 NovelFlow AI 做成聊天应用。
2. 不要把 Admin Console 和用户 Studio 混成同一个布局。
3. 不要让普通用户看到 Admin 导航。
4. 不要把套餐权益写死在组件里，应通过 mock plan_features / entitlements 驱动。
5. 不要把生成任务做成普通同步请求，必须展示 workflow steps。
6. 不要在列表页直接塞超长 Prompt / Response，使用详情抽屉或弹窗。
7. 所有长任务操作必须有确认弹窗。
8. 写作工作台必须支持章节 / 场景 / 版本三层结构。
9. 导出中心必须明确“导出来源：final 版本”。
10. Admin 系统设置必须体现 super_admin 与普通 admin 的权限差异。
```

---

## 10. 当前图片完整性检查

当前 `picture/` 目录已经覆盖第一阶段主要 UI：

```text
Auth
Studio Dashboard
Project Create
Project Overview
Writing Workspace
Story Bible
Characters
World / Lorebook
Outline
Context Builder
Generation Jobs
Versions / Audit Issues
Export
Billing / Usage
Account / Organization Settings
Admin Dashboard
Admin Users / Organizations
Admin Plans / Entitlements / Quotas
Admin Jobs / Model Calls
Admin Settings / Audit Logs
```

当前唯一建议后续补图的是：

```text
21_admin_content_review_risk_control.png
```

但这张不是第一阶段阻塞项。可以先让 Codex 基于 Admin 视觉规范实现 `/admin/content-review` 简版占位页。
