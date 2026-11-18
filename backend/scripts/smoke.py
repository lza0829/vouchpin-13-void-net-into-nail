#!/usr/bin/env python3
"""端到端冒烟：真实 HTTP 调用，核对两策略的合计与明细。用前清库。"""
from __future__ import annotations
import json
import os
import sys
import urllib.request
import urllib.error

BASE = os.environ.get("SMOKE_BASE", "http://localhost:10811/api")


def call(method: str, path: str, body: dict | None = None, expect: int = 200):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            payload = json.loads(r.read())
            code = r.status
    except urllib.error.HTTPError as e:
        payload = json.loads(e.read())
        code = e.code
    assert code == expect, f"{method} {path} -> {code}（期望 {expect}）: {payload}"
    return payload


def check(name: str, got, want):
    assert got == want, f"{name}: 得 {got!r}，期望 {want!r}"
    print(f"  ok  {name} = {got!r}")


def redeem(code, amount, camp="NEW10"):
    call("POST", "/events", {"event_type": "redeem", "coupon_code": code,
                             "campaign_code": camp, "amount": amount})


def void(code, camp="NEW10", expect=200):
    return call("POST", "/events", {"event_type": "void", "coupon_code": code,
                                    "campaign_code": camp}, expect=expect)


def set_day(day):
    call("PUT", "/settings/day", {"business_day": day})


def set_policy(policy, expect=200):
    return call("PUT", "/settings/void-policy", {"void_policy": policy}, expect=expect)


def main() -> None:
    # 干净起点：默认 never_pin
    check("默认策略", call("GET", "/settings/void-policy")["void_policy"], "never_pin")

    # seed 可能在其它业务日留 open 事实，先全部钉干净，避免干扰策略切换护栏
    today = call("GET", "/settings/day")["business_day"]
    set_day(today)
    if call("GET", "/redeem/preview")["open_count"] > 0:
        call("POST", "/redeem/seal", {})

    print("[A] never_pin：核销→作废→预览→钉扎→钉后作废拒绝")
    set_day("2026-11-17")
    base_n = call("GET", "/redeem/preview")["open_count"]
    base_total = call("GET", "/redeem/preview")["open_total"]
    redeem("S-A", 10)
    redeem("S-B", 20, "VIP20")
    v = void("S-B", "VIP20")
    check("作废作用事实", v["voided_fact_id"] is not None, True)
    p = call("GET", "/redeem/preview")
    # 相对增量：两笔核销一笔作废，open 只 +1，金额只 +10
    check("never_pin 预览笔数增量", p["open_count"] - base_n, 1)
    check("never_pin 预览合计增量", round(p["open_total"] - base_total, 2), 10.0)
    check("never_pin 无负向行", p["void_net_count"], 0)
    check("never_pin 全正向", all(f["amount"] > 0 for f in p["facts"]), True)
    check("S-B 已移出待钉", {f["coupon_code"] for f in p["facts"]} & {"S-B"}, set())
    seal = call("POST", "/redeem/seal", {})
    check("预览=将钉合计", seal["total_amount"], p["open_total"])
    detail = call("GET", f"/batches/{seal['batch_id']}")
    check("批明细与批头一致", detail["matches_header"], True)
    check("快照不含已作废券", {r["coupon_code"] for r in detail["facts"]} & {"S-B"}, set())
    void("S-A", expect=409)
    print("  ok  sealed 后作废 -> 409")

    print("[B] 切换 net_pin（无待钉时允许）")
    check("切换成功", set_policy("net_pin")["changed"], True)

    print("[C] net_pin：核销→作废→预览（负向对冲）→钉扎→快照对冲关系")
    set_day("2026-11-16")
    base_n = call("GET", "/redeem/preview")["open_count"]
    base_total = call("GET", "/redeem/preview")["open_total"]
    redeem("N-A", 10)
    redeem("N-B", 20, "VIP20")
    v = void("N-B", "VIP20")
    check("net_pin 生成负向事实", v["fact_id"] is not None, True)
    p = call("GET", "/redeem/preview")
    # 两正一负：行数 +3，净额只 +10
    check("net_pin 预览笔数增量", p["open_count"] - base_n, 3)
    check("net_pin 净额增量", round(p["open_total"] - base_total, 2), 10.0)
    check("net_pin 负向笔数", p["void_net_count"], 1)
    check("net_pin 负向金额", p["void_net_amount"], -20.0)
    neg = [f for f in p["facts"] if f["status"] == "open_void"]
    check("负向行回链存在", len(neg) == 1 and neg[0]["voided_fact_id"] is not None, True)
    seal = call("POST", "/redeem/seal", {})
    check("预览=将钉净额", seal["total_amount"], p["open_total"])
    check("批头负向笔数", seal["void_net_count"], 1)
    check("批头负向金额", seal["void_net_amount"], -20.0)
    detail = call("GET", f"/batches/{seal['batch_id']}")
    check("快照自洽", detail["matches_header"], True)
    nb = [r for r in detail["facts"] if r["coupon_code"] == "N-B"]
    check("N-B 正负成对", len(nb), 2)
    check("N-B 对冲为零", round(sum(r["amount"] for r in nb), 2), 0.0)

    print("[D] net_pin 钉后作废拒绝，且不落其它日、事件湖不物理删除")
    void("N-A", expect=409)
    call("POST", "/events",
         {"event_type": "void", "coupon_code": "N-A", "campaign_code": "NEW10",
          "business_day": "2026-11-15"}, expect=409)
    other = call("GET", "/facts?business_day=2026-11-15")
    check("其它日无负向事实", other, [])
    events = call("GET", "/events?business_day=2026-11-16")
    check("事件湖保留作废事件",
          [(e["event_type"], e["coupon_code"], e["amount"]) for e in events],
          [("redeem", "N-A", 10.0), ("redeem", "N-B", 20.0), ("void", "N-B", -20.0)])

    print("[E] 护栏：有待钉事实时禁止切策略")
    set_day("2026-11-14")
    redeem("N-C", 5, "TEA5")
    set_policy("never_pin", expect=409)
    print("  ok  open 存在时切换 -> 409")

    print("\n全部端到端断言通过 ✔")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\n断言失败: {e}", file=sys.stderr)
        sys.exit(1)
