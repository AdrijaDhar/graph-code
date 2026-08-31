from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from graphcode.config import settings


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    github_id: Mapped[str] = mapped_column(String(64), unique=True)
    login: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    memberships: Mapped[list[Membership]] = relationship(back_populates="user")


class Org(Base):
    __tablename__ = "orgs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    plan: Mapped[str] = mapped_column(String(32), default="free")
    stripe_customer_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    memberships: Mapped[list[Membership]] = relationship(back_populates="org")
    repos: Mapped[list[RepoRecord]] = relationship(back_populates="org")
    keys: Mapped[list[ApiKey]] = relationship(back_populates="org")


class Membership(Base):
    __tablename__ = "memberships"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"))
    role: Mapped[str] = mapped_column(String(32), default="owner")
    user: Mapped[User] = relationship(back_populates="memberships")
    org: Mapped[Org] = relationship(back_populates="memberships")


class RepoRecord(Base):
    __tablename__ = "repos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"))
    name: Mapped[str] = mapped_column(String(256))
    github_url: Mapped[str] = mapped_column(String(512), default="")
    local_path: Mapped[str] = mapped_column(String(512), default="")
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    org: Mapped[Org] = relationship(back_populates="repos")


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"))
    prefix: Mapped[str] = mapped_column(String(16))
    hashed: Mapped[str] = mapped_column(String(128))
    revoked: Mapped[int] = mapped_column(Integer, default=0)
    org: Mapped[Org] = relationship(back_populates="keys")


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(64))
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


_engine = None
SessionLocal = None


def init_db():
    global _engine, SessionLocal
    Path = __import__("pathlib").Path
    if settings.database_url.startswith("sqlite"):
        Path("data").mkdir(exist_ok=True)
    _engine = create_engine(settings.database_url, future=True)
    SessionLocal = sessionmaker(_engine, expire_on_commit=False)
    Base.metadata.create_all(_engine)
    return SessionLocal


def get_session():
    if SessionLocal is None:
        init_db()
    return SessionLocal()
