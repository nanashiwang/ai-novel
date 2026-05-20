# AI Novel API Contract v1

> 单一真相源（Single Source of Truth）。前端、后端、Admin、测试、运维脚本必须以本文档为准。
> 任何契约级修改（新增端点、新增枚举值、改名、改字段语义）必须先更新本文档，再写代码。

**版本**：v1
**冻结日期**：2026-05-19
**对应 Sprint 范围**：Sprint 1（已实现）→ Sprint 6（占位路由提前登记）
**维护原则**：v1 内向后兼容；不兼容变更走 v2 路径，v1/v2 并行至少一个 Sprint 后再下线 v1。
**代码侧真相源**：`backend/app/contracts.py` 镜像本文档的枚举值集合；
`backend/tests/test_contract_consistency.py` 通过 lint 自动校验代码中
所有 `job_type=` / `project.status=` / `raise XxxError(...)` 等字面量
都已在本文档（与 contracts.py）中登记。**新增枚举值必须同时更新两处**。

---

## 1. 通用约定

### 1.1 路由前缀

所有业务 API 在 `/api/v1` 下。Admin 端在 `/api/v1/admin` 下。

### 1.2 认证与多租户

| 头 | 必需 | 用途 |
|---|---|---|
| `Authorization: Bearer <jwt>` | 业务 API 必需 | 15 分钟 access token |
| `X-Organization-Id: org_xxx` | 业务 API 必需 | 当前操作的组织上下文 |
| Cookie `refresh_token` | refresh 必需 | 7 天 httpOnly cookie |

未提供 `X-Organization-Id` 时，后端按用户的默认 organization 推断；用户跨多个 organization 时**必须**显式提供。

### 1.3 长任务约定

任何调用模型的生成请求：

- **返回 `202 Accepted`**，body 形如 `GenerationJobResponse`（含 `id`, `workflow_id`, `status="queued"`, `reserved_quota`）。
- 前端通过 `GET /api/v1/generation-jobs/{id}` 轮询；未来引入 SSE 时端点保持不变。
- **不返回** 模型生成的最终结果；结果通过对应资源端点（如 `GET /projects/{id}/bible`）读取。

### 1.4 错误响应

统一形如：

```json
{
  "error": {
    "code": "quota_insufficient",
    "message": "...",
    "details": { "quota_key": "...", "requested": 2000, "available": 1200 }
  }
}
```

`code` 是稳定的机器可读标识；`message` 是面向开发者的英文/中文混合描述；`details` 是与该 code 强绑定的结构化补充信息。前端基于 `code` 分支，**不要解析 `message`**。

### 1.5 HTTP 状态码约定

| 状态 | 用途 |
|---|---|
| `200` | 同步读取/写入成功 |
| `201` | 资源创建成功 |
| `202` | 长任务已接受（生成类） |
| `204` | 删除成功 |
| `400` | 请求语法/字段错误（非业务） |
| `401` | 未认证（token 缺失/过期） |
| `402` | 额度/付费不足（`quota_insufficient`, `quota_not_in_plan`） |
| `403` | 已认证但无权限（`permission_denied`） |
| `404` | 资源不存在或不属于当前 tenant（避免 enumeration 攻击） |
| `409` | 资源状态冲突（如 job 已结束仍要取消） |
| `422` | Pydantic schema 校验失败（`validation_error`） |
| `429` | 速率限制 |
| `500` | 服务器未捕获异常 |

---

## 2. 路由清单

✅ = 已实现并测试覆盖；🟡 = 后续 Sprint 占位（路由保留，未来实现时必须用同一路径）；⚪ = 前端占位，尚未接后端。

### 2.1 认证 `/api/v1/auth`

| 方法 | 路径 | 状态 | 说明 |
|---|---|---|---|
| POST | `/register` | ✅ | 注册 + 自动签发 token |
| POST | `/login` | ✅ | 邮箱密码登录 |
| POST | `/refresh` | ✅ | 用 refresh cookie 换新 access token |
| POST | `/logout` | ✅ | 注销 refresh token |
| GET | `/me` | ✅ | 当前用户 + 默认 organization |

### 2.2 组织 `/api/v1/organizations`

| 方法 | 路径 | 状态 |
|---|---|---|
| GET | `/` | ✅ |
| GET | `/current` | ✅ |
| PATCH | `/current` | ✅ |
| GET | `/current/members` | ✅ |
| POST | `/current/members` | ✅ |
| DELETE | `/current/members/{member_id}` | ✅ |
| POST | `/invitations/accept` | ✅ |

### 2.3 项目 `/api/v1/projects`

| 方法 | 路径 | 状态 | Sprint |
|---|---|---|---|
| GET | `/` | ✅ | 1 |
| POST | `/` | ✅ | 1 |
| GET | `/{project_id}` | ✅ | 1 |
| DELETE | `/{project_id}` | ✅ | 1 |
| GET | `/{project_id}/bible` | ✅ | 1 |
| POST | `/{project_id}/bible/generate` | ✅ | 1 |
| POST | `/{project_id}/outline/generate` | ✅ | 2 |
| POST | `/{project_id}/chapters/{chapter_id}/scenes/generate` | ✅ | 3 |
| POST | `/{project_id}/scenes/{scene_id}/write` | ✅ | 1 / 升级 4 |
| POST | `/{project_id}/scenes/{scene_id}/audit` | ✅ | 5-A |
| POST | `/{project_id}/scenes/{scene_id}/rewrite` | ✅ | 5-A |
| POST | `/{project_id}/generate-full-novel` | ✅ | 1 |
| POST | `/{project_id}/exports` | ✅ | 5-B |
| GET | `/{project_id}/exports/{export_id}/download` | ✅ | 5-B |

**Sprint 3 关键决策**：scene-plan 是**章节级**而非项目级（`POST /projects/{pid}/chapters/{cid}/scenes/generate`），用户可逐章生成 scene cards 而不影响项目级状态机。项目级"为整本一次性拆 scenes"仍由 full_novel pipeline 处理。

### 2.4 项目子资源

| 路径前缀 | 主要端点 | 状态 |
|---|---|---|
| `/projects/{id}/spec` | GET, PUT | ✅ |
| `/projects/{id}/characters` | GET, POST, PATCH, DELETE | ✅ |
| `/projects/{id}/world-items` | GET, POST, PATCH, DELETE | ✅ |
| `/projects/{id}/volumes` | GET, POST | ✅ |
| `/projects/{id}/chapters` | GET, POST, GET/{id}, PATCH/{id}, DELETE/{id} | ✅ |
| `/projects/{id}/scenes` | GET, POST, GET/{id}, PATCH/{id}, DELETE/{id} | ✅ |
| `/projects/{id}/memory` | GET, POST | ✅（壳） / 升级 3-6 |
| `/projects/{id}/continuity-issues` | GET | ✅（壳） / 升级 5 |
| `/projects/{id}/versions` | GET, POST, GET/{id} | ✅ |
| `/projects/{id}/exports` | GET, POST, GET/{id} | ✅（壳） / 升级 5 |

### 2.5 任务 `/api/v1/generation-jobs`

> **命名冻结**：使用 `generation-jobs`，不使用 `jobs`。任何引用必须用这个全称。

| 方法 | 路径 | 状态 |
|---|---|---|
| GET | `/` | ✅ |
| GET | `/{job_id}` | ✅ |
| POST | `/{job_id}/cancel` | ✅ |
| POST | `/{job_id}/retry` | ✅ 6 |

### 2.6 计费 `/api/v1/billing` 与 `/api/v1/quotas`

| 路径 | 状态 |
|---|---|
| `GET /billing/plans` | ✅ |
| `POST /billing/checkout-session` | ✅（待接真实支付网关） / 升级未排期 |
| `GET /quotas` | ✅ |
| `GET /usage` | ✅ |
| `GET /entitlements` | ✅ |

### 2.7 Admin `/api/v1/admin`

| 路径 | 状态 |
|---|---|
| `GET /admin/users` | ✅ |
| `GET /admin/organizations`, `PATCH /admin/organizations/{id}/quota` | ✅ |
| `GET /admin/plans`, `POST /admin/plans`, `PUT /admin/plans/{id}` | ✅ |
| `GET /admin/generation-jobs`, `POST /admin/generation-jobs/{id}/cancel` | ✅ |
| `GET /admin/settings/model-gateway`, `PUT /admin/settings/model-gateway` | ✅ |
| `GET /admin/model-calls` | ✅ |
| `GET /admin/audit-logs` | ✅ |
| `GET /admin/content-reviews` | ✅（壳） / 升级 6 |

---

## 3. 关键请求/响应 Schema

权威定义在 `backend/app/schemas/`。本节仅列**Sprint 2 关键新增**的 outline 端点契约。

### 3.1 `POST /projects/{project_id}/outline/generate`

请求：

```json
{
  "target_chapters": 48,
  "force_regenerate": false,
  "estimate_words": 3000
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `target_chapters` | int | 否 | project.target_chapter_count 或 6 | 期望章节数，服务端上限 200 |
| `force_regenerate` | bool | 否 | false | 若已有 chapters 且未设为 true，走 reuse 分支 |
| `estimate_words` | int | 否 | 3000 | 用于 quota 预留 |

响应（**202**）：`GenerationJobResponse`（同 generate_bible）。

错误：

| code | HTTP | 触发条件 |
|---|---|---|
| `project_not_found` | 404 | project 不存在或不属于当前 tenant |
| `novel_spec_not_found` | 404 | 未先完成 generate_bible |
| `quota_insufficient` | 402 | 月生成额度不足 |
| `quota_not_in_plan` | 402 | 当前 plan 不开放生成额度 |
| `permission_denied` | 403 | 用户缺少 `generation_job:create` 权限 |

---

## 4. 枚举值

### 4.1 `generation_jobs.job_type`

| 值 | Sprint | 启动器 | 说明 |
|---|---|---|---|
| `generate_bible` | ✅ 1 | `start_generate_bible` | StoryBible 闭环 |
| `generate_outline` | ✅ 2 | `start_generate_outline` | Outline 闭环 |
| `generate_scene_plan` | ✅ 3 | `start_generate_scene_plan` | 单章 scene cards 拆分 |
| `write_scene` | ✅ 1（升级 4） | `start_write_scene` | 单场景写作 |
| `audit_scene` | ✅ 5-A | `start_audit_scene` | 单场景审稿 |
| `rewrite_scene` | ✅ 5-A | `start_rewrite_scene` | 单场景重写 |
| `export_novel` | ⚪ 同步 endpoint | — | Sprint 5-B 改为同步 `POST /exports`，不再走 job |
| `full_novel` | ✅ 1 | `start_generate_full_novel` | 兼容入口，串联多步 |

### 4.2 `generation_jobs.status`（v1 简化状态机）

```
                 ┌──────────┐  (api reject before insert)
                 │ (no row) │ ── 402/403/422 ──→ never created
                 └──────────┘
                       │
                       ▼  (service.py create row)
                  ┌────────┐
                  │ queued │
                  └───┬────┘
                      │  starter triggers worker
                      ▼
                  ┌─────────┐
              ┌── │ running │ ──┐
              │   └─────────┘   │
              │                 │
   succeeded ─┘                 └─ failed / cancelled
       │                                │
       └───────────── terminal ─────────┘
```

| 值 | 含义 | 来源 |
|---|---|---|
| `queued` | 已落库、quota 已预留、workflow 已 fire-and-forget | service.py 初始值 |
| `running` | worker 接到并已 mark | activities.mark_job_status |
| `succeeded` | 工作流正常完成 | workflow 末端 |
| `failed` | 工作流异常 / starter 启动失败 / activity 多次重试后失败 | workflow except 分支 |
| `cancelled` | 用户主动 cancel | api/generation_jobs.cancel |

**v1 不引入** `created` / `quota_reserved` / `quota_insufficient` / `permission_denied` / `subscription_inactive` / `rate_limited` 这些细分。**失败原因走 `error_message` + `error_code` 字段，不挤进 status**。优化方向文档建议的细分状态延到 v2 评估。

进入 `failed` / `cancelled` 时 `mark_job_status` 自动：
1. 释放未消耗的 quota reservation；
2. 回滚 project.status 中的过渡态（见 `_JOB_FAILURE_PROJECT_STATUS`）。

### 4.3 `projects.status`

```
created ──→ bible_generating ──→ bible_ready ──→ outline_generating ──→ outlined
                                                                          │
                                                                          ▼
       drafting ←── scenes_planned ←── scenes_planning ←──────────────────┘
          │
          ▼
       completed
```

| 值 | Sprint | 谁推进 | 失败回滚目标 |
|---|---|---|---|
| `created` | ✅ 1 | api/projects.create_project | — |
| `bible_generating` | ✅ 1 | service.create_bible_job | `created` |
| `bible_ready` | ✅ 1 | activities.generate_book_spec | — |
| `outline_generating` | ✅ 2 | service.create_outline_job | `bible_ready` |
| `outlined` | ✅ 1（已存在但未必走得到） | activities.generate_chapter_outline | — |
| `scenes_planning` | 🟡 仅在 full_novel pipeline 内部使用；**单章 generate_scene_plan 不动 project.status** | — | — |
| `scenes_planned` | ✅ 1（full_novel pipeline 内）| activities.generate_scene_cards | — |
| `drafting` | ✅ 1 | activities.write_scene_drafts | `scenes_planned` |
| `completed` | 🟡 4+ | TBD（全部 scene drafted 后） | — |

**Sprint 3 决策记录**：`generate_scene_plan` 是**章节级**任务，单次调用只影响该章的 scenes 行，不应把整个项目的 status 推到 `scenes_planning` 或 `scenes_planned`。因此 `_JOB_FAILURE_PROJECT_STATUS` 不登记 `generate_scene_plan`，单章失败不回滚 project.status。完整推进项目级状态由 full_novel pipeline 或未来 Sprint 5+ 的"全章 scene_plan 完成"扫描负责。

**注册表同步**：每新增过渡态必须同步在 `app/workflows/activities.py::_JOB_FAILURE_PROJECT_STATUS` 注册回滚映射；新增 job_type 影响 project.status 时同步登记。

### 4.4 Error code 全量

按业务域分组：

#### 通用

| code | HTTP | 触发 |
|---|---|---|
| `not_found` | 404 | NotFoundError 基类（一般不直接抛） |
| `permission_denied` | 403 | 当前角色无所需权限 |
| `validation_error` | 422 | Pydantic schema 校验失败 |
| `internal_error` | 500 | 未捕获异常兜底 |
| `http_error` | 透传 | 兼容老式 HTTPException |
| `conflict` | 409 | 业务状态冲突（retry/cancel 已结束 job 等） |

#### 资源不存在（通过 `*_not_found` 命名约定保持一致）

| code | 模块 |
|---|---|
| `project_not_found` | projects, generation |
| `novel_spec_not_found` | workflows |
| `job_not_found` | generation-jobs |
| `scene_not_found` | scenes, workflows |
| `chapter_not_found` | scenes, workflows |
| `volume_not_found` | chapters |
| `character_not_found` | characters |
| `world_item_not_found` | world-items |
| `version_not_found` | versions |
| `export_not_found` | exports |
| `organization_not_found` | organizations |
| `member_not_found` | organizations |
| `quota_not_found` | admin/organizations |
| `draft_not_found` | workflows（audit/rewrite/write 需要前置 draft） |

#### 额度/付费

| code | HTTP | 含义 |
|---|---|---|
| `quota_insufficient` | 402 | 当前周期额度不够本次预留 |
| `quota_not_in_plan` | 402 | 当前 plan 不开放此 quota_key |
| `invalid_amount` | 402 | reserve_quota 收到非正数 |
| `amount_must_be_positive` | 402 | reserve_quota 配套 message |

#### 参数

| code | 含义 |
|---|---|
| `scene_id_required` | run_scene_writing 缺少 scene_id payload |
| `chapter_id_required` | generate_chapter_scene_cards 缺少 chapter_id payload |
| `export_type_not_supported` | 导出格式超出 markdown/txt 范围 |
| `job_not_retryable` | 试图 retry 一个 succeeded/queued/running 任务 |
| `unknown_job_type` | retry 收到契约外的 job_type |

**新增规则**：所有新 error code 必须先登记到本表与 `app/contracts.py::ERROR_CODES`，命名必须 snake_case，资源不存在统一用 `<resource>_not_found`。`tests/test_contract_consistency.py` 会扫描代码字面量，未登记的值在 CI 中会失败。

---

## 5. 内部约定

### 5.1 Prompt key 与版本

| prompt_key | version | 调用方 |
|---|---|---|
| `bible/generate_story_bible` | `v1` | novel_planner.generate_story_bible |
| `outline/plan_chapters` | `v1` | novel_planner.plan_chapters |
| `outline/plan_scenes` | `v1` | novel_planner.plan_scenes |
| `writing/write_scene` | `v1` | writer.write_scene_draft |

版本号变化必须：① 新建 `<key>.<version>.md` prompt 文件；② 同步更新 caller 中的 `_PROMPT_VERSION` 常量；③ `model_calls.prompt_version` 自动落新值，便于回归对比。

### 5.2 Quota key

| quota_key | 计量单位 | 当前消费方 |
|---|---|---|
| `monthly_generated_words` | words | bible / outline / scene_plan / write_scene 都从这里预留 |

未来如分离 `monthly_review_count`、`monthly_rewrite_count`，按相同 reservation → settle/release 模式扩展。

### 5.3 RetryPolicy 命名

集中在 `app/workflows/retry_policy.py`：

- `MODEL_ACTIVITY_RETRY`：模型密集 activity（3 次，2-30s 退避）
- `STATUS_ACTIVITY_RETRY`：状态机 activity（5 次，1-10s 退避）

业务异常（AppError 子类、ValueError、TypeError、ValidationError）通过 `non_retryable_error_types` 跳过重试。新增业务异常子类必须在此处登记。

---

## 6. v1 冻结策略

### 6.1 允许的演进

- 新增 endpoint（v1 内）
- 新增 error code（先登记本文档）
- 给现有 response schema 添加可选字段
- 新增 enum 值（job_type、project.status）— **必须先更新本文档**

### 6.2 禁止的演进（必须 v2）

- 删除/重命名已有 endpoint 或字段
- 修改已有 error code 的 HTTP 状态码
- 修改已有 enum 值的语义
- 改变 response 必需字段类型

### 6.3 当前已知的 v2 候选

- ~~`scene_write` → `write_scene`（Sprint 4 前迁移）~~ — ✅ 已在 v1 内完成（alembic 0008）
- job status 细分（多个 failed 子状态）
- API 响应 envelope（统一包成 `{data, meta}` 形式）

---

## 7. 变更流程

1. 提 PR 前**先**修改本文档对应章节，再同步 `app/contracts.py`。
2. PR 标题前缀 `contract:` 或 `contract!:`（破坏性）。
3. Reviewer 检查代码是否与文档一致；CI 会跑 `test_contract_consistency.py`
   自动捕获代码中未登记的字面量。
4. 合并后通知前端 / Admin / QA 同步。

任何"先写代码再补文档"的变更都视为契约漂移。Lint 测试是兜底，**不是替代设计沟通**。
