from __future__ import annotations
from typing import Any
from fastapi import HTTPException
from app.db import connect
from app.policy import VOID_POLICIES, DEFAULT_VOID_POLICY
from app.repositories import settings as settings_repo
from app.repositories import facts as fact_repo


def get_day() -> dict[str, Any]:
    conn = connect()
    try:
        return {"business_day": settings_repo.get(conn, "business_day")}
    finally:
        conn.close()


def set_day(body: dict[str, Any]) -> dict[str, Any]:
    day = (body.get("business_day") or "").strip()
    if len(day) != 10:
        raise HTTPException(400, "business_day 格式 YYYY-MM-DD")
    conn = connect(immediate=True)
    try:
        settings_repo.set_(conn, "business_day", day)
        conn.commit()
        return {"business_day": day}
    finally:
        conn.close()


def get_void_policy() -> dict[str, Any]:
    conn = connect()
    try:
        return {
            "void_policy": settings_repo.get_void_policy(conn),
            "options": list(VOID_POLICIES),
            "default": DEFAULT_VOID_POLICY,
        }
    finally:
        conn.close()


def set_void_policy(body: dict[str, Any]) -> dict[str, Any]:
    policy = (body.get("void_policy") or "").strip()
    if policy not in VOID_POLICIES:
        raise HTTPException(
            400, f"void_policy 须为 { '/'.join(VOID_POLICIES) }"
        )
    conn = connect(immediate=True)
    try:
        current = settings_repo.get_void_policy(conn)
        if policy == current:
            return {"void_policy": policy, "changed": False}
        # 有待钉事实时切策略会让同一批 open 行换口径，拒绝，保证全局互斥不串味
        if fact_repo.has_open_facts(conn):
            raise HTTPException(
                409, "仍存在待钉（open/open_void）事实，请先钉扎或处理后再切换作废策略"
            )
        settings_repo.set_(conn, "void_policy", policy)
        conn.commit()
        return {"void_policy": policy, "changed": True}
    finally:
        conn.close()
