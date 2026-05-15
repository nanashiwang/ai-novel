# Codex 前端交接检查清单

> 用途：在把项目交给 Codex 前，确认资料是否完整。  
> 建议位置：`docs/codex_handoff_checklist.md`

---

## 1. 当前应该具备的文件

仓库根目录建议包含：

```text
AGENTS.md
codex_first_task_prompt.md 或 codex_frontend_task_prompt.md
README.md
```

`docs/` 目录建议包含：

```text
docs/ai_novel_saas_final_architecture.md
docs/ai_novel_saas_ui_spec.md
docs/ai_novel_saas_ui_image_prompts_standalone_v2.md
docs/ui_image_manifest.md
docs/frontend_implementation_spec.md
docs/mock_data_schema.md
docs/codex_handoff_checklist.md
```

`picture/` 目录建议包含：

```text
picture/01_auth_login_register.png
picture/02_studio_dashboard_admin_visible.png
picture/03_studio_dashboard_user_only.png
picture/04_project_create_wizard.png
picture/05_project_overview.png
picture/06_writing_workspace.png
picture/08_characters_relationships.png
picture/10_outline_planner.png
picture/12_generation_jobs.png
picture/14_export_center.png
picture/17_admin_dashboard.png
picture/19_admin_plans_entitlements_quotas.png
picture/22_admin_system_settings_audit_logs.png
```

---

## 2. 交给 Codex 前的整理动作

1. 把 UI 图片统一放入 `picture/`。
2. 尽量按建议文件名重命名图片。
3. 把新增的三个规格文件放入 `docs/`：
   - `ui_image_manifest.md`
   - `frontend_implementation_spec.md`
   - `mock_data_schema.md`
4. 把 `codex_frontend_task_prompt.md` 放在根目录或 `docs/`。
5. 确认 `AGENTS.md` 在仓库根目录。
6. 确认架构文档和 UI 规格文档都在 `docs/`。

---

## 3. 第一轮 Codex 任务边界

第一轮只做：

```text
前端 UI 壳
路由
布局
mock 数据
mock 用户权限
mock 任务状态
mock 按钮反馈
```

第一轮不要做：

```text
后端
数据库
GPT API
支付
Temporal
真实导出
真实登录
```

---

## 4. 第一轮 Codex 完成后需要检查

### 路由检查

必须能访问：

```text
/auth/login
/auth/register
/studio
/studio/projects
/studio/projects/new
/studio/projects/project_fog_archive
/studio/projects/project_fog_archive/write
/studio/projects/project_fog_archive/jobs
/studio/projects/project_fog_archive/outline
/studio/projects/project_fog_archive/characters
/studio/projects/project_fog_archive/export
/admin
/admin/plans
/admin/quotas
/admin/settings
/admin/audit-logs
```

### 角色检查

普通用户：

```text
不能看到 Admin 导航
不能看到管理员控制中心
访问 /admin 显示权限不足或重定向
```

super_admin：

```text
能看到 Admin 导航
能进入 Admin Console
能看到系统设置保存按钮
能看到管理员控制中心
```

### 页面检查

1. `/studio` 是否有普通用户版和管理员版差异。
2. `/studio/projects/new` 是否有完整表单和套餐额度检查。
3. `/studio/projects/[projectId]` 是否有项目状态和章节进度。
4. `/studio/projects/[projectId]/write` 是否为三栏布局。
5. `/studio/projects/[projectId]/jobs` 是否有 workflow 和 model calls。
6. `/studio/projects/[projectId]/export` 是否有导出格式和 final 版本提示。
7. `/admin` 是否是平台级数据。
8. `/admin/plans` 是否有 plan_features。
9. `/admin/quotas` 是否有手动额度调整。
10. `/admin/settings` 是否有模型配置和 Prompt 版本。
11. `/admin/audit-logs` 是否有审计日志表格。

---

## 5. 第二轮 Codex 任务建议

第一轮 UI 壳完成后，第二轮再做：

```text
后端 SaaS 底座
数据库 schema
Auth mock → Auth API
Organization / Membership
RBAC
Plan / Entitlement / Quota
Project API
GenerationJob API
Model Gateway mock
```

不要在第一轮就让 Codex 同时做后端和真实 GPT。

---

## 6. 第三轮 Codex 任务建议

第二轮底座完成后，再做：

```text
GPT Model Gateway
Prompt Manager
Temporal Workflow 或任务队列
GenerateBibleWorkflow
GenerateOutlineWorkflow
WriteSceneWorkflow
Usage Meter
Quota Reservation / Settlement
```

---

## 7. 最终提醒

这个项目的核心不是“页面好看”，而是长期能支撑：

```text
多租户
权限
套餐
额度
自动小说生成 workflow
模型调用日志
记忆系统
审稿重写
Admin 运营后台
```

所以第一阶段 UI 也必须从一开始体现这些架构概念。
