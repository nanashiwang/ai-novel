# NovelFlow AI 架构说明

当前仓库已经从纯前端扩展为完整 SaaS 架构骨架：

- `frontend/`：Next.js App Router UI 壳。
- `backend/`：FastAPI API、服务边界、SQLAlchemy 模型、Temporal workflow/worker 占位。
- `infra/postgres/`：PostgreSQL + pgvector 初始化 schema 和 seed。
- `docker-compose.yml`：Postgres、Redis、Temporal、Temporal UI、MinIO。

## 后端请求链路

受保护 API 按 PRD 保留统一链路：

```text
Auth → Tenant Resolver → Permission Checker → Entitlement Checker → Quota Checker → Handler → Audit Logger
```

生成任务入口：

```text
POST /api/v1/projects/{project_id}/generate-full-novel
  → check permission generation_job:create
  → check entitlement generation:full_novel
  → reserve quota monthly_generated_words
  → create generation_jobs
  → start workflow stub
```

## 关键约束

- 所有小说业务数据带 `organization_id`。
- 权限（Role/Permission）和商业权益（Plan/Entitlement）分离。
- 自动写作任务写入 `generation_jobs`，模型调用写入 `model_calls`，额度消耗写入 `usage_events`。
- Model Gateway 是唯一模型调用入口；当前是 mock 模式。
- Temporal workflow 已有类和 worker 入口，后续可替换 `WorkflowStarter` 为真实 client。

## 本地验证

```bash
make check-frontend
make check-backend
```

启动基础设施：

```bash
make infra-up
```
