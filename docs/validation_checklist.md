# AI Novel SaaS 端到端验证清单

> 本清单覆盖 Sprint 1 → Sprint 6 全部已实现功能。按顺序执行能验证整条
> "创建项目 → 故事圣经 → 大纲 → 场景计划 → 写作 → 审稿 → 重写 → 导出"
> 业务链路，以及多租户、配额、版本、Admin 运维等横切关注点。
>
> **执行时长估算**：完整跑完约 60-90 分钟（含等待 / 检查 / 截图）。
> 急速冒烟（只走 happy path 不做边界）约 20 分钟。

---

## 0. 环境准备

### 0.1 拉取最新代码

```bash
cd /Users/nanashiwang/Documents/Projects/ai-novel
git pull origin main
git log --oneline -3   # 应该看到最新的 Sprint 6 commits
```

### 0.2 基础设施启动

```bash
# Postgres + Redis + Temporal + MinIO
make infra-up

# 验证容器
docker ps | grep -E "novelflow|temporal|postgres|redis|minio"
```

预期：5 个容器 healthy。

### 0.3 数据库迁移

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
alembic current   # 应该停在 0009_export_file_content
```

预期：迁移链单一 head 0009，无 warning。

### 0.4 种子数据（可选）

```bash
make seed   # 创建 admin 用户、Free/Starter/Pro/Team/Enterprise 五个 plan
```

### 0.5 服务启动

```bash
# 后端
cd backend && uvicorn app.main:app --reload --port 8000

# 前端（另开 terminal）
cd frontend && npm run dev -- --port 13000
```

预期：
- 后端 http://localhost:8000/docs 能打开 Swagger UI
- 前端 http://localhost:13000 能进入登录页

### 0.6 自动化质量门（执行任何手工验证前先跑）

```bash
# 后端：70+ 测试全过
cd backend && .venv/bin/pytest tests/ -q --ignore=tests/test_quota_race_postgres.py
# 预期：70 passed

# 前端：tsc + eslint + vitest
cd frontend
node_modules/.bin/tsc --noEmit
node_modules/.bin/eslint . --max-warnings=0
node_modules/.bin/vitest run
# 预期：tsc 无错，eslint 0 warning，vitest 14/14
```

**任何一项失败前不要进入手工验证。** 自动化失败说明代码层就有问题。

---

## 1. 认证与多租户（Sprint 1 基础设施）

### 1.1 注册首个用户（成为 super_admin）

- 在前端登录页点"注册"
- 填邮箱 `admin@test.local` / 密码 `password123` / 姓名 `Admin`
- ✅ 注册成功并自动登录
- ✅ 顶部右侧可以看到用户头像
- 检查 db：`SELECT platform_role FROM users WHERE email='admin@test.local'` → 应该是 `super_admin`（首用户特权）

### 1.2 注册第二个用户

- 退出登录 → 注册 `user2@test.local`
- ✅ platform_role 应为 `member`，组织 plan_code = `Free`

### 1.3 跨租户隔离

- user2 登录后，不应该看到 admin 的项目
- 在 url 直接访问 admin 项目 id：`/studio/projects/{admin_project_id}` → ✅ 404 或权限拒绝

---

## 2. Sprint 1：StoryBible 闭环

### 2.1 创建项目

- 登录 admin → "新建项目" → 标题`雾城记忆案` / 类型`悬疑幻想` / 目标字数 120000
- ✅ 项目列表立刻显示
- ✅ 项目状态 = `created`
- ✅ Overview 的"下一步动作"卡片应该显示「生成故事圣经」CTA → /bible

### 2.2 生成故事圣经

- 点击 Overview 上的"生成故事圣经"或直接进 `/studio/projects/{id}/bible`
- 点"启动生成"
- ✅ Toast `已提交故事圣经生成任务`
- ✅ 旋转图标显示 1-2 秒
- ✅ Bible 页显示生成的 spec / characters / world_items / plot_threads
- ✅ project.status → `bible_ready`
- ✅ Overview "下一步动作" 切换到「生成章节大纲」

**Bible 页应该出现这些数据（mock provider 固定 fixture）：**
- premise: 一名创作者在失控的记忆城市中追查真相
- 至少 2 个角色（林澈、沈砚）
- 至少 2 个 world_items
- 至少 1 个 plot thread

### 2.3 失败路径

- 进入「任务」页 → 应该能看到 succeeded 的 `generate_bible` 任务
- 任务行的额度列应该显示 `2000/2000`

---

## 3. Sprint 2：Outline 闭环

### 3.1 生成大纲

- Bible 页底部点"前往大纲页" → `/outline`
- 点"启动生成"
- ✅ 章节树显示 6 章左右
- ✅ 每章卡片显示标题 + 摘要
- ✅ project.status → `outlined`

### 3.2 失败回滚验证

- 切换到任务页 → ✅ 看到 succeeded 的 `generate_outline` 任务

---

## 4. Sprint 3：ScenePlan + ContextBuilder

### 4.1 生成单章场景

- 大纲页 → 点某一章卡片 → 右侧场景拆分区
- 点"生成场景计划"
- ✅ 该章生成 3 个 scenes（mock 默认）
- ✅ 每个 scene 卡显示标题 / 地点 / 目标 / 状态=`planned`
- ✅ project.status 不变（仍是 `outlined` — 单章生成不应推进项目级状态）

### 4.2 验证 ContextBuilder 写入了 memory_entries

```sql
SELECT count(*) FROM memory_entries
WHERE project_id = '<project_id>' AND source_type = 'scene';
```

- ✅ 应该等于该章节生成的 scenes 数量（每个 scene 一条摘要）

### 4.3 跨章节多次生成

- 切到另一章重复 → 每章独立生成
- ✅ "重新生成"按钮在该章已有 scenes 时禁用（除非 force_regenerate=true）

---

## 5. Sprint 4-A：WriteScene 闭环

### 5.1 进入写作页

- 顶部导航 → "写作工作台" 或 `/write`
- ✅ 左栏列出 chapters；点击展开显示 scenes
- ✅ 选第一章的第一个 scene
- ✅ 中间区域显示"还没有 draft"占位

### 5.2 生成正文

- 右上"生成当前场景" → 提交
- ✅ Toast 提示 + scene 状态 badge 短暂变 `writing` → `drafted`
- ✅ 中间区域显示 Tiptap 编辑器，渲染 mock 正文
- ✅ 右栏"版本历史"显示 1 个 draft 版本
- ✅ 右栏"ContextBuilder Inspector" 折叠区显示 7 段（hard_constraints / task / characters / world_rules / plot_threads / recent_summary / memory_recall）
- ✅ 各段显示 token budget 与 truncated 标签

### 5.3 验证 draft_versions 父链

- 再次点"重新生成场景"
- ✅ 版本历史新增第 2 版
- ✅ DB 检查：`SELECT id, parent_version_id FROM draft_versions WHERE scene_id='<id>' ORDER BY created_at DESC` — 第 2 版的 parent 应指向第 1 版

---

## 6. Sprint 4-B：Tiptap 编辑器 + 版本面板 + Diff + 自动保存 + 删除

### 6.1 编辑正文 → 手动保存

- 在编辑器内修改一段文字
- ✅ 顶部出现"未保存" 紫色 badge
- ✅ "保存版本"按钮变可点
- 点击保存
- ✅ Toast `已保存为新版本`
- ✅ 版本列表新增 1 条 `user` 类型版本

### 6.2 自动保存 15s

- 再修改一段
- 等 15 秒不点任何按钮
- ✅ 静默生成一个 `autosave` 版本（无 toast，但版本列表+1）

### 6.3 切换历史版本

- 点版本列表的某条历史版本
- ✅ 顶部出现"预览历史版本" 琥珀色 badge
- ✅ 编辑器变只读，显示该版本内容
- ✅ "保存版本"按钮 disabled
- 点"返回最新版本" → 回到 latest，可编辑

### 6.4 Diff 视图

- hover 任一非当前版本卡 → 出现 GitCompare 图标
- 点击 → 中间区域切换到 DiffView，行级红绿差异
- ✅ 顶部显示 `第 X 版 → 第 Y 版`
- 点"退出对比"返回编辑器

### 6.5 删除版本

- hover 某个版本卡 → 出现 Trash2 图标
- 点击 → confirm 弹窗 → 确定
- ✅ Toast `已删除该版本`
- ✅ 该版本从列表消失
- ✅ 若删除的是当前预览版本，自动 fallback 到 latest

---

## 7. Sprint 5-A：审稿 + 重写

### 7.1 触发审稿

- 写作页中部"审稿 & 问题"面板
- 点"审稿"
- ✅ Toast `已提交审稿任务`
- ✅ 1-2 秒后面板显示 2 个 mock issues（continuity / character 各一个，severity=medium 和 low）
- ✅ DB 检查：`SELECT * FROM continuity_issues WHERE scene_id='<id>' AND status='open'` 应该有数据

### 7.2 重写并修复

- "重写并修复"按钮（仅当有 open issues 时可点）
- ✅ Toast `已提交重写任务`
- ✅ 一段时间后版本列表新增一个 `rewrite` 类型版本（parent 指向之前的 latest）
- ✅ 所有 open issues 变 `fixed`（绿色 badge）
- ✅ 编辑器自动切到新版本

### 7.3 审稿失败路径

- 在新 scene（没 draft）的情况下点审稿
- ✅ 任务页能看到 failed 的 `audit_scene` 任务，`error_message` 含 `draft_not_found`
- ✅ 该 job 的 QuotaReservation 已 released

---

## 8. Sprint 5-B：导出

### 8.1 导出 Markdown

- 进入"导出"页或 `/export`
- ✅ 5 个格式卡片：Markdown / TXT 可点，DOCX / EPUB / PDF 灰色显示"Sprint 6 接入"
- 点 Markdown "开始导出"
- ✅ Toast 含文件大小
- ✅ 下方"最近导出文件"表格新增一行 `markdown` / `ready` / 大小 / 时间

### 8.2 下载

- 点导出行的"下载"按钮
- ✅ 浏览器开始下载 `.md` 文件
- ✅ 文件内容包含：项目标题 H1、所有章节标题、所有场景正文

### 8.3 TXT 同样验证

- 同上 → 点 TXT
- ✅ 下载 `.txt`，含 `===` 章节分隔与 `---` 场景分隔

### 8.4 未支持的格式

- 通过 curl 或浏览器 DevTools 直接发：

```bash
curl -X POST http://localhost:8000/api/v1/projects/<pid>/exports \
  -H "Authorization: Bearer <token>" -H "X-Organization-Id: <org>" \
  -H "Content-Type: application/json" -d '{"export_type":"docx"}'
```

- ✅ 404 `export_type_not_supported`

### 8.5 跨租户下载

- 用 user2 的 token 访问 admin 项目的 download URL
- ✅ 404

---

## 9. Sprint 5-C：Admin 模型日志/任务对账

### 9.1 进入 Admin（仅 super_admin）

- 用 admin 账号登录 → 顶部右侧切到 Admin
- ✅ 看到 Admin 侧边栏

### 9.2 模型调用日志

- `/admin/model-calls`
- ✅ 显示所有 model_calls，含 prompt_key / prompt_version
- 在 project_id 过滤框粘贴某项目 id → 仅显示该项目的 calls
- 点某行 job_id 单元格 → ✅ 自动 drill-down 到该 job 的所有 model_calls

### 9.3 任务管理

- `/admin/generation-jobs`
- ✅ 显示所有 generation_jobs
- 用 status 下拉选 `failed` → 仅显示失败任务
- 任意 failed 任务点"取消"按钮（只有 queued/running 才有意义；UI 按合约约束）

---

## 10. Sprint 6：Retry + Admin Audit

### 10.1 触发一个失败任务

最容易的方式：把后端 model_gateway_mode 改为 `real` 但不配 API key，然后触发任何生成（会 401）：

```bash
# 或者直接停掉 redis/temporal/postgres 之一，再生成
make infra-down
```

任意触发一个 generate_bible → 会因为基础设施不通而失败。

恢复 `make infra-up` 后：

### 10.2 Retry

- 任务页 → failed 任务行 → ✅ 出现"重试"按钮（绿色 secondary）
- 点击
- ✅ Toast `已重新提交任务（generate_bible）`
- ✅ 任务列表新增 queued 状态新任务
- DB 检查：`SELECT input_payload->>'retry_of' FROM generation_jobs WHERE id='<new_id>'` → 应该等于旧 job id

### 10.3 拒绝 retry succeeded 任务

```bash
curl -X POST http://localhost:8000/api/v1/generation-jobs/<succeeded_job_id>/retry \
  -H "Authorization: Bearer <token>" -H "X-Organization-Id: <org>"
```

- ✅ 409 `conflict`，error code `conflict` 信息 `job_not_retryable`

### 10.4 Admin Settings Audit

- Admin → 系统设置 → 修改模型网关（例如把 default_model 改为另一个）
- ✅ 保存成功
- DB 检查：

```sql
SELECT action, before_data, after_data FROM admin_audit_logs
WHERE action = 'model_gateway:update'
ORDER BY created_at DESC LIMIT 1;
```

- ✅ before_data / after_data 反映本次修改的字段差异
- ✅ 敏感字段（api_key）**不在** before_data / after_data，仅 `*_api_key_configured` 布尔位

---

## 11. 横切验证

### 11.1 契约一致性

```bash
cd backend
.venv/bin/pytest tests/test_contract_consistency.py -v
# 预期：5 passed
```

如果失败：说明代码里有未登记的字面量，应同步 `backend/app/contracts.py` 与 `docs/api_contract_v1.md`。

### 11.2 测试覆盖度统计

```bash
.venv/bin/pytest tests/ -q --ignore=tests/test_quota_race_postgres.py | tail -3
# 预期：70 passed
```

测试分布（应基本覆盖所有关键路径）：
- conftest + admin_plans + admin_settings + auth + healthz + http + nav + permissions + projects + refresh + organizations + tenancy + story_pipeline (~30)
- generate_bible_flow: 5
- generate_outline_flow: 5
- generate_scene_plan_flow: 7
- write_scene_flow: 5
- audit_rewrite_flow: 5
- export_flow: 6
- retry_job_flow: 3
- contract_consistency: 5

### 11.3 迁移链

```bash
.venv/bin/python -c "
from alembic.config import Config
from alembic.script import ScriptDirectory
cfg = Config('alembic.ini')
script = ScriptDirectory.from_config(cfg)
print('heads:', script.get_heads())
print('chain:')
for rev in reversed(list(script.walk_revisions())):
    print(f'  {rev.revision} <- {rev.down_revision or \"<base>\"}')"
```

- ✅ 单一 head: `0009_export_file_content`
- ✅ 链路：`0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009`

### 11.4 失败路径自动回归

每个 Sprint 都有失败路径测试。重点验证："失败 → quota 释放 → project.status 回滚（如适用）"链路：

```bash
.venv/bin/pytest tests/ -k "fail" -v 2>&1 | grep -E "PASSED|FAILED"
```

- ✅ 所有 `*_release*_on_failure` / `*_releases_quota_on_failure` 测试全过

### 11.5 contract lint 真实拦截

故意添加一个未登记的 error code，验证 lint 抓住：

```bash
# 在任何 service 文件加 `raise NotFoundError("my_bogus_code")`，然后
.venv/bin/pytest tests/test_contract_consistency.py -v
# 预期：失败，明确指出 file:line 与字面量
# 测试完撤销改动
```

---

## 12. 已知限制（不在本次验证范围）

| 限制 | 状态 | 何时处理 |
|---|---|---|
| MinIO 真实上传 | Sprint 5-B 用 db 存 content 代替；MinIO 已在 docker-compose 但未接入 | 真实部署阶段 |
| pgvector HNSW v2 召回 | ContextBuilder.memory_recall 段保留空占位 | Sprint 7+ |
| Prometheus metrics endpoint | 未实现；structlog 已有 JSON 日志 | 接 OpenTelemetry 时 |
| docx / epub / pdf 导出 | 灰色禁用 | 需要引入 python-docx / ebooklib 等 |
| 真实 Temporal worker 启动 | TEMPORAL_ENABLED=false 走 after_commit 本地 dispatch；workflows 真实跑需要 worker 进程 | staging 部署 |
| 接受 / 拒绝 AI 候选版本（diff 后选择） | Sprint 4-B2 改为"每次生成都是新版本，不喜欢删除"的等价模型 | 不计划 |

---

## 13. 验证通过的判据

至少满足下面 4 条才算 v1 staging-ready：

1. ✅ 自动化质量门全过（pytest 70/70 + 前端三个工具）
2. ✅ 端到端旅程章节 2-8 完全跑通（从 created 到 drafting 到导出下载）
3. ✅ 跨租户隔离测试章节 1.3 / 8.5 / 10.3 通过
4. ✅ 失败回滚链路章节 7.3 / 11.4 通过

任何一条失败，**不要上 staging**。
