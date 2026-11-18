"""
验收主线：两套互斥策略 × 三场景
A. 核销后作废再钉（void 发生在 pin 前，同日）
B. 钉后再作废（sealed 后的 void 不得改该批净额）
C. 作废后预览（open 集合随作废变化的口径）
"""
from __future__ import annotations
import pytest

from conftest import set_policy, redeem, void, list_events, list_facts

POLICIES = ["never_pin", "net_pin"]


# ---------------------------------------------------------------- A. 核销→作废→钉
@pytest.mark.parametrize("policy", POLICIES)
def test_redeem_then_void_then_seal(client, use_day, policy):
    set_policy(client, policy)
    # 两笔核销：C-A 10 元保留；C-B 20 元随后作废
    redeem(client, "C-A", 10.0)
    redeem(client, "C-B", 20.0)
    r = void(client, "C-B")
    assert r.status_code == 200, r.text
    void_body = r.json()
    assert void_body["void_policy"] == policy

    events = list_events(client)
    assert [e["event_type"] for e in events] == [
        "redeem", "redeem", "void"
    ]
    # 事件湖：作废以负金额单独可查，绝不物理删除
    void_event = [e for e in events if e["event_type"] == "void"][0]
    assert void_event["amount"] == pytest.approx(-20.0)
    assert void_event["coupon_code"] == "C-B"

    preview = client.get("/api/redeem/preview").json()
    assert preview["void_policy"] == policy

    if policy == "never_pin":
        # 作废永不进钉：open 只剩 C-A 一行正向，无负向行
        assert preview["open_count"] == 1
        assert preview["open_total"] == pytest.approx(10.0)
        assert preview["void_net_count"] == 0
        assert preview["void_net_amount"] == 0
        assert preview["positive_count"] == 1
        assert {f["coupon_code"] for f in preview["facts"]} == {"C-A"}
        assert all(f["amount"] > 0 for f in preview["facts"])
    else:
        # 净额进钉：正向 2 行 + 负向 1 行，净额 10
        assert preview["open_count"] == 3
        assert preview["positive_count"] == 2
        assert preview["void_net_count"] == 1
        assert preview["void_net_amount"] == pytest.approx(-20.0)
        assert preview["open_total"] == pytest.approx(10.0)
        neg = [f for f in preview["facts"] if f["status"] == "open_void"]
        assert len(neg) == 1 and neg[0]["amount"] == pytest.approx(-20.0)
        # 负向行回链到被对冲的正向事实，明细能看出对冲关系
        assert neg[0]["voided_fact_id"] is not None
        assert neg[0]["coupon_code"] == "C-B"

    # 预览合计必须与将钉（seal 返回）合计一致
    seal = client.post("/api/redeem/seal", json={}).json()
    assert seal["total_amount"] == pytest.approx(preview["open_total"])
    assert seal["fact_count"] == preview["open_count"]
    assert seal["void_net_count"] == preview["void_net_count"]
    assert seal["void_net_amount"] == pytest.approx(preview["void_net_amount"])

    # 批头与批明细快照同源自洽
    detail = client.get(f"/api/batches/{seal['batch_id']}").json()
    assert detail["matches_header"] is True
    assert detail["snapshot_total"] == pytest.approx(seal["total_amount"])
    snap = detail["facts"]
    assert len(snap) == seal["fact_count"]

    # 事实侧状态核对，且没有任何物理删除
    facts = list_facts(client)
    assert len(facts) == (2 if policy == "never_pin" else 3)
    if policy == "never_pin":
        b = next(f for f in facts if f["coupon_code"] == "C-B")
        assert b["status"] == "voided"
        assert b["void_event_id"] == void_event["id"]
        assert b["batch_id"] is None
        # 批明细快照里不应出现被作废的 C-B
        assert {r["coupon_code"] for r in snap} == {"C-A"}
    else:
        b_pos = next(f for f in facts if f["coupon_code"] == "C-B" and f["amount"] > 0)
        b_neg = next(f for f in facts if f["coupon_code"] == "C-B" and f["amount"] < 0)
        assert b_pos["status"] == "sealed" and b_neg["status"] == "sealed"
        assert b_neg["voided_fact_id"] == b_pos["id"]
        # 批明细里 C-B 正负成对
        cb = [r for r in snap if r["coupon_code"] == "C-B"]
        assert len(cb) == 2
        assert sum(r["amount"] for r in cb) == pytest.approx(0.0)


# ---------------------------------------------------------------- B. 钉后再作废
@pytest.mark.parametrize("policy", POLICIES)
def test_void_after_sealed_is_rejected_and_batch_untouched(client, use_day, policy):
    set_policy(client, policy)
    redeem(client, "C-A", 10.0)
    seal = client.post("/api/redeem/seal", json={}).json()

    r = void(client, "C-A")
    # 两策略都拒绝：sealed 后的作废不得改该批净额，也不落其它日
    assert r.status_code == 409
    assert "钉扎" in r.json()["detail"]

    # 批次净额/笔数原封不动
    detail = client.get(f"/api/batches/{seal['batch_id']}").json()
    assert detail["batch"]["total_amount"] == pytest.approx(10.0)
    assert detail["batch"]["fact_count"] == 1
    assert detail["batch"]["void_net_count"] == 0

    # 事件湖没有混入被拒绝的作废事件
    events = list_events(client)
    assert all(e["event_type"] != "void" for e in events)

    # 事实仍为 sealed，未被改成 voided
    facts = list_facts(client)
    assert all(f["status"] == "sealed" for f in facts)


def test_net_pin_void_after_seal_never_lands_another_day(client, use_day):
    """net_pin 下显式把作废写到另一个未钉业务日，也要被拒绝（只能拒绝，不落其它日）。"""
    set_policy(client, "net_pin")
    redeem(client, "C-A", 10.0)
    client.post("/api/redeem/seal", json={})

    r = client.post(
        "/api/events",
        json={
            "event_type": "void",
            "coupon_code": "C-A",
            "campaign_code": "NEW10",
            "business_day": "2026-11-11",
        },
    )
    assert r.status_code in (400, 404, 409)
    # 另一个业务日没有被写入任何负向事实
    other = client.get("/api/facts?business_day=2026-11-11").json()
    assert other == []


# ---------------------------------------------------------------- C. 作废后预览
@pytest.mark.parametrize("policy", POLICIES)
def test_preview_shrinks_after_void(client, use_day, policy):
    set_policy(client, policy)
    redeem(client, "C-A", 10.0)
    redeem(client, "C-B", 20.0)

    before = client.get("/api/redeem/preview").json()
    assert before["open_count"] == 2
    assert before["open_total"] == pytest.approx(30.0)

    assert void(client, "C-A").status_code == 200
    after = client.get("/api/redeem/preview").json()

    if policy == "never_pin":
        # open 随作废减少且不含负向行
        assert after["open_count"] == 1
        assert after["open_total"] == pytest.approx(20.0)
        assert all(f["amount"] > 0 for f in after["facts"])
        assert {f["coupon_code"] for f in after["facts"]} == {"C-B"}
    else:
        # 净额口径：行数 +1（负向行），净额降到 20
        assert after["open_count"] == 3
        assert after["open_total"] == pytest.approx(20.0)
        assert after["void_net_count"] == 1
        assert any(f["status"] == "open_void" for f in after["facts"])

    # 再钉一次，预览与批次一致
    seal = client.post("/api/redeem/seal", json={}).json()
    assert seal["total_amount"] == pytest.approx(after["open_total"])


def test_never_pin_preview_never_contains_negative_rows(client, use_day):
    set_policy(client, "never_pin")
    redeem(client, "C-A", 10.0)
    redeem(client, "C-B", 20.0)
    void(client, "C-A")
    preview = client.get("/api/redeem/preview").json()
    assert all(f["amount"] > 0 for f in preview["facts"])
    assert preview["void_net_count"] == 0 and preview["void_net_amount"] == 0
