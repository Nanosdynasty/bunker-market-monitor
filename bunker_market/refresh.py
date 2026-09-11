import socket
import uuid
from datetime import date, timedelta

from flask import current_app
from sqlalchemy.exc import IntegrityError

from .models import Observation, Port, ProviderState, RefreshLease, RefreshRun, db, utcnow
from .normalization import port_identity
from .providers import BulugoAdapter, OilPriceAPIAdapter
from .providers.base import ProviderError


LEASE_SECONDS = 120


def build_adapters():
    config = current_app.config
    return [
        (
            BulugoAdapter(
                config["BULUGO_API_KEY"],
                config["BULUGO_API_URL"],
                config["PROVIDER_TIMEOUT_SECONDS"],
            ),
            config["BULUGO_DAILY_QUOTA"],
        ),
        (
            OilPriceAPIAdapter(
                config["OILPRICEAPI_KEY"],
                config["OILPRICEAPI_URL"],
                config["PROVIDER_TIMEOUT_SECONDS"],
            ),
            config["OILPRICEAPI_DAILY_QUOTA"],
        ),
    ]


def ensure_provider_states() -> None:
    for adapter, quota in build_adapters():
        state = db.session.get(ProviderState, adapter.provider_id)
        if not state:
            state = ProviderState(id=adapter.provider_id, name=adapter.display_name)
            db.session.add(state)
        state.configured = adapter.configured
        state.daily_quota = quota
        if not adapter.configured and state.status != "demo":
            state.status = "not_configured"
    db.session.commit()


def _acquire_lease(owner: str) -> bool:
    now = utcnow()
    lease = db.session.get(RefreshLease, 1)
    if not lease:
        lease = RefreshLease(id=1)
        db.session.add(lease)
        db.session.flush()
    if lease.locked_until and lease.locked_until > now and lease.owner != owner:
        db.session.rollback()
        return False
    lease.owner = owner
    lease.locked_until = now + timedelta(seconds=LEASE_SECONDS)
    db.session.commit()
    return True


def _release_lease(owner: str) -> None:
    lease = db.session.get(RefreshLease, 1)
    if lease and lease.owner == owner:
        lease.owner = None
        lease.locked_until = None
        db.session.commit()


def _reset_quota_day(state: ProviderState) -> None:
    today = date.today()
    if state.quota_date != today:
        state.quota_date = today
        state.requests_today = 0


def _upsert_observations(provider_id: str, observations) -> int:
    inserted = 0
    for item in observations:
        identity = port_identity(item.port_name, item.country, item.region)
        port = db.session.get(Port, identity["code"])
        if not port:
            port = Port(**identity)
            db.session.add(port)
        exists = Observation.query.filter_by(
            provider_id=provider_id,
            port_code=identity["code"],
            grade=item.grade,
            source_time=item.source_time,
        ).first()
        if exists:
            continue
        db.session.add(
            Observation(
                provider_id=provider_id,
                port_code=identity["code"],
                grade=item.grade,
                price=item.price,
                currency=item.currency,
                unit=item.unit,
                source_time=item.source_time,
                retrieved_at=utcnow(),
                provenance_url=item.provenance_url,
                source_label=item.source_label,
                stale_upstream=item.stale_upstream,
                synthetic=item.synthetic,
            )
        )
        inserted += 1
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ProviderError("Duplicate or conflicting provider observations")
    return inserted


def perform_refresh(trigger: str = "manual", force: bool = False) -> dict:
    owner = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
    if not _acquire_lease(owner):
        return {"status": "already_running", "inserted": 0, "providers": []}

    run = RefreshRun(trigger=trigger)
    db.session.add(run)
    db.session.commit()
    results = []
    total_inserted = 0
    errors = []
    now = utcnow()

    try:
        for adapter, quota in build_adapters():
            state = db.session.get(ProviderState, adapter.provider_id)
            _reset_quota_day(state)
            if not adapter.configured:
                if state.status != "demo":
                    state.status = "not_configured"
                results.append({"provider": adapter.provider_id, "status": state.status})
                continue
            if state.requests_today >= quota:
                state.status = "rate_limited"
                state.last_error = "Configured daily request budget has been reached"
                results.append({"provider": adapter.provider_id, "status": "rate_limited"})
                continue
            if not force and state.next_allowed_at and state.next_allowed_at > now:
                results.append({"provider": adapter.provider_id, "status": "cooldown"})
                continue

            state.last_attempt_at = now
            state.requests_today += 1
            state.next_allowed_at = now + timedelta(
                minutes=current_app.config["REFRESH_INTERVAL_MINUTES"]
            )
            db.session.commit()
            try:
                observations = adapter.fetch()
                inserted = _upsert_observations(adapter.provider_id, observations)
                total_inserted += inserted
                state = db.session.get(ProviderState, adapter.provider_id)
                state.status = "current"
                state.last_success_at = utcnow()
                state.last_error = None
                state.records_last_run = len(observations)
                state.ports_last_run = len({o.port_name for o in observations})
                db.session.commit()
                results.append(
                    {
                        "provider": adapter.provider_id,
                        "status": "current",
                        "received": len(observations),
                        "inserted": inserted,
                    }
                )
            except ProviderError as exc:
                state = db.session.get(ProviderState, adapter.provider_id)
                state.status = "rate_limited" if exc.status_code == 429 else "unavailable"
                state.last_error = str(exc)
                db.session.commit()
                errors.append(f"{adapter.display_name}: {exc}")
                results.append(
                    {"provider": adapter.provider_id, "status": state.status, "error": str(exc)}
                )

        run = db.session.get(RefreshRun, run.id)
        run.finished_at = utcnow()
        run.inserted_count = total_inserted
        run.status = "partial" if errors and total_inserted else "failed" if errors else "complete"
        run.error_summary = "; ".join(errors) or None
        db.session.commit()
        return {"status": run.status, "inserted": total_inserted, "providers": results}
    finally:
        _release_lease(owner)
