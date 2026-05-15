# NovelFlow AI Backend

FastAPI 后端架构骨架，按 PRD Phase 2-4 搭建：SaaS 底座、小说业务、生成任务、Model Gateway、Temporal Workflow。

## 本阶段边界

- 已搭建可运行 API 壳、服务边界、schema、mock repository、工作流/worker 占位。
- 不连接真实 OpenAI、支付、生产 Temporal；默认使用 mock model gateway 和内存数据。
- 所有业务模型保留 `organization_id` 租户边界。

## 本地运行

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
uvicorn app.main:app --reload --port 8000
```

## 常用接口

- `GET /health`
- `GET /api/v1/auth/me`
- `GET /api/v1/projects`
- `POST /api/v1/projects/{project_id}/generate-full-novel`
- `GET /api/v1/generation-jobs/{job_id}`
- `GET /api/v1/admin/model-calls`

## 架构链路

生成任务入口会执行：Auth → Tenant → Permission → Entitlement → Quota Reservation → GenerationJob → Workflow Starter。
