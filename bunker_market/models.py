from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint


db = SQLAlchemy()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ProviderState(db.Model):
    __tablename__ = "provider_states"

    id = db.Column(db.String(32), primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    configured = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(32), nullable=False, default="not_configured")
    last_attempt_at = db.Column(db.DateTime)
    last_success_at = db.Column(db.DateTime)
    next_allowed_at = db.Column(db.DateTime)
    last_error = db.Column(db.String(500))
    requests_today = db.Column(db.Integer, nullable=False, default=0)
    daily_quota = db.Column(db.Integer, nullable=False, default=0)
    quota_date = db.Column(db.Date)
    records_last_run = db.Column(db.Integer, nullable=False, default=0)
    ports_last_run = db.Column(db.Integer, nullable=False, default=0)


class Port(db.Model):
    __tablename__ = "ports"

    code = db.Column(db.String(12), primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    country = db.Column(db.String(100), nullable=False, default="Unknown")
    region = db.Column(db.String(80), nullable=False, default="Other")
    priority = db.Column(db.Integer, nullable=False, default=999)


class Observation(db.Model):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "port_code",
            "grade",
            "source_time",
            name="uq_observation_identity",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(
        db.String(32), db.ForeignKey("provider_states.id"), nullable=False, index=True
    )
    port_code = db.Column(
        db.String(12), db.ForeignKey("ports.code"), nullable=False, index=True
    )
    grade = db.Column(db.String(16), nullable=False, index=True)
    price = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(8), nullable=False, default="USD")
    unit = db.Column(db.String(16), nullable=False, default="MT")
    source_time = db.Column(db.DateTime, nullable=False, index=True)
    retrieved_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    provenance_url = db.Column(db.String(500))
    source_label = db.Column(db.String(120))
    stale_upstream = db.Column(db.Boolean, nullable=False, default=False)
    synthetic = db.Column(db.Boolean, nullable=False, default=False)


class RefreshLease(db.Model):
    __tablename__ = "refresh_leases"

    id = db.Column(db.Integer, primary_key=True, default=1)
    owner = db.Column(db.String(80))
    locked_until = db.Column(db.DateTime)


class RefreshRun(db.Model):
    __tablename__ = "refresh_runs"

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    finished_at = db.Column(db.DateTime)
    trigger = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="running")
    inserted_count = db.Column(db.Integer, nullable=False, default=0)
    error_summary = db.Column(db.String(1000))


class UploadState(db.Model):
    __tablename__ = "upload_states"

    id = db.Column(db.Integer, primary_key=True, default=1)
    file_name = db.Column(db.String(255))
    sheet_name = db.Column(db.String(255))
    uploaded_at = db.Column(db.DateTime)
    status = db.Column(db.String(32), nullable=False, default="waiting")
    layout = db.Column(db.String(40))
    rows_received = db.Column(db.Integer, nullable=False, default=0)
    ports_received = db.Column(db.Integer, nullable=False, default=0)
    skipped_cells = db.Column(db.Integer, nullable=False, default=0)
    formula_cache_missing = db.Column(db.Integer, nullable=False, default=0)
    excel_errors = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.String(1000))


class CloudWorkbookState(db.Model):
    __tablename__ = "cloud_workbook_states"

    session_id = db.Column(db.String(96), primary_key=True)
    drive_id = db.Column(db.String(255))
    item_id = db.Column(db.String(255))
    file_name = db.Column(db.String(255))
    file_path = db.Column(db.String(1000))
    worksheet = db.Column(db.String(255))
    worksheets_json = db.Column(db.Text)
    etag = db.Column(db.String(500))
    last_modified = db.Column(db.DateTime)
    last_checked = db.Column(db.DateTime)
    last_success = db.Column(db.DateTime)
    status = db.Column(db.String(32), nullable=False, default="waiting")
    changed = db.Column(db.Boolean, nullable=False, default=False)
    last_error = db.Column(db.String(1000))
