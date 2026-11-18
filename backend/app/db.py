from __future__ import annotations
import sqlite3
from app.config import DB_PATH

SCHEMA = '''
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaigns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  face_value REAL NOT NULL,
  min_spend REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS coupon_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  coupon_code TEXT NOT NULL,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL DEFAULT 0,
  business_day TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS redeem_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  coupon_code TEXT NOT NULL,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL,
  business_day TEXT NOT NULL,
  event_id INTEGER NOT NULL,
  batch_id INTEGER,
  status TEXT NOT NULL DEFAULT 'open',
  void_event_id INTEGER,
  voided_fact_id INTEGER
);
CREATE TABLE IF NOT EXISTS redeem_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  business_day TEXT NOT NULL,
  status TEXT NOT NULL,
  fact_count INTEGER NOT NULL DEFAULT 0,
  total_amount REAL NOT NULL DEFAULT 0,
  void_net_count INTEGER NOT NULL DEFAULT 0,
  void_net_amount REAL NOT NULL DEFAULT 0,
  sealed_at TEXT,
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS redeem_batch_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL,
  fact_id INTEGER NOT NULL,
  coupon_code TEXT NOT NULL,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL,
  status TEXT NOT NULL,
  event_id INTEGER NOT NULL,
  void_event_id INTEGER,
  voided_fact_id INTEGER,
  seq INTEGER NOT NULL DEFAULT 0
);
'''

# 依赖新列的索引，在迁移完成后再建
POST_MIGRATION_INDEXES = '''
-- 每券码至多一条正向事实（open/voided/sealed 历史行都占位，沿用 v1 单券单次核销）；
-- 负向对冲行 voided_fact_id 非空，豁免唯一约束，允许同券正负成对。
CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_unique_live_coupon
  ON redeem_facts(coupon_code) WHERE voided_fact_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_facts_day_status
  ON redeem_facts(business_day, status);
CREATE INDEX IF NOT EXISTS idx_facts_batch ON redeem_facts(batch_id);
CREATE INDEX IF NOT EXISTS idx_batch_facts_batch ON redeem_batch_facts(batch_id);
'''


def connect(immediate: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if immediate:
        conn.execute("BEGIN IMMEDIATE")
    return conn


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    return column in cols


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _migrate(conn: sqlite3.Connection) -> None:
    """v1 -> v2: void linkage on facts, void-net header on batches, snapshot table."""
    if _table_exists(conn, "redeem_facts") and not _has_column(
        conn, "redeem_facts", "void_event_id"
    ):
        conn.execute(
            '''
            CREATE TABLE redeem_facts_v2 (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              coupon_code TEXT NOT NULL,
              campaign_code TEXT NOT NULL,
              amount REAL NOT NULL,
              business_day TEXT NOT NULL,
              event_id INTEGER NOT NULL,
              batch_id INTEGER,
              status TEXT NOT NULL DEFAULT 'open',
              void_event_id INTEGER,
              voided_fact_id INTEGER
            )
            '''
        )
        conn.execute(
            '''
            INSERT INTO redeem_facts_v2
              (id, coupon_code, campaign_code, amount, business_day, event_id, batch_id, status,
               void_event_id, voided_fact_id)
            SELECT id, coupon_code, campaign_code, amount, business_day, event_id, batch_id, status,
                   NULL, NULL
            FROM redeem_facts
            '''
        )
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name='redeem_facts_v2'"
        )
        conn.execute("DROP TABLE redeem_facts")
        conn.execute("ALTER TABLE redeem_facts_v2 RENAME TO redeem_facts")

    if _table_exists(conn, "redeem_batches"):
        if not _has_column(conn, "redeem_batches", "void_net_count"):
            conn.execute("ALTER TABLE redeem_batches ADD COLUMN void_net_count INTEGER NOT NULL DEFAULT 0")
        if not _has_column(conn, "redeem_batches", "void_net_amount"):
            conn.execute("ALTER TABLE redeem_batches ADD COLUMN void_net_amount REAL NOT NULL DEFAULT 0")

    if not _table_exists(conn, "redeem_batch_facts"):
        conn.execute(
            '''
            CREATE TABLE redeem_batch_facts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              batch_id INTEGER NOT NULL,
              fact_id INTEGER NOT NULL,
              coupon_code TEXT NOT NULL,
              campaign_code TEXT NOT NULL,
              amount REAL NOT NULL,
              status TEXT NOT NULL,
              event_id INTEGER NOT NULL,
              void_event_id INTEGER,
              voided_fact_id INTEGER,
              seq INTEGER NOT NULL DEFAULT 0
            )
            '''
        )

    # 老库补齐策略设置（seed 只在库空时跑）
    row = conn.execute(
        "SELECT 1 FROM settings WHERE key='void_policy'"
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES('void_policy', 'never_pin')"
        )


def init_db() -> None:
    conn = connect()
    try:
        # 先建表/迁移列，再建依赖新列的索引
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.executescript(POST_MIGRATION_INDEXES)
        conn.commit()
    finally:
        conn.close()
