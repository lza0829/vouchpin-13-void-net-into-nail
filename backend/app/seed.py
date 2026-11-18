from __future__ import annotations
from datetime import date, timedelta
from app.db import connect, init_db
from app.policy import DEFAULT_VOID_POLICY


def seed_if_empty() -> None:
    init_db()
    conn = connect()
    try:
        n = conn.execute("SELECT COUNT(*) c FROM campaigns").fetchone()["c"]
        if n:
            return
        today = date.today().isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES('business_day', ?)",
            (today,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES('void_policy', ?)",
            (DEFAULT_VOID_POLICY,),
        )
        campaigns = [
            ("NEW10", "新人立减10", 10.0, 30.0),
            ("VIP20", "会员满减20", 20.0, 100.0),
            ("TEA5", "茶饮立减5", 5.0, 15.0),
        ]
        for code, title, face, mn in campaigns:
            conn.execute(
                "INSERT INTO campaigns(code, title, face_value, min_spend) VALUES(?,?,?,?)",
                (code, title, face, mn),
            )
        # issue + redeem events for today and yesterday
        yday = (date.today() - timedelta(days=1)).isoformat()
        rows = [
            ("issue", "C-1001", "NEW10", 0, today, f"{today}T09:00:00"),
            ("issue", "C-1002", "VIP20", 0, today, f"{today}T09:10:00"),
            ("issue", "C-1003", "TEA5", 0, today, f"{today}T09:20:00"),
            ("issue", "C-1004", "TEA5", 0, today, f"{today}T09:30:00"),
            ("redeem", "C-1001", "NEW10", 10, today, f"{today}T12:00:00"),
            ("redeem", "C-1002", "VIP20", 20, today, f"{today}T12:30:00"),
            ("redeem", "C-1003", "TEA5", 5, today, f"{today}T13:00:00"),
            # 先核销后作废：事件湖保留成对的 redeem(+5) / void(-5)
            ("void", "C-1003", "TEA5", -5, today, f"{today}T13:20:00"),
            ("issue", "C-0901", "NEW10", 0, yday, f"{yday}T10:00:00"),
            ("redeem", "C-0901", "NEW10", 10, yday, f"{yday}T18:00:00"),
        ]
        fact_ids: dict[str, int] = {}
        for et, cc, camp, amt, day, at in rows:
            cur = conn.execute(
                "INSERT INTO coupon_events(event_type, coupon_code, campaign_code, amount, business_day, occurred_at) VALUES(?,?,?,?,?,?)",
                (et, cc, camp, amt, day, at),
            )
            if et == "redeem":
                fcur = conn.execute(
                    "INSERT INTO redeem_facts(coupon_code, campaign_code, amount, business_day, event_id, status) VALUES(?,?,?,?,?, 'open')",
                    (cc, camp, amt, day, cur.lastrowid),
                )
                fact_ids[cc] = int(fcur.lastrowid)
            if et == "void" and cc in fact_ids:
                # 默认 never_pin：正向事实置 voided 回链作废事件，不物理删除
                conn.execute(
                    "UPDATE redeem_facts SET status='voided', void_event_id=? WHERE id=?",
                    (cur.lastrowid, fact_ids[cc]),
                )
        conn.commit()
    finally:
        conn.close()
