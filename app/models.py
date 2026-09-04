"""
SQLAlchemy ORM models.
Each class maps 1-to-1 with a PostgreSQL table defined in the ERD.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db import Base


def _uuid():
    return uuid.uuid4()


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Organizations — the top-level tenant (a company / app sending us events)
# ---------------------------------------------------------------------------
class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    # relationships
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="organization", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="organization", cascade="all, delete-orphan")
    webhook_endpoints = relationship("WebhookEndpoint", back_populates="organization", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="organization", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Users — human accounts that log in to manage an organization
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    role = Column(String(50), nullable=False, default="member")  # e.g. "owner", "member"
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    organization = relationship("Organization", back_populates="users")


# ---------------------------------------------------------------------------
# API Keys — machine credentials; separate from human user accounts
# ---------------------------------------------------------------------------
class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True)   # SHA-256 hex digest
    key_prefix = Column(String(8), nullable=False)               # first 8 chars shown in the UI
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    organization = relationship("Organization", back_populates="api_keys")
    events = relationship("Event", back_populates="api_key")


# ---------------------------------------------------------------------------
# Events — the core entity: every incoming event stored durably here
# ---------------------------------------------------------------------------
class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    api_key_id = Column(UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    event_type = Column(String(100), nullable=False)
    payload = Column(JSONB, nullable=False)
    # "received" → "processing" → "processed" | "failed"
    status = Column(String(20), nullable=False, default="received")
    received_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    # Database-level uniqueness guarantee — stronger than application checks alone
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_events_org_idempotency"),
    )

    organization = relationship("Organization", back_populates="events")
    api_key = relationship("ApiKey", back_populates="events")
    deliveries = relationship("WebhookDelivery", back_populates="event", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Webhook Endpoints — URLs an organization wants events forwarded to
# ---------------------------------------------------------------------------
class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    url = Column(Text, nullable=False)
    secret = Column(String(64), nullable=False)   # used to sign payloads (HMAC)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    organization = relationship("Organization", back_populates="webhook_endpoints")
    deliveries = relationship("WebhookDelivery", back_populates="endpoint", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Webhook Deliveries — one row per delivery attempt (success or failure)
# ---------------------------------------------------------------------------
class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    webhook_endpoint_id = Column(UUID(as_uuid=True), ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False)
    attempt_number = Column(Integer, nullable=False, default=1)
    # "success" | "failed"
    status = Column(String(20), nullable=False)
    response_status_code = Column(Integer, nullable=True)  # HTTP status returned by client
    error_detail = Column(Text, nullable=True)             # exception message if failed
    attempted_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)  # set when scheduling backoff

    event = relationship("Event", back_populates="deliveries")
    endpoint = relationship("WebhookEndpoint", back_populates="deliveries")


# ---------------------------------------------------------------------------
# Audit Logs — permanent record of "who did what, when"
# ---------------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    # "api_key" | "user" | "system"
    actor_type = Column(String(20), nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=True)   # FK to api_key or user; nullable for system actions
    action = Column(String(100), nullable=False)           # e.g. "event.created", "api_key.revoked"
    extra = Column(JSONB, nullable=True)                   # optional extra context (renamed: 'metadata' is reserved)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    organization = relationship("Organization", back_populates="audit_logs")
