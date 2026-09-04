from __future__ import annotations

import uuid

from graphcode.saas.models import Membership, Org, User, init_db


def test_db_roundtrip_org_user_membership():
    Session = init_db()
    uid = uuid.uuid4().hex[:8]
    with Session() as s:
        user = User(github_id=f"gh-{uid}", login=f"user-{uid}", name="Test User")
        s.add(user)
        s.flush()
        org = Org(name=f"org-{uid}")
        s.add(org)
        s.flush()
        s.add(Membership(user_id=user.id, org_id=org.id, role="owner"))
        s.commit()
        user_id, org_id = user.id, org.id

    with Session() as s:
        fetched_user = s.get(User, user_id)
        fetched_org = s.get(Org, org_id)
        assert fetched_user is not None and fetched_user.login == f"user-{uid}"
        assert fetched_org is not None and fetched_org.plan == "free"
        mem = s.query(Membership).filter_by(user_id=user_id, org_id=org_id).first()
        assert mem is not None and mem.role == "owner"


def test_org_stripe_fields_persist():
    Session = init_db()
    uid = uuid.uuid4().hex[:8]
    with Session() as s:
        org = Org(name=f"stripe-org-{uid}", plan="pro", stripe_customer_id="cus_test123")
        s.add(org)
        s.commit()
        org_id = org.id

    with Session() as s:
        fetched = s.get(Org, org_id)
        assert fetched.plan == "pro"
        assert fetched.stripe_customer_id == "cus_test123"
