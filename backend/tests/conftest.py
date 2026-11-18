from __future__ import annotations
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """每个测试一个隔离的临时 SQLite 库，跑完即弃。"""
    db_path = tmp_path / "test.db"
    import app.db as db_mod
    import app.config as cfg
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_path))
    monkeypatch.setattr(cfg, "DB_PATH", str(db_path))

    from app.seed import seed_if_empty
    seed_if_empty()

    # 清掉 seed 的演示事实/事件，保留 campaigns 与 settings，保证全局 open 护栏干净
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        "DELETE FROM redeem_batch_facts; DELETE FROM redeem_batches; "
        "DELETE FROM redeem_facts; DELETE FROM coupon_events;"
    )
    conn.commit()
    conn.close()

    from app.main import app
    return TestClient(app)


@pytest.fixture
def day() -> str:
    return "2026-11-10"


@pytest.fixture
def use_day(client, day):
    r = client.put("/api/settings/day", json={"business_day": day})
    assert r.status_code == 200
    return day


def set_policy(client, policy: str) -> dict:
    r = client.put("/api/settings/void-policy", json={"void_policy": policy})
    assert r.status_code == 200, r.text
    return r.json()


def redeem(client, code: str, amount: float, campaign: str = "NEW10") -> dict:
    r = client.post(
        "/api/events",
        json={
            "event_type": "redeem",
            "coupon_code": code,
            "campaign_code": campaign,
            "amount": amount,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def void(client, code: str, campaign: str = "NEW10"):
    return client.post(
        "/api/events",
        json={"event_type": "void", "coupon_code": code, "campaign_code": campaign},
    )


def list_events(client) -> list[dict]:
    return client.get("/api/events").json()


def list_facts(client) -> list[dict]:
    return client.get("/api/facts").json()
