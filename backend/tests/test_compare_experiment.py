"""compare_experiment 测试（Sprint 15-D2）。

覆盖：
- 仅匹配的 experiment_id 行被纳入
- response_json["content"] 与 response_text 双路径都能被消费
- 缺 metadata / 缺内容的行被跳过
- A/B 两个 variant 都有样本时返回完整 deltas
- 单 variant 也能产出报告（另一边 sample_count=0）
"""
from __future__ import annotations

import pytest

from app.evals.from_model_calls import compare_experiment
from app.models.common import new_id
from app.models.model_call import ModelCall


def _mk_call(
    *,
    organization_id: str = "org1",
    project_id: str = "proj1",
    task_type: str = "write_scene_draft",
    prompt_version: str = "v2",
    response_text: str | None = None,
    response_json: dict | None = None,
    metadata_json: dict | None = None,
) -> ModelCall:
    return ModelCall(
        id=new_id("model_call"),
        organization_id=organization_id,
        project_id=project_id,
        job_id=None,
        task_type=task_type,
        model="test-model",
        prompt_key="writing/write_scene",
        prompt_version=prompt_version,
        system_prompt="sys",
        user_prompt="usr",
        response_text=response_text,
        response_json=response_json,
        input_tokens=10,
        output_tokens=20,
        latency_ms=100,
        cost_usd=0,
        status="success",
        metadata_json=metadata_json,
    )


@pytest.mark.asyncio
async def test_compare_experiment_aggregates_both_variants(db_session):
    exp_id = "pexp_test_x"
    # A variant：3 条带"对话很多"的内容
    for _ in range(3):
        db_session.add(
            _mk_call(
                response_json={
                    "content": (
                        '主角说"我们必须出发"。\n'
                        '配角答"等等，我有疑问"。\n'
                        '他叹了口气："好吧"。'
                    )
                },
                metadata_json={"experiment_id": exp_id, "variant": "a"},
            )
        )
    # B variant：2 条对白少环境多
    for _ in range(2):
        db_session.add(
            _mk_call(
                response_text="阳光透过窗户洒在桌面上，灰尘飞舞。\n远处传来钟声，街上的人停下脚步抬头望去。",
                metadata_json={"experiment_id": exp_id, "variant": "b"},
            )
        )
    # 噪声：不同 experiment_id
    db_session.add(
        _mk_call(
            response_json={"content": "无关内容"},
            metadata_json={"experiment_id": "other_exp", "variant": "a"},
        )
    )
    # 噪声：无 metadata
    db_session.add(_mk_call(response_text="无 meta", metadata_json=None))
    # 噪声：无内容
    db_session.add(
        _mk_call(
            response_json=None,
            response_text=None,
            metadata_json={"experiment_id": exp_id, "variant": "a"},
        )
    )
    await db_session.flush()

    cmp = await compare_experiment(db_session, experiment_id=exp_id)
    assert cmp.experiment_id == exp_id
    assert cmp.matched_calls == 5  # 3 + 2 命中
    assert cmp.variants["a"].sample_count == 3
    assert cmp.variants["b"].sample_count == 2
    # A 对话多 → dialogue_ratio 更高
    a_ratio = cmp.variants["a"].objective["dialogue_ratio"]
    b_ratio = cmp.variants["b"].objective["dialogue_ratio"]
    assert a_ratio > b_ratio
    # deltas 是 b - a；对话比例上 delta 应为负
    assert cmp.deltas["dialogue_ratio"] < 0


@pytest.mark.asyncio
async def test_compare_experiment_single_variant(db_session):
    exp_id = "pexp_lonely"
    db_session.add(
        _mk_call(
            response_json={"content": "孤立 variant a。"},
            metadata_json={"experiment_id": exp_id, "variant": "a"},
        )
    )
    await db_session.flush()
    cmp = await compare_experiment(db_session, experiment_id=exp_id)
    assert cmp.variants["a"].sample_count == 1
    assert cmp.variants["b"].sample_count == 0
    # deltas 落到 0 - 非零 = 负数（b - a，b 空）
    assert "dialogue_ratio" in cmp.deltas


@pytest.mark.asyncio
async def test_compare_experiment_empty_when_no_match(db_session):
    db_session.add(
        _mk_call(
            response_json={"content": "x"},
            metadata_json={"experiment_id": "other", "variant": "a"},
        )
    )
    await db_session.flush()
    cmp = await compare_experiment(db_session, experiment_id="pexp_nope")
    assert cmp.matched_calls == 0
    assert cmp.variants["a"].sample_count == 0
    assert cmp.variants["b"].sample_count == 0


def test_comparison_to_dict_is_serializable():
    """to_dict 不应包含 dataclass 实例；json.dumps 能直接处理。"""
    import json

    from app.evals.from_model_calls import (
        ExperimentComparison,
        VariantAggregate,
    )

    cmp = ExperimentComparison(
        experiment_id="x",
        generated_at="2026-05-23T00:00:00+00:00",
        total_calls=0,
        matched_calls=0,
        variants={
            "a": VariantAggregate(variant="a", sample_count=0, objective={}),
            "b": VariantAggregate(variant="b", sample_count=0, objective={}),
        },
    )
    json.dumps(cmp.to_dict(), ensure_ascii=False)
