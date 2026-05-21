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
    finalize_full_novel,
    generate_book_spec,
    generate_chapter_outline,
    generate_chapter_scene_cards,
    mark_job_status,
    plan_chapter_scenes_for_full_novel,
    prepare_full_novel,
    rewrite_scene,
    run_full_novel_pipeline,
    run_scene_writing,
    write_chapter_scenes_for_full_novel,
)
from app.workflows.audit_scene import AuditSceneWorkflow
from app.workflows.generate_bible import GenerateBibleWorkflow
from app.workflows.generate_full_novel import (
    GenerateFullNovelChapterWorkflow,
    GenerateFullNovelWorkflow,
)
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
            GenerateFullNovelChapterWorkflow,
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
            prepare_full_novel,
            plan_chapter_scenes_for_full_novel,
            write_chapter_scenes_for_full_novel,
            finalize_full_novel,
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

## 7. full_novel 长任务部署注意（Sprint 12-B）

`GenerateFullNovelWorkflow` 与其它单 activity workflow 不同，是一个**分批 +
continue_as_new** 的编排器，会启动若干 `GenerateFullNovelChapterWorkflow`
子 workflow。这给部署带来几个 Temporal 特有的注意事项。

### 7.1 history 长度

每批默认 `BATCH_SIZE = 3` 章。一批内的事件大致：

- `prepare_full_novel`：1 activity（含 spec / outline 复用）
- 每章 child workflow scheduled / completed：2 events × 3 = 6
- 每章子 workflow 内部 ~2 activity：12 events
- `finalize_full_novel` + `mark_job_status` (succeeded)：4 events

合计单 run ~25 events；continue_as_new 之后 history 重置回 0。即使
2000 章项目（MAX_OUTLINE_CHAPTERS）也只会有 ~670 个 run，每 run 都远低于
51200 event / 50MB 的默认上限。

如需调整 batch 大小，改 `app/workflows/generate_full_novel.py::BATCH_SIZE`。
**注意：调整后必须重新部署 worker**（workflow 代码改动违反 deterministic
replay，已 in-flight 的 full_novel job 会在下一次重放时报错）。建议：

1. 创建一个 worker version 标签（如 `BATCH_SIZE=5`）
2. 等所有 BATCH_SIZE=3 的 full_novel job 跑完
3. 再上线新 worker

### 7.2 max_concurrent_activities

父 workflow 在一批内**并行** K=3 个子 workflow，每子 workflow 又有
plan + write 两个 activity；写作 activity 可能持续 5~10 分钟。建议
`max_concurrent_activities` ≥ 16，避免子 workflow 的 activity 排队过久。
内存上每个 activity ~120MB（包含 LLM client / sqlalchemy session）。

### 7.3 子 workflow ID 冲突

父 workflow 给每个 child 命名为 `<parent_wf_id>-ch-<chapter_id>`。同一
chapter 的 retry / continue_as_new 后再次入批时会再次启动同名 child
workflow，Temporal 的 `WorkflowIDReusePolicy` 默认为 `AllowDuplicate`，
不冲突。

### 7.4 quota 结算时机

父 full_novel job 在 `prepare` 阶段不 settle quota（spec/outline 子
activity 已被改成 `skip_settle=True`）；唯一 settle 点在
`finalize_full_novel`，按"实际写出字数"commit。这意味着：

- continue_as_new 中途失败 → mark_job_status('failed') 会自动释放剩余
  reservation
- 半路 cancel → 同上，但已经写出的字数不会被 settle，"幽灵预留"在
  `_release_job_reservations` 中被一次性释放（与其它 job 类型对称）

### 7.5 监控

观察以下指标判断 full_novel 健康度：

- `temporalio_workflow_completed_total{workflow_type="GenerateFullNovelWorkflow"}`
- `temporalio_workflow_failed_total{workflow_type="GenerateFullNovelChapterWorkflow"}`
  ：单章失败率；超过 10% 就应该告警，多半是 LLM provider 限流或 prompt
  退化
- `jobs_created_total{job_type="full_novel", status="succeeded"}` /
  `failed`（API metrics）

### 7.6 故障恢复

worker 重启不会丢 full_novel 状态：每次 continue_as_new 都把当前进度
（offset + 累积 metrics）序列化到 Temporal history，新 worker 接管后从
最新状态继续。但**进行中的 child workflow** 必须由原 worker 完成或被
Temporal 重新调度（取决于 `worker_shutdown_grace_period`）。建议
worker 的 SIGTERM grace ≥ 30 分钟，让最长的 write_chapter_scenes
activity 有机会完成。

