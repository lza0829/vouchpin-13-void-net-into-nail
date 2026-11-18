from __future__ import annotations
from typing import Any
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo
from app.repositories import events as event_repo


def dashboard() -> dict[str, Any]:
    conn = connect()
    try:
        day = settings_repo.get(conn, "business_day")
        policy = settings_repo.get_void_policy(conn)
        facts = fact_repo.list_facts(conn, day)
        open_n = sum(1 for f in facts if f["status"] == "open")
        sealed_n = sum(1 for f in facts if f["status"] == "sealed")
        voided_n = sum(1 for f in facts if f["status"] == "voided")
        open_void_n = sum(1 for f in facts if f["status"] == "open_void")
        events = event_repo.list_events(conn, day)
        # 事件湖口径：核销毛额（正向）与作废额（负向），两策略都可查
        gross = round(
            sum(float(e["amount"]) for e in events if e["event_type"] == "redeem"), 2
        )
        void_amt = round(
            sum(float(e["amount"]) for e in events if e["event_type"] == "void"), 2
        )
        batches = batch_repo.list_batches(conn)
        sealed_today = fact_repo.day_is_sealed(conn, day)
        return {
            "business_day": day,
            "void_policy": policy,
            "event_count": len(events),
            "void_event_count": sum(1 for e in events if e["event_type"] == "void"),
            "fact_count": len(facts),
            "open_fact_count": open_n,
            "sealed_fact_count": sealed_n,
            "voided_fact_count": voided_n,
            "open_void_fact_count": open_void_n,
            "redeem_gross_today": gross,
            "void_amount_today": void_amt,
            "redeem_net_today": round(gross + void_amt, 2),
            # 兼容旧字段名：净额（net_pin 下含负向、never_pin 下剔除已作废）
            "redeem_total_today": round(gross + void_amt, 2),
            "batch_count": len(batches),
            "day_sealed": sealed_today,
        }
    finally:
        conn.close()
