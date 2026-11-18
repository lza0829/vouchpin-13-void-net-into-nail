from __future__ import annotations
import sqlite3
from typing import Any


def list_batches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM redeem_batches ORDER BY id DESC"
    ).fetchall()]


def get_batch(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM redeem_batches WHERE id=?", (batch_id,)
    ).fetchone()
    return dict(row) if row else None


def create_batch(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        """
        INSERT INTO redeem_batches(
          business_day, status, fact_count, total_amount,
          void_net_count, void_net_amount, sealed_at, note
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            fields["business_day"],
            fields.get("status") or "sealed",
            int(fields.get("fact_count") or 0),
            float(fields.get("total_amount") or 0),
            int(fields.get("void_net_count") or 0),
            float(fields.get("void_net_amount") or 0),
            fields.get("sealed_at"),
            fields.get("note") or "",
        ),
    )
    return int(cur.lastrowid)


def add_snapshot_rows(conn: sqlite3.Connection, batch_id: int, facts: list[dict[str, Any]]) -> None:
    """seal 时把将钉集合逐行固化成批明细快照（含负向对冲行与对冲回链）。"""
    for seq, f in enumerate(facts):
        conn.execute(
            """
            INSERT INTO redeem_batch_facts(
              batch_id, fact_id, coupon_code, campaign_code, amount, status,
              event_id, void_event_id, voided_fact_id, seq
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                batch_id,
                int(f["id"]),
                f["coupon_code"],
                f["campaign_code"],
                float(f["amount"]),
                f["status"],
                int(f["event_id"]),
                f["void_event_id"],
                f["voided_fact_id"],
                seq,
            ),
        )


def list_snapshot(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM redeem_batch_facts WHERE batch_id=? ORDER BY seq",
        (batch_id,),
    ).fetchall()
    return [dict(r) for r in rows]
