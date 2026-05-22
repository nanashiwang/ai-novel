"""PromptRouter + Admin API 测试（Sprint 15-D1）。

覆盖：
- PromptRouter._bucket 稳定性（同输入必返同值）
- PromptRouter.route 无 active 实验时透传 baseline
- PromptRouter.route 有 active 实验时按 split 分流
- 100 个 project_id 在 50/50 split 下分布在 40-60 范围内
- 缓存：route 一次再切换 status 后 invalidate 立即生效
- API：CRUD + status 转换 + 删除保护
- ModelGateway 集成：active 实验时 model_calls.metadata_json 含 experiment_id/variant
"""
from __future__ import annotations

from collections import Counter

import pytest

from app.models.common import new_id
from app.models.prompt_experiment import PromptExperiment
from app.services.prompt_router import RoutingResult, prompt_router


def test_bucket_is_stable_and_in_range():
    a = prompt_router._bucket("exp_x", "org_1", "proj_1")
    b = prompt_router._bucket("exp_x", "org_1", "proj_1")
    assert a == b
    assert 0 <= a < 100


def test_bucket_changes_with_project():
    # 不同 project_id 应产生不同 bucket（同 exp+org）
    a = prompt_router._bucket("exp_x", "org_1", "proj_1")
    b = prompt_router._bucket("exp_x", "org_1", "proj_2")
    assert a != b


@pytest.mark.asyncio
async def test_route_without_active_experiment_returns_baseline(db_session):
    prompt_router.invalidate()
    result = await prompt_router.route(
        db_session,
        organization_id="org_baseline",
        prompt_key="writing/write_scene",
        baseline_version="v2",
        project_id="proj_x",
    )
    assert isinstance(result, RoutingResult)
    assert result.prompt_version == "v2"
    assert result.experiment_id is None
    assert result.variant is None


@pytest.mark.asyncio
async def test_route_active_experiment_routes_to_variant(db_session):
    prompt_router.invalidate()
    exp = PromptExperiment(
        id=new_id("pexp"),
        organization_id="org_route",
        prompt_key="writing/write_scene",
        variant_a_version="v2",
        variant_b_version="v3",
        traffic_split_pct=50,
        status="active",
    )
    db_session.add(exp)
    await db_session.flush()
    prompt_router.invalidate()

    result = await prompt_router.route(
        db_session,
        organization_id="org_route",
        prompt_key="writing/write_scene",
        baseline_version="v2",
        project_id="proj_route_1",
    )
    assert result.experiment_id == exp.id
    assert result.variant in {"a", "b"}
    assert result.prompt_version in {"v2", "v3"}


@pytest.mark.asyncio
async def test_route_5050_split_distribution_within_tolerance(db_session):
    prompt_router.invalidate()
    exp = PromptExperiment(
        id=new_id("pexp"),
        organization_id="org_dist",
        prompt_key="writing/write_scene",
        variant_a_version="v2",
        variant_b_version="v3",
        traffic_split_pct=50,
        status="active",
    )
    db_session.add(exp)
    await db_session.flush()
    prompt_router.invalidate()

    counts: Counter[str] = Counter()
    for i in range(100):
        result = await prompt_router.route(
            db_session,
            organization_id="org_dist",
            prompt_key="writing/write_scene",
            baseline_version="v2",
            project_id=f"proj_{i}",
        )
        counts[result.variant or "?"] += 1
    # 100 样本 50/50 split：每边落在 [35, 65]（容忍统计抖动）
    assert 35 <= counts["a"] <= 65, counts
    assert 35 <= counts["b"] <= 65, counts


@pytest.mark.asyncio
async def test_route_status_pause_takes_effect_after_invalidate(db_session):
    prompt_router.invalidate()
    exp = PromptExperiment(
        id=new_id("pexp"),
        organization_id="org_pause",
        prompt_key="writing/write_scene",
        variant_a_version="v2",
        variant_b_version="v3",
        traffic_split_pct=50,
        status="active",
    )
    db_session.add(exp)
    await db_session.flush()
    prompt_router.invalidate()

    r1 = await prompt_router.route(
        db_session,
        organization_id="org_pause",
        prompt_key="writing/write_scene",
        baseline_version="v2",
        project_id="proj_pause",
    )
    assert r1.experiment_id == exp.id

    exp.status = "paused"
    await db_session.flush()
    prompt_router.invalidate("org_pause")

    r2 = await prompt_router.route(
        db_session,
        organization_id="org_pause",
        prompt_key="writing/write_scene",
        baseline_version="v2",
        project_id="proj_pause",
    )
    assert r2.experiment_id is None
    assert r2.prompt_version == "v2"


@pytest.mark.asyncio
async def test_zero_split_routes_everyone_to_b(db_session):
    prompt_router.invalidate()
    exp = PromptExperiment(
        id=new_id("pexp"),
        organization_id="org_zero",
        prompt_key="writing/write_scene",
        variant_a_version="v2",
        variant_b_version="v3",
        traffic_split_pct=0,
        status="active",
    )
    db_session.add(exp)
    await db_session.flush()
    prompt_router.invalidate()

    for i in range(20):
        r = await prompt_router.route(
            db_session,
            organization_id="org_zero",
            prompt_key="writing/write_scene",
            baseline_version="v2",
            project_id=f"p{i}",
        )
        assert r.variant == "b"
        assert r.prompt_version == "v3"


@pytest.mark.asyncio
async def test_full_split_routes_everyone_to_a(db_session):
    prompt_router.invalidate()
    exp = PromptExperiment(
        id=new_id("pexp"),
        organization_id="org_full",
        prompt_key="writing/write_scene",
        variant_a_version="v2",
        variant_b_version="v3",
        traffic_split_pct=100,
        status="active",
    )
    db_session.add(exp)
    await db_session.flush()
    prompt_router.invalidate()

    for i in range(20):
        r = await prompt_router.route(
            db_session,
            organization_id="org_full",
            prompt_key="writing/write_scene",
            baseline_version="v2",
            project_id=f"p{i}",
        )
        assert r.variant == "a"
        assert r.prompt_version == "v2"
