"""验证 B+C 模块：组织套餐切换 + 用户管理 + 套餐删除保护 + quota 跨租户列表。

约束的关键风险点：
- 切换 plan 后 quota_balance.limit 应同步刷新，used / reserved 不变（升级不清零）
- 删除被引用的 plan → 必须 409 plan_in_use，否则组织额度初始化时崩
- super_admin 不能改自己的 role / status，避免锁死系统
- 普通用户不能调用任何 admin 接口
"""
from __future__ import annotations

import pytest


async def _register(client, email: str) -> tuple[str, str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return data["access_token"], data["user"]["organization_id"], data["user"]["id"]


async def _seed_plans(client, headers):
    """造两套餐：Standard 与 Pro，便于切换测试。"""
    standard = await client.post(
        "/api/v1/admin/plans",
        headers=headers,
        json={
            "code": "Standard",
            "name": "Standard",
            "description": "标准",
            "price_monthly": 29,
            "currency": "CNY",
            "status": "active",
            "features": [
                {
                    "feature_key": "monthly_generated_words",
                    "enabled": True,
                    "limit_value": 50000,
                    "limit_unit": "words",
                }
            ],
        },
    )
    assert standard.status_code == 201, standard.text
    pro = await client.post(
        "/api/v1/admin/plans",
        headers=headers,
        json={
            "code": "Pro",
            "name": "Pro",
            "description": "专业",
            "price_monthly": 99,
            "currency": "CNY",
            "status": "active",
            "features": [
                {
                    "feature_key": "monthly_generated_words",
                    "enabled": True,
                    "limit_value": 500000,
                    "limit_unit": "words",
                },
                {
                    "feature_key": "monthly_review_count",
                    "enabled": True,
                    "limit_value": 200,
                    "limit_unit": "times",
                },
            ],
        },
    )
    assert pro.status_code == 201, pro.text
    return standard.json(), pro.json()


@pytest.mark.asyncio
async def test_switch_org_plan_resets_quota_limits(client):
    admin_token, _, _ = await _register(client, "switch-admin@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    await _seed_plans(client, admin_headers)

    # 第二个普通用户，默认在 Free plan
    _, target_org, _ = await _register(client, "switch-target@example.com")

    # 切到 Standard
    res = await client.patch(
        f"/api/v1/admin/organizations/{target_org}",
        headers=admin_headers,
        json={"plan_code": "Standard", "reason": "升级试用"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["plan_code"] == "Standard"

    # Standard 的 monthly_generated_words 应该已被同步
    balances = await client.get(
        f"/api/v1/admin/organizations/{target_org}/quotas",
        headers=admin_headers,
    )
    assert balances.status_code == 200
    rows = {b["quota_key"]: b for b in balances.json()}
    assert rows["monthly_generated_words"]["limit_value"] == 50000
    # 一个新 plan_features = 一个 quota_balance 行
    assert len(rows) == 1

    # 再升 Pro：原 quota 升级 + 新增 monthly_review_count
    res = await client.patch(
        f"/api/v1/admin/organizations/{target_org}",
        headers=admin_headers,
        json={"plan_code": "Pro"},
    )
    assert res.status_code == 200

    balances2 = await client.get(
        f"/api/v1/admin/organizations/{target_org}/quotas",
        headers=admin_headers,
    )
    rows2 = {b["quota_key"]: b for b in balances2.json()}
    assert rows2["monthly_generated_words"]["limit_value"] == 500000
    assert rows2["monthly_review_count"]["limit_value"] == 200
    # used / reserved 没有被改动（升级不清零）
    assert rows2["monthly_generated_words"]["used_value"] == 0
    assert rows2["monthly_generated_words"]["reserved_value"] == 0


@pytest.mark.asyncio
async def test_switch_to_nonexistent_plan_rejected(client):
    admin_token, _, _ = await _register(client, "noplan-admin@example.com")
    _, target_org, _ = await _register(client, "noplan-target@example.com")

    res = await client.patch(
        f"/api/v1/admin/organizations/{target_org}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"plan_code": "Nonexistent"},
    )
    assert res.status_code == 404
    body = res.json()
    assert body["error"]["code"] == "plan_not_found"


@pytest.mark.asyncio
async def test_delete_plan_in_use_blocked(client):
    admin_token, admin_org, _ = await _register(client, "del-admin@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    standard, _ = await _seed_plans(client, admin_headers)

    # 把 admin 的组织绑到 Standard，让它"被使用"
    res = await client.patch(
        f"/api/v1/admin/organizations/{admin_org}",
        headers=admin_headers,
        json={"plan_code": "Standard"},
    )
    assert res.status_code == 200

    # 删除 Standard 应该被拦
    res = await client.delete(
        f"/api/v1/admin/plans/{standard['id']}",
        headers=admin_headers,
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "plan_in_use"


@pytest.mark.asyncio
async def test_delete_plan_unused_succeeds(client):
    admin_token, _, _ = await _register(client, "del2-admin@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    standard, _ = await _seed_plans(client, admin_headers)

    res = await client.delete(
        f"/api/v1/admin/plans/{standard['id']}",
        headers=admin_headers,
    )
    assert res.status_code == 204

    plans = await client.get("/api/v1/admin/plans", headers=admin_headers)
    codes = {p["code"] for p in plans.json()}
    assert "Standard" not in codes
    assert "Pro" in codes


@pytest.mark.asyncio
async def test_admin_cannot_modify_self_role(client):
    admin_token, _, admin_user_id = await _register(client, "self-admin@example.com")
    res = await client.patch(
        f"/api/v1/admin/users/{admin_user_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"platform_role": "user"},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "cannot_modify_self"


@pytest.mark.asyncio
async def test_admin_can_disable_other_user(client):
    admin_token, _, _ = await _register(client, "disable-admin@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    _, _, target_id = await _register(client, "disable-target@example.com")

    res = await client.patch(
        f"/api/v1/admin/users/{target_id}",
        headers=admin_headers,
        json={"status": "disabled", "reason": "违反内容规范"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "disabled"


@pytest.mark.asyncio
async def test_admin_reset_password_returns_temp(client):
    admin_token, _, _ = await _register(client, "rp-admin@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    _, _, target_id = await _register(client, "rp-target@example.com")

    res = await client.post(
        f"/api/v1/admin/users/{target_id}/reset-password",
        headers=admin_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["temp_password"]
    assert len(body["temp_password"]) >= 12

    # 用新临时密码可以登录，旧密码失效
    login_new = await client.post(
        "/api/v1/auth/login",
        json={"email": "rp-target@example.com", "password": body["temp_password"]},
    )
    assert login_new.status_code == 200
    login_old = await client.post(
        "/api/v1/auth/login",
        json={"email": "rp-target@example.com", "password": "password123"},
    )
    assert login_old.status_code == 401


@pytest.mark.asyncio
async def test_user_detail_lists_organizations(client):
    admin_token, _, _ = await _register(client, "detail-admin@example.com")
    _, target_org, target_id = await _register(client, "detail-target@example.com")

    res = await client.get(
        f"/api/v1/admin/users/{target_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == target_id
    # 注册时默认创建个人组织 + 加成员
    assert len(body["organizations"]) >= 1
    assert any(o["organization_id"] == target_org for o in body["organizations"])


@pytest.mark.asyncio
async def test_normal_user_blocked_on_admin_endpoints(client):
    await _register(client, "first@example.com")  # 占用 super_admin 位
    token, _, target_id = await _register(client, "normal@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    for path, method in [
        (f"/api/v1/admin/users/{target_id}", "patch"),
        ("/api/v1/admin/organizations/org_x", "patch"),
        ("/api/v1/admin/quota-balances", "get"),
        ("/api/v1/admin/quota-keys", "get"),
    ]:
        if method == "get":
            res = await client.get(path, headers=headers)
        else:
            res = await client.patch(path, headers=headers, json={"plan_code": "X"})
        assert res.status_code == 403, f"{method} {path} expected 403"


@pytest.mark.asyncio
async def test_plan_response_includes_organization_count(client):
    admin_token, admin_org, _ = await _register(client, "count-admin@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    _, pro = await _seed_plans(client, admin_headers)

    # 把 admin org 切到 Pro，让 Pro 的 organization_count = 1
    await client.patch(
        f"/api/v1/admin/organizations/{admin_org}",
        headers=admin_headers,
        json={"plan_code": "Pro"},
    )
    res = await client.get("/api/v1/admin/plans", headers=admin_headers)
    by_code = {p["code"]: p for p in res.json()}
    assert by_code["Pro"]["organization_count"] == 1
    assert by_code["Standard"]["organization_count"] == 0


@pytest.mark.asyncio
async def test_quota_keys_aggregates_from_plan_features(client):
    admin_token, _, _ = await _register(client, "qk-admin@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    await _seed_plans(client, admin_headers)

    res = await client.get("/api/v1/admin/quota-keys", headers=admin_headers)
    assert res.status_code == 200
    keys = {row["feature_key"] for row in res.json()}
    assert "monthly_generated_words" in keys
    assert "monthly_review_count" in keys
