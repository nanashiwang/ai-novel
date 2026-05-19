# Temporal Worker 部署指南

本文档描述如何把 NovelFlow 从默认的 **本地 fire-and-forget 模式** 切换到
**真实 Temporal 集群 + 独立 worker 进程** 的生产部署。

> 本仓库默认 `TEMPORAL_ENABLED=false`：generation_jobs 通过
> `workflow_starter._run_local()` 直接在 API 进程内 `asyncio.create_task` 跑
> 完，不依赖 Temporal。这种模式适合开发/演示，但 **不适合生产**——API
> 重启 = 正在跑的 job 全部丢失。

## 何时启用 Temporal

|场景|建议|
|---|---|
|本地开发、CI 集成|`TEMPORAL_ENABLED=false`（默认）|
|演示环境、内网 PoC|可保持 false，但需告知用户重启风险|
|生产 / 多副本部署|**必须** `TEMPORAL_ENABLED=true` + 独立 worker|

启用 Temporal 后获得：
- workflow 状态在 Temporal 集群持久化，API 重启不影响 in-flight job
- 自动按 `MODEL_ACTIVITY_RETRY` / `STATUS_ACTIVITY_RETRY` 做指数退避重试
- 可在 Temporal UI（`http://temporal-ui:8080`）按 workflow_id 查看完整事件历史

## 1. 启动 Temporal 集群

仓库根目录 `docker-compose.yml` 已包含完整 Temporal 服务：

```bash
docker compose up -d temporal-postgres temporal temporal-ui
# 验证：
docker compose logs temporal | grep "started"
open http://localhost:8080    # Temporal Web UI
```

包含：
- `temporal-postgres`：Temporal 元数据存储（独立于业务 DB）
- `temporal`：`temporalio/auto-setup:1.25.1`，自动建库 + 启动 frontend/matching/history/worker
- `temporal-ui`：`temporalio/ui:2.30.1`，端口 8080

## 2. 配置 API 进程

`backend/.env`（或 K8s ConfigMap）追加：

```bash
TEMPORAL_ENABLED=true
TEMPORAL_HOST=temporal:7233              # docker compose 内 DNS；外部部署改为实际地址
TEMPORAL_NAMESPACE=default
```

重启 API。任何调 `workflow_starter.start_*()` 的入口都会改走
`Client.connect(...).start_workflow(...)`，不会再 fire-and-forget。

**注意**：API 进程**不**注册 workflow / activity，只负责提交任务。

## 3. 部署 worker 进程

worker 与 API 同代码库，但作为独立进程运行。**两侧必须使用同一 git
commit**——workflow 代码不一致会导致 deterministic replay 失败。

### 3.1 worker 入口脚本

新建 `backend/worker.py`（如尚未存在）：

```python
"""Temporal worker 入口。

注册本仓库的全部 workflow 与 activity，监听 `novelflow-generation`
task_queue。生产部署用 `python worker.py`（建议 supervisor / k8s 管控）。
"""
from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from app.core.config import get_settings
from app.workflows.activities import (
    audit_scene,
    generate_book_spec,
    generate_chapter_outline,
    generate_chapter_scene_cards,
    mark_job_status,
    rewrite_scene,
    run_full_novel_pipeline,
    run_scene_writing,
)
from app.workflows.audit_scene import AuditSceneWorkflow
from app.workflows.generate_bible import GenerateBibleWorkflow
from app.workflows.generate_full_novel import GenerateFullNovelWorkflow
from app.workflows.generate_outline import GenerateOutlineWorkflow
from app.workflows.generate_scene_plan import GenerateScenePlanWorkflow
from app.workflows.rewrite_scene import RewriteSceneWorkflow
from app.workflows.write_scene import WriteSceneWorkflow

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    settings = get_settings()
    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
    worker = Worker(
        client,
        task_queue="novelflow-generation",
        workflows=[
            GenerateBibleWorkflow,
            GenerateOutlineWorkflow,
            GenerateScenePlanWorkflow,
            WriteSceneWorkflow,
            AuditSceneWorkflow,
            RewriteSceneWorkflow,
            GenerateFullNovelWorkflow,
        ],
        activities=[
            mark_job_status,
            generate_book_spec,
            generate_chapter_outline,
            generate_chapter_scene_cards,
            run_scene_writing,
            audit_scene,
            rewrite_scene,
            run_full_novel_pipeline,
        ],
        max_concurrent_activities=8,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
```

### 3.2 本地验证

```bash
cd backend
TEMPORAL_ENABLED=true .venv/bin/python worker.py
# 另一终端启动 API（同样 TEMPORAL_ENABLED=true）
# 触发一个 bible 生成；Temporal UI 应能看到 workflow execution
```

### 3.3 K8s 部署样例

worker 作为独立 Deployment（与 api 同 image，不同 entrypoint）：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: novelflow-worker
spec:
  replicas: 2                    # 与业务量匹配；活动是 I/O bound，2-4 足够
  selector:
    matchLabels: { app: novelflow-worker }
  template:
    metadata:
      labels: { app: novelflow-worker }
    spec:
      containers:
        - name: worker
          image: ghcr.io/your-org/novelflow-backend:<同 api 的 git_sha>
          command: ["python", "worker.py"]
          env:
            - name: TEMPORAL_ENABLED
              value: "true"
            - name: TEMPORAL_HOST
              value: "temporal-frontend.temporal.svc.cluster.local:7233"
            - name: DATABASE_URL
              valueFrom: { secretKeyRef: { name: db-secret, key: url } }
            # 与 api 完全一致的 model / minio / quota 相关配置
          resources:
            requests: { cpu: 200m, memory: 512Mi }
            limits:   { cpu: 1000m, memory: 1Gi }
```

**镜像构建要求**：worker 镜像必须能 import 到全部 `app.workflows.*`、
`app.services.*`，因此和 API 共用同一 `backend/Dockerfile`，只是 `command`
不同。

## 4. 灰度切换步骤

1. **预上线**：在 staging 把 `TEMPORAL_ENABLED=true`，跑 `docs/validation_checklist.md`
   中"端到端生成"章节验证所有 7 类 job
2. **生产开关**：先部署 worker（2 副本），再把 API 的 `TEMPORAL_ENABLED` 改成 true
   并滚动重启
3. **回滚**：把 API 的 `TEMPORAL_ENABLED` 改回 false 并重启即可——已在 Temporal
   里跑的 job 会继续由 worker 跑完，新 job 走 local fire-and-forget
4. **下线 worker**：确认 Temporal 上 `novelflow-generation` task_queue 中
   pending workflow 为 0 后，再缩容到 0

## 5. 监控埋点

API 侧已通过 `app.core.metrics.JOBS_CREATED`（按 job_type / status）记录
job 终态计数，所有完成都会触发——无论 local 还是 Temporal 路径，都会从
`mark_job_status` 进入埋点，因此切换 Temporal 不影响监控仪表板。

worker 侧建议额外暴露：
- `temporalio` SDK 内置的 worker metrics（通过 `Worker(..., metrics_handler=...)`
  注入 prometheus handler）
- workflow 失败次数、activity 重试次数

抓取端点：`/api/v1/admin/metrics`（platform admin 权限）。

## 6. 常见问题

**Q: workflow 卡 running 不动**
A: 看 Temporal UI 的 pending activities。最常见原因是 worker 没启动或没注册
对应 activity。

**Q: deterministic replay 报错**
A: workflow 代码改动后必须重新部署 worker；workflow 内不要使用
`datetime.now()` / `random` 等非确定性 API（用 `workflow.now()` /
`workflow.random()`）。

**Q: 本地开发也需要起 Temporal 吗**
A: 不需要。默认 `TEMPORAL_ENABLED=false` 走 local 模式，跑 pytest 也无依赖。
