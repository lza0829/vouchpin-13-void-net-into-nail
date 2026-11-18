from __future__ import annotations
import sqlite3
from typing import Any

# 状态：open=待钉正向事实；voided=已被作废的正向事实（never_pin）；
#       sealed=已随批钉扎；open_void=待钉负向对冲事实（net_pin）
VALID_STATUSES = {"open", "voided", "sealed", "open_void"}


def list_facts(conn: sqlite3.Connection, business_day: str | None = None) -> list[dict[str, Any]]:
    if business_day:
        rows = conn.execute(
            "SELECT * FROM redeem_facts WHERE business_day=? ORDER BY id",
            (business_day,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM redeem_facts ORDER BY id DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]


def insert_fact(conn: sqlite3.Connection, **fields: Any) -> int:
    status = fields.get("status") or "open"
    if status not in VALID_STATUSES:
        raise ValueError(f"非法事实状态 {status}")
    cur = conn.execute(
        """
        INSERT INTO redeem_facts(
          coupon_code, campaign_code, amount, business_day, event_id, status,
          void_event_id, voided_fact_id
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            fields["coupon_code"],
            fields["campaign_code"],
            float(fields["amount"]),
            fields["business_day"],
            int(fields["event_id"]),
            status,
            fields.get("void_event_id"),
            fields.get("voided_fact_id"),
        ),
    )
    return int(cur.lastrowid)


def find_positive_fact_by_coupon(
    conn: sqlite3.Connection, coupon_code: str
) -> dict[str, Any] | None:
    """
    找该券码最新一条正向事实（任意状态：open/sealed/voided）。
    负向对冲行的 voided_fact_id 非空，天然排除；状态语义由服务层判定。
    """
    row = conn.execute(
        "SELECT * FROM redeem_facts "
        "WHERE coupon_code=? AND voided_fact_id IS NULL ORDER BY id DESC LIMIT 1",
        (coupon_code,),
    ).fetchone()
    return dict(row) if row else None

def mark_voided(
    conn: sqlite3.Connection, fact_id: int, void_event_id: int
) -> None:
    """never_pin：把正向 open 事实置 voided 并回链作废事件，不物理删除。"""
    conn.execute(
        "UPDATE redeem_facts SET status='voided', void_event_id=? WHERE id=?",
        (void_event_id, fact_id),
    )


def pin_candidates(
    conn: sqlite3.Connection, business_day: str, void_policy: str
) -> list[dict[str, Any]]:
    """
    全局唯一的「将钉集合」口径，预览与 seal 必须共用：
    - never_pin：只含正向 open 事实，不含任何负向行；
    - net_pin：含正向 open 与负向 open_void，按发生顺序（id）排列便于看对冲。
    """
    if void_policy == "net_pin":
        rows = conn.execute(
            "SELECT * FROM redeem_facts "
            "WHERE business_day=? AND status IN ('open', 'open_void') ORDER BY id",
            (business_day,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM redeem_facts "
            "WHERE business_day=? AND status='open' ORDER BY id",
            (business_day,),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_batched(conn: sqlite3.Connection, fact_ids: list[int], batch_id: int) -> None:
    for fid in fact_ids:
        conn.execute(
            "UPDATE redeem_facts SET status='sealed', batch_id=? WHERE id=?",
            (batch_id, fid),
        )


def day_is_sealed(conn: sqlite3.Connection, business_day: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM redeem_batches WHERE business_day=? AND status='sealed' LIMIT 1",
        (business_day,),
    ).fetchone()
    return row is not None


def has_open_facts(conn: sqlite3.Connection) -> bool:
    """是否还存在任何待钉事实（切策略前的护栏）。"""
    row = conn.execute(
        "SELECT 1 FROM redeem_facts WHERE status IN ('open', 'open_void') LIMIT 1"
    ).fetchone()
    return row is not None
