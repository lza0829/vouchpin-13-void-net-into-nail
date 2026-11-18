from __future__ import annotations
import sqlite3
from app.policy import DEFAULT_VOID_POLICY


def get(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row else default


def get_void_policy(conn: sqlite3.Connection) -> str:
    return get(conn, "void_policy", DEFAULT_VOID_POLICY)


def set_(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
