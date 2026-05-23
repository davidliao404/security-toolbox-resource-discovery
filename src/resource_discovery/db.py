from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, Integer, MetaData, String, Table, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()


def json_column(name: str, *, nullable: bool = False) -> Column:
    return Column(name, JSONB, nullable=nullable)


tasks = Table(
    "tasks",
    metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("task_id", String(128), primary_key=True),
    Column("client_id", String(128), nullable=False, default=""),
    Column("status", String(64), nullable=False),
    json_column("payload"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_tasks_client_id", "client_id"),
    Index("ix_tasks_tenant_status_created", "tenant_id", "status", "created_at"),
)

task_results = Table(
    "task_results",
    metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("task_id", String(128), primary_key=True),
    Column("result_type", String(64), primary_key=True),
    Column("position", Integer, primary_key=True),
    json_column("payload"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_results_tenant_task_type_position", "tenant_id", "task_id", "result_type", "position"),
)

scope_profiles = Table(
    "scope_profiles",
    metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("profile_id", String(128), primary_key=True),
    Column("status", String(64), nullable=False),
    json_column("payload"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_scope_profiles_tenant_status", "tenant_id", "status"),
)

request_nonces = Table(
    "request_nonces",
    metadata,
    Column("nonce", String(256), primary_key=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Index("ix_nonces_expires_at", "expires_at"),
)

audit_events = Table(
    "audit_events",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("tenant_id", String(128), nullable=False),
    Column("task_id", String(128), nullable=False),
    Column("event_type", String(128), nullable=False),
    json_column("details"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_audit_events_tenant_created", "tenant_id", "created_at"),
    Index("ix_audit_events_task", "tenant_id", "task_id"),
)

queue_jobs = Table(
    "queue_jobs",
    metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("task_id", String(128), primary_key=True),
    Column("state", String(64), nullable=False),
    Column("attempts", Integer, nullable=False, default=0),
    Column("last_error", Text, nullable=False, default=""),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_queue_jobs_state_available", "state", "available_at", "created_at"),
    Index("ix_queue_jobs_tenant_state", "tenant_id", "state"),
)

client_secrets = Table(
    "client_secrets",
    metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("client_id", String(128), primary_key=True),
    Column("secret_ref", String(512), nullable=False),
    Column("active", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_client_secrets_active", "tenant_id", "client_id", "active"),
)

retention_policies = Table(
    "retention_policies",
    metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("task_days", Integer, nullable=False, default=180),
    Column("result_days", Integer, nullable=False, default=90),
    Column("audit_days", Integer, nullable=False, default=365),
    Column("nonce_days", Integer, nullable=False, default=1),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

rate_limit_buckets = Table(
    "rate_limit_buckets",
    metadata,
    Column("tenant_id", String(128), nullable=False),
    Column("bucket_name", String(128), nullable=False),
    Column("window_start", DateTime(timezone=True), nullable=False),
    Column("used", Integer, nullable=False, default=0),
    Column("limit_value", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("tenant_id", "bucket_name", "window_start", name="uq_rate_limit_bucket"),
    Index("ix_rate_limit_tenant_bucket", "tenant_id", "bucket_name"),
)
