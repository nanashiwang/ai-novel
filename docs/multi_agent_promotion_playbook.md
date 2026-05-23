# Multi-agent 写作默认化决策手册（Sprint 15-D3）

> 本手册回答一个问题：**WRITER_PIPELINE_MODE 默认值什么时候从 `single` 切到 `multi`？**
> 使用 Sprint 15-D1 的 A/B 实验框架 + D2 的 model_calls 对比 + D3 的 CI gate 给出客观依据，避免凭直觉切换默认值。

## 背景

- Sprint 14-C3 落地了 planner → drafter → stylist 三步流水线，配置 `WRITER_PIPELINE_MODE=multi` 启用；默认仍是 `single`（单次 LLM 调用直接产 SceneDraftContract）
- multi 模式预期质量更高，但 **3 倍 token 成本**（plan + draft + polish 各一次调用）
- 谁先看到 multi 的胜出证据，谁先翻默认值——本手册定义"看到证据"的硬标准

## 决策流程

### Step 1 · 创建 A/B 实验

平台 admin 通过 `/api/v1/admin/prompt-experiments` 创建一条实验：

```http
POST /api/v1/admin/prompt-experiments
{
  "organization_id": "<目标观察组织>",
  "prompt_key": "writing/write_scene",
  "variant_a_version": "v2",           // 当前 single 模式用的 prompt 版本
  "variant_b_version": "v2",           // 临时也用 v2；本实验对照的是 mode 不是 version
  "traffic_split_pct": 50,
  "notes": "M1：A=single B=multi 全字段对照"
}
```

> 真正切 mode 的不是 prompt_version——multi 模式实际上是写作器内部行为，目前**没有**通过 PromptRouter 切。
> **本手册的 v1 决策方式**：手动选择一批 project（用户角度划分），其中一半显式设 `WRITER_PIPELINE_MODE=multi`（per-process / per-deployment 环境变量），与默认 single 并行运行 ≥ 2 周。
> **v2 升级路径**：把 `WRITER_PIPELINE_MODE` 改为可被 PromptRouter 路由的"虚拟 prompt_key"（如 `writing/pipeline_mode`），让 A/B 框架直接控制。

### Step 2 · 积累样本

最少要求：

| 维度 | 阈值 | 说明 |
|------|------|------|
| 总 scene 数 | ≥ 100（A、B 各 ≥ 50） | 少于 50 时统计抖动太大不可信 |
| 项目跨度 | ≥ 5 个项目 | 避免单项目风格主导样本分布 |
| 时间跨度 | ≥ 7 天 | 跨越不同时段、不同用户使用模式 |
| genre 多样性 | ≥ 2 种 | 至少覆盖项目里最主流的两类题材 |

### Step 3 · 跑对比

```bash
python -m app.evals.cli compare-experiment <experiment_id> --output ab-report.json
```

输出 JSON 含每个 variant 的：

- `sample_count`：实际命中的 model_calls 数
- `objective`：5 项客观指标均值（dialogue_ratio、lexical_diversity、sensory_density_total、paragraph_count、sentence_length_mean）
- `deltas`：B - A（值 > 0 表示 B 在该指标上高于 A）

### Step 4 · 胜出判定

**multi（视为 B）切换为默认值**，需要同时满足：

| 条件 | 阈值 |
|------|------|
| 客观指标至少 2/5 项 B 优于 A（相对提升 ≥ +3%） | 必要 |
| `lexical_diversity` 不低于 A（不退化） | 必要 |
| `dialogue_ratio` 在 [A × 0.85, A × 1.15] 区间（不大幅偏离） | 必要 |
| 用户感知抽样反馈：multi 偏好 ≥ 60% | 推荐 |
| 月度 token 成本相对 single 涨幅 ≤ 3.5×（含 plan + draft + stylist） | 必要 |
| LLM judge 评分（启用时）综合分 ≥ A + 0.3 | 推荐 |

任何一项**必要**条件不满足 → 维持 `single` 默认值，回到 Step 1 调整 prompt 或 stylist 强度后再 A/B。

### Step 5 · 切换

满足条件后：

```python
# backend/app/core/config.py
writer_pipeline_mode: str = "multi"  # 从 "single" 改这里
```

同步动作：

1. **更新 baseline**：`make eval-baseline`，让 CI gate 接受新基线
2. **写 CHANGELOG**：注明决策依据（引用 ab-report.json）
3. **沟通**：通知所有调用方"默认成本 3x，敏感场景显式设回 single"
4. **保留实验**：实验状态切到 `ended`（不要 delete），便于事后回看 A/B 数据

### Step 6 · 回滚条件

切换为默认后，以下任一情况立即回切：

- 月度 token 成本超出预算 > 10%
- 用户投诉率（与写作质量相关）增加 > 20%
- CI gate 在合入后的第一周内非首次 regression 失败

## 常见误区

- ❌ **看 judge 分高就切**：LLM judge 默认是 stub（统一返 3.0），CI 模式下无法作为唯一依据。除非把 judge 接入真实 LLM 并用 50+ 人工标注样本校准。
- ❌ **样本量 < 50 就下结论**：客观指标在小样本下波动大，容易得到反向结论。
- ❌ **只看 dialogue_ratio**：multi 模式的 stylist 可能压缩对白比例，但整体节奏改善。综合 5 项才靠谱。
- ❌ **跳过 token 成本评估**：multi 是质量 vs 成本权衡，不能只看一边。

## 当前状态（2026-05-23）

- WRITER_PIPELINE_MODE 默认值：`single`
- baseline 文件：`backend/app/evals/baselines/eval_baseline.json`
- 已运行的 A/B 实验：无
- 下一步：等待第一条 multi 模式实验数据
