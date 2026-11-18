from __future__ import annotations
from datetime import datetime
from typing import Any
from fastapi import HTTPException
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import events as event_repo
from app.repositories import facts as fact_repo
from app.repositories import campaigns as camp_repo


def list_campaigns() -> list[dict[str, Any]]:
    conn = connect()
    try:
        return camp_repo.list_all(conn)
    finally:
        conn.close()


def list_events(business_day: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        return event_repo.list_events(conn, day)
    finally:
        conn.close()


def _apply_void(
    conn, code: str, camp: str, day: str, occurred: str, note: str, void_policy: str
) -> dict[str, Any]:
    """
    作废入口的全局唯一实现。两策略共用事件湖写入，区别只在事实侧：
    - never_pin：正向 open 事实置 voided 并回链 void 事件，不产生负向行；
    - net_pin ：正向事实保留，另写一条同额负向 open_void 事实互相对冲。
    任何路径都不物理删除事件或事实。
    """
    fact = fact_repo.find_positive_fact_by_coupon(conn, code)
    if fact is None:
        raise HTTPException(404, f"券码 {code} 没有可作废的有效核销事实")
    if fact["status"] == "sealed":
        raise HTTPException(
            409,
            f"券码 {code} 的核销已随批次 #{fact['batch_id']} 钉扎（sealed 后不可改净额），作废被拒绝",
        )
    if fact["status"] == "voided":
        raise HTTPException(409, f"券码 {code} 的核销已作废，不可重复作废")
    if fact["business_day"] != day:
        raise HTTPException(
            400,
            f"作废事件须落在原核销业务日 {fact['business_day']}（当前业务日 {day}）",
        )
    # 作废事件以负金额入湖，与正向核销事件天然成对、可查对冲
    void_amount = -abs(float(fact["amount"]))
    void_event_id = event_repo.insert_event(
        conn,
        event_type="void",
        coupon_code=code,
        campaign_code=camp or fact["campaign_code"],
        amount=void_amount,
        business_day=day,
        occurred_at=occurred,
        note=note,
    )

    negative_fact_id = None
    if void_policy == "net_pin":
        # 净额进钉：负向事实待钉，seal 时与正向行净额计入
        negative_fact_id = fact_repo.insert_fact(
            conn,
            coupon_code=code,
            campaign_code=fact["campaign_code"],
            amount=void_amount,
            business_day=day,
            event_id=void_event_id,
            status="open_void",
            void_event_id=void_event_id,
            voided_fact_id=int(fact["id"]),
        )
    else:
        # 作废永不进钉：只移除出 open 集合（置 voided），钉扎集合不再含该券
        fact_repo.mark_voided(conn, int(fact["id"]), void_event_id)

    return {
        "event_id": void_event_id,
        "fact_id": negative_fact_id,
        "voided_fact_id": int(fact["id"]),
        "void_amount": void_amount,
        "void_policy": void_policy,
        "business_day": day,
    }


def add_event(body: dict[str, Any]) -> dict[str, Any]:
    conn = connect(immediate=True)
    try:
        day = body.get("business_day") or settings_repo.get(conn, "business_day")
        et = body.get("event_type")
        if et not in {"issue", "redeem", "void"}:
            raise HTTPException(400, "event_type 须为 issue/redeem/void")
        code = (body.get("coupon_code") or "").strip()
        camp = (body.get("campaign_code") or "").strip()
        if not code or not camp:
            raise HTTPException(400, "coupon_code / campaign_code 必填")
        if et == "redeem" and fact_repo.day_is_sealed(conn, day):
            raise HTTPException(409, f"业务日 {day} 核销已钉扎，禁止再写入核销")
        amount = float(body.get("amount") or 0)
        if et == "redeem" and amount <= 0:
            # default face value from campaign
            camps = {c["code"]: c for c in camp_repo.list_all(conn)}
            if camp in camps:
                amount = float(camps[camp]["face_value"])
        occurred = body.get("occurred_at") or datetime.now().replace(microsecond=0).isoformat()
        note = body.get("note") or ""

        if et == "void":
            result = _apply_void(
                conn, code, camp, day, occurred, note,
                settings_repo.get_void_policy(conn),
            )
            conn.commit()
            return result

        eid = event_repo.insert_event(
            conn,
            event_type=et,
            coupon_code=code,
            campaign_code=camp,
            amount=amount,
            business_day=day,
            occurred_at=occurred,
            note=note,
        )
        fact_id = None
        if et == "redeem":
            try:
                fact_id = fact_repo.insert_fact(
                    conn,
                    coupon_code=code,
                    campaign_code=camp,
                    amount=amount,
                    business_day=day,
                    event_id=eid,
                    status="open",
                )
            except Exception as e:
                raise HTTPException(409, f"核销事实写入失败（可能券码已核销）: {e}") from e
        conn.commit()
        return {"event_id": eid, "fact_id": fact_id, "business_day": day}
    finally:
        conn.close()
