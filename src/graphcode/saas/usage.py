from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from graphcode.saas.models import UsageEvent, get_session

PLANS = {
    "free": {"repos": 2, "queries_per_day": 50, "indexes_per_day": 1, "price": 0},
    "pro": {"repos": 10, "queries_per_day": 2000, "indexes_per_day": 100, "price": 0},
    "team": {"repos": 50, "queries_per_day": 10000, "indexes_per_day": 500, "price": 0},
}


def record_usage(org_id: int, kind: str, tokens_out: int = 0, latency_ms: int = 0) -> None:
    s = get_session()
    try:
        s.add(UsageEvent(org_id=org_id, kind=kind, tokens_out=tokens_out, latency_ms=latency_ms))
        s.commit()
    finally:
        s.close()


def count_today(org_id: int, kind_prefix: str) -> int:
    s = get_session()
    try:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        q = select(func.count(UsageEvent.id)).where(
            UsageEvent.org_id == org_id,
            UsageEvent.kind.like(f"{kind_prefix}%"),
            UsageEvent.created_at >= start,
        )
        return int(s.execute(q).scalar() or 0)
    finally:
        s.close()


def remaining(org_id: int, plan: str) -> dict:
    limits = PLANS.get(plan, PLANS["free"])
    q = count_today(org_id, "query")
    i = count_today(org_id, "index")
    return {
        "plan": plan,
        "queries_used": q,
        "queries_limit": limits["queries_per_day"],
        "indexes_used": i,
        "indexes_limit": limits["indexes_per_day"],
        "repos_limit": limits["repos"],
    }


def check_quota(org_id: int, plan: str, kind: str) -> tuple[bool, str]:
    rem = remaining(org_id, plan)
    if kind.startswith("query") and rem["queries_used"] >= rem["queries_limit"]:
        return False, "Daily query quota exceeded. Upgrade on /app/usage."
    if kind.startswith("index") and rem["indexes_used"] >= rem["indexes_limit"]:
        return False, "Daily index quota exceeded. Upgrade on /app/usage."
    return True, ""
