"""端点级测试：analytics（埋点/漏斗/AB 测试）、config（动态配置中心）、
services（服务注册发现与网关路由）三个平台侧路由。

ConfigManager 默认把 configs.json 写在 ``.caipiao/config``（相对 CWD），
测试期替换为临时目录的实例，避免污染仓库工作区。
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest


def _make_env() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_web_platform_"))
    os.environ.setdefault("CAIPIAO_WEB_DB", f"sqlite:///{tmp / 'platform.db'}")
    os.environ.setdefault("CAIPIAO_WEB_DATA", str(tmp))
    os.environ.setdefault("CAIPIAO_WEB_SECRET", "test-secret-platform")
    os.environ["CAIPIAO_WEB_RATE_LIMIT"] = "100000/minute"
    os.environ["CAIPIAO_WEB_AUTH_RATE_LIMIT"] = "100000/minute"
    return tmp


@pytest.fixture(scope="module")
def workdir() -> Path:
    return _make_env()


@pytest.fixture(scope="module")
def client(workdir):
    from fastapi.testclient import TestClient

    from web_main import app as fastapi_app

    import caipiao.web.config_manager as _cm

    saved = _cm._config_manager
    _cm._config_manager = _cm.ConfigManager(data_dir=str(workdir / "config"))
    with TestClient(fastapi_app) as c:
        yield c
    _cm._config_manager = saved


@pytest.fixture(scope="module")
def token(client) -> str:
    username = f"plat_{uuid.uuid4().hex[:10]}"
    r = client.post("/auth/register", json={"username": username, "password": "pw123456"})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", data={"username": username, "password": "pw123456"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def h(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _uniq(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# --------------------------------------------------------------------------- #
# /analytics
# --------------------------------------------------------------------------- #
def test_analytics_requires_auth(client):
    assert client.get("/analytics/overview").status_code == 401
    assert client.post("/analytics/events", json={"event_type": "a", "event_name": "b"}).status_code == 401


def test_analytics_track_and_query_events(client, h, token):
    me = client.get("/me", headers=h).json()["id"]
    name = _uniq("clicked")

    r = client.post(
        "/analytics/events",
        json={"event_type": "action", "event_name": name, "properties": {"page": "home"}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"
    event_id = r.json()["event_id"]
    assert event_id

    # 显式 session_id 分支
    r = client.post(
        "/analytics/events",
        json={"event_type": "action", "event_name": name, "session_id": "sess-1"},
        headers=h,
    )
    assert r.status_code == 200

    r = client.get("/analytics/events/counts", params={"event_type": "action"}, headers=h)
    assert r.status_code == 200
    assert r.json()[name] == 2

    # 未产生过的事件类型返回空计数
    r = client.get("/analytics/events/counts", params={"event_type": _uniq("nope")}, headers=h)
    assert r.json() == {}

    r = client.get(f"/analytics/user/{me}/events", params={"limit": 10}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == me
    names = [e["event_name"] for e in body["events"]]
    assert names.count(name) == 2
    first = body["events"][0]
    assert {"event_id", "event_type", "event_name", "properties", "timestamp"} == set(first)

    r = client.get("/analytics/user/ghost/events", headers=h)
    assert r.json() == {"user_id": "ghost", "events": []}


def test_analytics_overview(client, h):
    r = client.get("/analytics/overview", params={"minutes": 120}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active_users"] >= 1
    assert body["total_events"] >= 2
    assert isinstance(body["top_events"], list)
    assert isinstance(body["hourly_distribution"], list)
    assert body["active_funnels"] >= 0
    assert body["active_ab_tests"] >= 0


def test_analytics_funnel(client, h):
    step_a = _uniq("view")
    step_b = _uniq("buy")
    for event_name in (step_a, step_b):
        client.post(
            "/analytics/events",
            json={"event_type": "action", "event_name": event_name},
            headers=h,
        )

    r = client.post(
        "/analytics/funnels",
        json={
            "name": "购买漏斗",
            "steps": [
                {"name": "浏览", "event_type": "action", "event_name": step_a},
                {"name": "下单", "event_type": "action", "event_name": step_b},
                {"name": "支付", "event_type": "action", "event_name": _uniq("pay")},
            ],
            "time_window_minutes": 120,
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    fid = r.json()["id"]
    assert r.json()["name"] == "购买漏斗"

    r = client.get(f"/analytics/funnels/{fid}/analyze", params={"minutes": 120}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["funnel_id"] == fid
    assert body["total_users"] >= 1
    assert [s["step"] for s in body["steps"]] == [1, 2, 3]
    assert [s["name"] for s in body["steps"]] == ["浏览", "下单", "支付"]
    assert body["steps"][0]["users"] >= 1
    # 最后一步没有任何事件，转化为 0
    assert body["steps"][2]["users"] == 0
    assert body["conversion_rate"] == 0

    assert client.get("/analytics/funnels/nope/analyze", headers=h).json() == {"error": "漏斗不存在"}


def test_analytics_funnel_name_validated(client, h):
    r = client.post("/analytics/funnels", json={"name": "", "steps": []}, headers=h)
    assert r.status_code == 422
    r = client.post("/analytics/funnels", json={"name": "x" * 51, "steps": []}, headers=h)
    assert r.status_code == 422


def test_analytics_ab_test(client, h):
    r = client.post(
        "/analytics/ab-tests",
        json={
            "name": "首页改版",
            "variants": [{"name": "control", "weight": 0.5}, {"name": "treatment"}],
            "target_metric": "ctr",
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    tid = r.json()["id"]

    r = client.post(f"/analytics/ab-tests/{tid}/assign", headers=h)
    assert r.status_code == 200, r.text
    variant = r.json()["variant"]
    assert variant in {"control", "treatment"}

    r = client.post(
        f"/analytics/ab-tests/{tid}/convert", params={"variant": variant}, headers=h
    )
    assert r.json() == {"status": "ok"}

    r = client.get(f"/analytics/ab-tests/{tid}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == tid
    assert body["name"] == "首页改版"
    assert body["status"] == "running"
    assert body["target_metric"] == "ctr"
    assert {v["name"] for v in body["variants"]} == {"control", "treatment"}
    hit = next(v for v in body["variants"] if v["name"] == variant)
    assert hit["assigned_users"] == 1
    assert hit["conversions"] == 1
    assert hit["conversion_rate"] == 100.0

    assert client.get("/analytics/ab-tests/nope", headers=h).json() == {"error": "测试不存在"}
    assert client.post("/analytics/ab-tests/nope/assign", headers=h).json() == {
        "error": "无法分配变体"
    }
    # 未知测试记录转化是幂等的空操作
    assert client.post(
        "/analytics/ab-tests/nope/convert", params={"variant": "x"}, headers=h
    ).json() == {"status": "ok"}


# --------------------------------------------------------------------------- #
# /config
# --------------------------------------------------------------------------- #
def test_config_requires_auth(client):
    assert client.get("/config").status_code == 401


def test_config_set_get_list_delete(client, h):
    key = _uniq("feature")

    r = client.post(
        "/config",
        json={
            "key": key,
            "value": 42,
            "value_type": "number",
            "description": "并发上限",
            "category": "runtime",
        },
        headers=h,
    )
    assert r.json() == {"status": "ok", "key": key}

    assert client.get(f"/config/{key}", headers=h).json() == {"key": key, "value": 42}
    assert client.get(f"/config/{_uniq('missing')}", headers=h).json() == {
        "error": "Config not found"
    }

    r = client.get("/config", headers=h)
    item = next(i for i in r.json() if i["key"] == key)
    assert item["value"] == 42
    assert item["value_type"] == "number"
    assert item["category"] == "runtime"
    assert item["is_secret"] is False
    assert item["updated_at"] > 0

    # 按分类过滤
    r = client.get("/config", params={"category": "runtime"}, headers=h)
    assert key in {i["key"] for i in r.json()}
    assert client.get("/config", params={"category": _uniq("none")}, headers=h).json() == []

    # 密钥类配置不出现在默认列表中
    secret_key = _uniq("secret")
    client.post(
        "/config",
        json={"key": secret_key, "value": "s3cr3t", "is_secret": True},
        headers=h,
    )
    assert secret_key not in {i["key"] for i in client.get("/config", headers=h).json()}

    assert client.delete(f"/config/{key}", headers=h).json() == {"status": "ok"}
    assert client.delete(f"/config/{key}", headers=h).json() == {"error": "Cannot delete"}


def test_config_bulk_export_import(client, h):
    k1, k2 = _uniq("bulk1"), _uniq("bulk2")

    r = client.post("/config/bulk", json={"configs": {k1: "a", k2: "b"}}, headers=h)
    assert r.json() == {"status": "ok", "updated": 2}

    # /config/export 是静态路径，必须优先于 /config/{key} 匹配
    exported = client.get("/config/export", headers=h).json()
    assert exported[k1] == "a"
    assert exported[k2] == "b"

    k3 = _uniq("imported")
    r = client.post("/config/import", json={"configs": {k3: "c"}}, headers=h)
    assert r.json() == {"status": "ok", "imported": 1}
    assert client.get(f"/config/{k3}", headers=h).json()["value"] == "c"


def test_config_versions_and_rollback(client, h):
    key = _uniq("ver")
    client.post("/config", json={"key": key, "value": "v1"}, headers=h)

    r = client.post("/config/versions", params={"description": "首个快照"}, headers=h)
    assert r.status_code == 200, r.text
    version = r.json()["version"]
    assert r.json()["created_at"] > 0

    client.post("/config", json={"key": key, "value": "v2"}, headers=h)
    assert client.get(f"/config/{key}", headers=h).json()["value"] == "v2"

    r = client.get("/config/versions/list", headers=h)
    entry = next(v for v in r.json() if v["version"] == version)
    assert entry["description"] == "首个快照"
    assert entry["items_count"] >= 1

    assert client.post(f"/config/rollback/{version}", headers=h).json() == {"status": "ok"}
    assert client.get(f"/config/{key}", headers=h).json()["value"] == "v1"

    assert client.post("/config/rollback/99999", headers=h).json() == {"error": "Version not found"}


# --------------------------------------------------------------------------- #
# /services
# --------------------------------------------------------------------------- #
def test_services_requires_auth(client):
    assert client.get("/services/list").status_code == 401
    assert client.get("/services/stats").status_code == 401


def test_service_register_discover_deregister(client, h):
    name = _uniq("svc")

    r = client.post(
        "/services/register",
        json={"name": name, "host": "127.0.0.1", "port": 9001, "metadata": {"connections": 3}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert r.json()["name"] == name

    r = client.post(
        "/services/register",
        json={"name": name, "host": "127.0.0.1", "port": 9002, "protocol": "https"},
        headers=h,
    )
    iid2 = r.json()["id"]

    r = client.get("/services/list", headers=h)
    instances = r.json()[name]
    assert {i["id"] for i in instances} == {iid, iid2}
    assert all(i["status"] == "healthy" for i in instances)

    # 三种负载均衡策略都应命中已注册实例
    for strategy in ("round_robin", "random", "least_connections", "unknown"):
        r = client.get(
            f"/services/discover/{name}", params={"strategy": strategy}, headers=h
        )
        assert r.status_code == 200, r.text
        assert r.json()["id"] in {iid, iid2}
        assert r.json()["protocol"] in {"http", "https"}

    assert client.get(f"/services/discover/{_uniq('ghost')}", headers=h).json() == {
        "error": "No healthy instances"
    }

    # 心跳
    r = client.post(
        "/services/heartbeat", params={"service_name": name, "instance_id": iid}, headers=h
    )
    assert r.json() == {"status": "ok"}
    r = client.post(
        "/services/heartbeat", params={"service_name": name, "instance_id": "ghost"}, headers=h
    )
    assert r.json() == {"error": "Not found"}

    # 尚未做过健康检查时历史为空
    assert client.get(f"/services/health/{iid}", headers=h).json() == []

    r = client.get("/services/stats", headers=h)
    stats = r.json()
    assert stats["total_services"] >= 1
    assert stats["total_instances"] >= 2
    assert stats["healthy_instances"] >= 2
    assert stats["unhealthy_instances"] == stats["total_instances"] - stats["healthy_instances"]
    assert stats["routes"] >= 0

    r = client.post(
        "/services/deregister", params={"service_name": name, "instance_id": iid}, headers=h
    )
    assert r.json() == {"status": "ok"}
    r = client.post(
        "/services/deregister", params={"service_name": name, "instance_id": iid}, headers=h
    )
    assert r.json() == {"error": "Not found"}
    # 最后一个实例摘除后服务名整体消失
    client.post(
        "/services/deregister", params={"service_name": name, "instance_id": iid2}, headers=h
    )
    assert name not in client.get("/services/list", headers=h).json()


def test_service_health_history(client, h):
    """健康检查历史由注册中心异步探活写入，这里直接驱动一次探活再读端点。"""
    import asyncio

    from caipiao.web.service_registry import ServiceInstance, get_service_registry

    registry = get_service_registry()
    instance = ServiceInstance(
        id=_uniq("inst"), name=_uniq("probe"), host="127.0.0.1", port=1
    )
    registry.register(instance)
    # 端口 1 不可达，探活必然失败，走 unhealthy 分支
    asyncio.run(registry.check_health(instance))

    r = client.get(f"/services/health/{instance.id}", headers=h)
    assert r.status_code == 200, r.text
    history = r.json()
    assert len(history) == 1
    assert history[0]["status"] == "unhealthy"
    assert history[0]["checked_at"] > 0


def test_service_routes(client, h):
    path = _uniq("api")

    r = client.post(
        "/services/routes",
        json={"path": path, "service": "billing", "method": "GET", "strip_prefix": True},
        headers=h,
    )
    assert r.json() == {"path": path, "service": "billing"}

    r = client.get("/services/routes", headers=h)
    entry = next(x for x in r.json() if x["path"] == path)
    assert entry["service"] == "billing"
    assert entry["method"] == "GET"

    assert client.delete(f"/services/routes/{path}", headers=h).json() == {"status": "ok"}
    assert client.delete(f"/services/routes/{path}", headers=h).json() == {"error": "Not found"}
