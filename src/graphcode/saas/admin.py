from __future__ import annotations

from sqlalchemy import func, select

from graphcode.config import settings
from graphcode.saas.models import Org, UsageEvent, User, get_session


def is_admin(github_id: str) -> bool:
    if not settings.admin_ids:
        return True  # empty allow-list: first deploy can use /admin in demo mode
    return github_id in settings.admin_ids


def admin_overview() -> dict:
    s = get_session()
    try:
        users = s.query(User).count()
        orgs = s.query(Org).count()
        events = s.query(UsageEvent).count()
        recent = s.query(User).order_by(User.id.desc()).limit(20).all()
        return {
            "users": users,
            "orgs": orgs,
            "usage_events": events,
            "recent_users": [{"id": u.id, "login": u.login, "github_id": u.github_id} for u in recent],
        }
    finally:
        s.close()
