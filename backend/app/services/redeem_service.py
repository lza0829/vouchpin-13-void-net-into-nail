from __future__ import annotations
from datetime import datetime
from typing import Any
from fastapi import HTTPException
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo


def _summarize(candidates: list[dict[str, Any]]) -> tuple[int, float, int, float]:
    """返回 (总笔数, 合计净额, 负向笔数, 负向金额)；never_pin 时后两者恒为 0。"""
    count = len(candidates)
    total = round(sum(float(f["amount"]) for f in candidates), 2)
    void_rows = [f for f in candidates if f["status"] == "open_void"]
    void_count = len(void_rows)
    void_amount = round(sum(float(f["amount"]) for f in void_rows), 2)
    return count, total, void_count, void_amount


def list_facts(business_day: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        return fact_repo.list_facts(conn, day)
    finally:
        conn.close()


def preview(business_day: str | None = None) -> dict[str, Any]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        policy = settings_repo.get_void_policy(conn)
        # 与 seal 完全同源：同一个待钉集合、同一套汇总
        candidates = fact_repo.pin_candidates(conn, day, policy)
        count, total, void_count, void_amount = _summarize(candidates)
        return {
            "business_day": day,
            "void_policy": policy,
            "open_count": count,
            "open_total": total,
            "void_net_count": void_count,
            "void_net_amount": void_amount,
            "positive_count": count - void_count,
            "already_sealed": fact_repo.day_is_sealed(conn, day),
            "facts": candidates,
        }
    finally:
        conn.close()


def seal(body: dict[str, Any]) -> dict[str, Any]:
    conn = connect(immediate=True)
    try:
        day = body.get("business_day") or settings_repo.get(conn, "business_day")
        policy = settings_repo.get_void_policy(conn)
        if fact_repo.day_is_sealed(conn, day):
            raise HTTPException(409, f"业务日 {day} 已有 sealed 钉扎批")
        candidates = fact_repo.pin_candidates(conn, day, policy)
        if not candidates:
            raise HTTPException(400, "无可钉扎的 open 核销事实")
        count, total, void_count, void_amount = _summarize(candidates)
        bid = batch_repo.create_batch(
            conn,
            business_day=day,
            status="sealed",
            fact_count=count,
            total_amount=total,
            void_net_count=void_count,
            void_net_amount=void_amount,
            sealed_at=datetime.now().replace(microsecond=0).isoformat(),
            note=body.get("note") or "",
        )
        # 批明细快照：逐行固化（net_pin 含负向对冲行及 voided_fact_id 回链）
        batch_repo.add_snapshot_rows(conn, bid, candidates)
        fact_repo.mark_batched(conn, [int(f["id"]) for f in candidates], bid)
        conn.commit()
        return {
            "batch_id": bid,
            "business_day": day,
            "void_policy": policy,
            "fact_count": count,
            "total_amount": total,
            "void_net_count": void_count,
            "void_net_amount": void_amount,
            "status": "sealed",
        }
    finally:
        conn.close()


def list_batches() -> list[dict[str, Any]]:
    conn = connect()
    try:
        return batch_repo.list_batches(conn)
    finally:
        conn.close()


def batch_detail(batch_id: int) -> dict[str, Any]:
    conn = connect()
    try:
        batch = batch_repo.get_batch(conn, batch_id)
        if batch is None:
            raise HTTPException(404, f"批次 #{batch_id} 不存在")
        rows = batch_repo.list_snapshot(conn, batch_id)
        snap_total = round(sum(float(r["amount"]) for r in rows), 2)
        return {
            "batch": batch,
            "facts": rows,
            # 快照自洽校验：明细金额之和必须等于批头合计
            "snapshot_total": snap_total,
            "matches_header": snap_total == round(float(batch["total_amount"]), 2),
        }
    finally:
        conn.close()
