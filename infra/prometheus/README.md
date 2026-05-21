# 监控告警栈（Sprint 13-A4）

Prometheus + Grafana 容器化，提供生成任务失败率、ModelGateway 延迟、API
错误率与基础设施可用性的实时观测与告警。

## 启动

```bash
make monitoring-up           # 启动 prometheus + grafana
make monitoring-down         # 停掉
```

访问：

- Prometheus UI：<http://localhost:9090>
- Grafana：<http://localhost:3001>（默认 `admin/admin`，首次登录请改密码）

Prometheus 通过 docker network 与 backend 通信，scrape `http://backend:8000/metrics`，
故必须先 `make deploy` 起 backend；本地裸跑 `uvicorn` 时请把 prometheus.yml 的
target 改为 `host.docker.internal:8000`。

## 告警规则速查

| Alert | 触发条件 | severity | 团队 |
|-------|---------|---------|------|
| JobFailureRateHigh | 失败率 > 10%（5m） | warning | backend |
| JobFailureRateCritical | 失败率 > 30%（3m） | critical | backend |
| ModelLatencyP95High | p95 > 30s（10m） | warning | backend |
| ModelCallFailureSurge | 非 ok 状态 > 1/s（5m） | critical | backend |
| APIErrorRateHigh | 5xx 占比 > 5%（5m） | warning | backend |
| APILatencyP95High | p95 > 1s（10m） | warning | backend |
| BackendDown | 抓不到 backend > 2m | critical | backend |
| ExportsThroughputDropped | 营业时段 1h 无导出 | warning | product |

规则文件：`infra/prometheus/alert_rules.yml`

## 新增指标流程

1. 在 `backend/app/core/metrics.py` 注册新 Counter / Histogram，按命名约定
   `novelflow_<group>_<unit>`
2. 在 activity / endpoint 处显式 `.inc()` / `.observe()`
3. 若值得告警，把新 rule 追加到 `alert_rules.yml`，并在本表登记
4. 重新 `make monitoring-up` 后，Prometheus `--web.enable-lifecycle` 允许
   `curl -X POST http://localhost:9090/-/reload` 热加载

## Grafana 仪表盘

`infra/grafana/dashboards/backend-overview.json` 通过 provisioning 自动加载。
新增看板：把 JSON 放到同目录，重启 grafana 容器即可。

## 生产化建议

- 当前未集成 alertmanager；告警仅在 Prometheus UI 可视化
- 生产环境建议：
  - 接入 alertmanager + 企业微信 / 飞书 webhook
  - 拆出独立 Prometheus 实例做长期存储（Thanos / Cortex）
  - Grafana 配 OAuth，禁用本地 admin
