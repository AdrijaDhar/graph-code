from graphcode.saas.models import init_db
from graphcode.saas.usage import PLANS, check_quota, remaining


def test_free_plan_exists():
    init_db()
    assert "free" in PLANS
    rem = remaining(0, "free")
    assert rem["queries_limit"] == PLANS["free"]["queries_per_day"]
    ok, _ = check_quota(0, "free", "query")
    assert ok
