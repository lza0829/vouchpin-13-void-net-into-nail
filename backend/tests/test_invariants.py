"""
不变量与边界：
- 作废事件入湖且不物理删除（两策略）
- 预览/批头/批明细/事件湖同源一致
- 策略切换护栏与默认值
- 重复作废、无券作废、业务日错位、sealed 日禁核销
- v1 -> v2 schema 迁移
"""
from __future__ import annotations
import sqlite3

from conftest import set_policy, redeem, void, list_events, list_facts


def test_default_policy_is_never_pin(client):
    r = client.get("/api/settings/void-policy")
    assert r.json()["void_policy"] == "never_pin"
    assert set(r.json()["options"]) == {"never_pin", "net_pin"}


def test_policy_switch_blocked_while_open_facts_exist(client, use_day):
    set_policy(client, "never_pin")
    redeem(client, "C-A", 10.0)
    r = client.put("/api/settings/void-policy", json={"void_policy": "net_pin"})
    assert r.status_code == 409
    # 钉干净后可切
    client.post("/api/redeem/seal", json={})
    r2 = client.put("/api/settings/void-policy", json={"void_policy": "net_pin"})
    assert r2.status_code == 200 and r2.json()["changed"] is True
    assert client.get("/api/settings/void-policy").json()["void_policy"] == "net_pin"


def test_invalid_policy_rejected(client):
    r = client.put("/api/settings/void-policy", json={"void_policy": "bogus"})
    assert r.status_code == 400


def test_void_unknown_coupon_404(client, use_day):
    set_policy(client, "never_pin")
    r = void(client, "C-NOPE")
    assert r.status_code == 404
    assert list_events(client) == []


def test_double_void_rejected(client, use_day):
    set_policy(client, "never_pin")
    redeem(client, "C-A", 10.0)
    assert void(client, "C-A").status_code == 200
    r2 = void(client, "C-A")
    assert r2.status_code == 409
    # 只有一条作废事件
    assert sum(1 for e in list_events(client) if e["event_type"] == "void") == 1


def test_void_on_wrong_business_day_rejected(client, use_day):
    set_policy(client, "net_pin")
    redeem(client, "C-A", 10.0)
    r = client.post(
        "/api/events",
        json={
            "event_type": "void",
            "coupon_code": "C-A",
            "campaign_code": "NEW10",
            "business_day": "2026-11-11",
        },
    )
    assert r.status_code == 400
    # 没有产生跨日负向事实
    assert client.get("/api/facts?business_day=2026-11-11").json() == []


def test_redeem_blocked_after_day_sealed(client, use_day):
    set_policy(client, "never_pin")
    redeem(client, "C-A", 10.0)
    client.post("/api/redeem/seal", json={})
    r = client.post(
        "/api/events",
        json={"event_type": "redeem", "coupon_code": "C-Z",
              "campaign_code": "NEW10", "amount": 5.0},
    )
    assert r.status_code == 409


def test_no_physical_delete_any_policy(client, use_day):
    """两策略下：作废后事件与事实都只增不减/只改状态，绝不物理删除。"""
    for policy in ("never_pin", "net_pin"):
        # never_pin 先跑并钉干净，才能切到 net_pin
        redeem(client, f"C-{policy}-1", 10.0)
        before_events = len(list_events(client))
        before_facts = len(list_facts(client))
        r = void(client, f"C-{policy}-1")
        assert r.status_code == 200
        assert len(list_events(client)) == before_events + 1  # 多一条 void 事件
        if policy == "never_pin":
            # 事实行数不变，只是状态 open -> voided
            assert len(list_facts(client)) == before_facts
            f = next(x for x in list_facts(client) if x["coupon_code"] == f"C-{policy}-1")
            assert f["status"] == "voided" and f["void_event_id"]
        else:
            # net_pin 多一条负向事实，原正向事实不动
            assert len(list_facts(client)) == before_facts + 1
            client.post("/api/redeem/seal", json={})
        # voided 不属于待钉集合，无 open/open_void 时允许切换全局策略
        set_policy(client, "net_pin" if policy == "never_pin" else "never_pin")


def test_dashboard_carries_policy_and_gross_net(client, use_day):
    set_policy(client, "never_pin")
    redeem(client, "C-A", 10.0)
    redeem(client, "C-B", 20.0)
    void(client, "C-B")
    d = client.get("/api/dashboard").json()
    assert d["void_policy"] == "never_pin"
    assert d["redeem_gross_today"] == 30.0
    assert d["void_amount_today"] == -20.0
    assert d["redeem_net_today"] == 10.0
    assert d["void_event_count"] == 1
    assert d["voided_fact_count"] == 1


def test_batch_404(client):
    assert client.get("/api/batches/9999").status_code == 404


def test_seal_empty_rejected(client, use_day):
    set_policy(client, "never_pin")
    assert client.post("/api/redeem/seal", json={}).status_code == 400


def test_seal_twice_rejected(client, use_day):
    set_policy(client, "never_pin")
    redeem(client, "C-A", 10.0)
    assert client.post("/api/redeem/seal", json={}).status_code == 200
    assert client.post("/api/redeem/seal", json={}).status_code == 409


def test_v1_to_v2_migration(tmp_path):
    """老库（无 void 字段、无快照表）启动后自动迁移且数据不丢。"""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO settings VALUES('business_day', '2026-01-01');
        CREATE TABLE campaigns (
          id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
          title TEXT NOT NULL, face_value REAL NOT NULL, min_spend REAL NOT NULL DEFAULT 0);
        CREATE TABLE coupon_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
          coupon_code TEXT NOT NULL, campaign_code TEXT NOT NULL,
          amount REAL NOT NULL DEFAULT 0, business_day TEXT NOT NULL,
          occurred_at TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT (datetime('now')));
        CREATE TABLE redeem_facts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, coupon_code TEXT NOT NULL UNIQUE,
          campaign_code TEXT NOT NULL, amount REAL NOT NULL,
          business_day TEXT NOT NULL, event_id INTEGER NOT NULL,
          batch_id INTEGER, status TEXT NOT NULL DEFAULT 'open');
        CREATE TABLE redeem_batches (
          id INTEGER PRIMARY KEY AUTOINCREMENT, business_day TEXT NOT NULL,
          status TEXT NOT NULL, fact_count INTEGER NOT NULL DEFAULT 0,
          total_amount REAL NOT NULL DEFAULT 0, sealed_at TEXT,
          note TEXT NOT NULL DEFAULT '');
        INSERT INTO campaigns(code, title, face_value, min_spend)
          VALUES('NEW10','t',10,0);
        INSERT INTO coupon_events(event_type, coupon_code, campaign_code, amount,
          business_day, occurred_at)
          VALUES('redeem','C-1','NEW10',10,'2026-01-01','2026-01-01T10:00:00');
        INSERT INTO redeem_facts(coupon_code, campaign_code, amount, business_day,
          event_id, status)
          VALUES('C-1','NEW10',10,'2026-01-01',1,'open');
        """
    )
    conn.commit()
    conn.close()

    import app.db as db_mod
    import app.config as cfg
    db_mod.DB_PATH = str(db_path)
    cfg.DB_PATH = str(db_path)
    db_mod.init_db()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cols = {r[1] for r in conn.execute("PRAGMA table_info(redeem_facts)")}
    assert {"void_event_id", "voided_fact_id"} <= cols
    bcols = {r[1] for r in conn.execute("PRAGMA table_info(redeem_batches)")}
    assert {"void_net_count", "void_net_amount"} <= bcols
    row = conn.execute("SELECT * FROM redeem_facts WHERE coupon_code='C-1'").fetchone()
    assert row["amount"] == 10 and row["status"] == "open"
    assert conn.execute(
        "SELECT value FROM settings WHERE key='void_policy'"
    ).fetchone()["value"] == "never_pin"
    conn.execute(
        "INSERT INTO redeem_batch_facts(batch_id, fact_id, coupon_code, campaign_code,"
        " amount, status, event_id, seq) VALUES(1,1,'C-1','NEW10',10,'sealed',1,0)"
    )
    conn.commit()
    conn.close()
