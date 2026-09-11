from collections import defaultdict
from datetime import timedelta

from flask import current_app

from .models import Observation, Port, ProviderState, RefreshRun, UploadState, db, utcnow


PROVIDER_ORDER = ["bulugo", "oilpriceapi", "excel"]
PROVIDER_NAMES = {"bulugo": "Bulugo", "oilpriceapi": "OilPriceAPI", "excel": "Excel upload"}
GRADES = ["VLSFO", "HSFO", "MGO"]


def iso(value):
    return value.isoformat(timespec="seconds") + "Z" if value else None


def freshness(source_time, stale_upstream=False):
    if stale_upstream:
        return "stale"
    if not source_time:
        return "no_data"
    age = utcnow() - source_time
    return (
        "current"
        if age <= timedelta(minutes=current_app.config["STALE_AFTER_MINUTES"])
        else "stale"
    )


def _latest_and_previous():
    observations = Observation.query.order_by(Observation.source_time.desc()).all()
    grouped = defaultdict(list)
    for obs in observations:
        grouped[(obs.port_code, obs.grade, obs.provider_id)].append(obs)
    return grouped


def ranked_ports(limit=15):
    grouped = _latest_and_previous()
    stats = defaultdict(lambda: {"providers": set(), "grades": set(), "freshest": None})
    for (port_code, grade, provider), values in grouped.items():
        latest = values[0]
        stats[port_code]["providers"].add(provider)
        stats[port_code]["grades"].add(grade)
        if not stats[port_code]["freshest"] or latest.source_time > stats[port_code]["freshest"]:
            stats[port_code]["freshest"] = latest.source_time
    ports = Port.query.all()
    ports.sort(
        key=lambda p: (
            -len(stats[p.code]["providers"]),
            -len(stats[p.code]["grades"]),
            -(stats[p.code]["freshest"].timestamp() if stats[p.code]["freshest"] else 0),
            p.priority,
            p.name,
        )
    )
    return ports[:limit], grouped


def _observation_payload(obs, previous=None):
    delta = round(obs.price - previous.price, 2) if previous else None
    return {
        "price": round(obs.price, 2),
        "delta": delta,
        "currency": obs.currency,
        "unit": obs.unit,
        "sourceTime": iso(obs.source_time),
        "retrievedAt": iso(obs.retrieved_at),
        "freshness": freshness(obs.source_time, obs.stale_upstream),
        "synthetic": obs.synthetic,
        "sourceLabel": obs.source_label,
    }


def dashboard_payload(port_code=None, grade="VLSFO", range_name="7D"):
    ports, grouped = ranked_ports(15)
    if not ports:
        return {"mode": "empty", "ports": [], "history": [], "selectedPort": None}
    selected = next((p for p in ports if p.code == port_code), ports[0])
    grade = grade if grade in GRADES else "VLSFO"
    range_name = range_name.upper()
    delta_map = {"24H": timedelta(hours=24), "7D": timedelta(days=7), "30D": timedelta(days=30)}
    cutoff = utcnow() - delta_map[range_name] if range_name in delta_map else None

    observed_providers = {key[2] for key in grouped}
    active_providers = [provider for provider in PROVIDER_ORDER if provider in observed_providers]
    card_rows = []
    for port in ports:
        grade_rows = []
        for item_grade in GRADES:
            providers = {}
            for provider in active_providers:
                values = grouped.get((port.code, item_grade, provider), [])
                providers[provider] = (
                    _observation_payload(values[0], values[1] if len(values) > 1 else None)
                    if values
                    else None
                )
            grade_rows.append({"grade": item_grade, "providers": providers})
        card_rows.append(
            {
                "code": port.code,
                "name": port.name,
                "country": port.country,
                "region": port.region,
                "grades": grade_rows,
            }
        )

    history = []
    for provider in active_providers:
        values = list(reversed(grouped.get((selected.code, grade, provider), [])))
        if cutoff:
            values = [obs for obs in values if obs.source_time >= cutoff]
        history.append(
            {
                "provider": provider,
                "points": [
                    {"time": iso(obs.source_time), "price": round(obs.price, 2)}
                    for obs in values
                ],
            }
        )

    has_real_data = Observation.query.filter_by(synthetic=False).first() is not None
    has_demo_data = Observation.query.filter_by(synthetic=True).first() is not None
    mode = "mixed" if has_real_data and has_demo_data else "live" if has_real_data else "demo"
    return {
        "mode": mode,
        "providers": [{"id": provider, "name": PROVIDER_NAMES[provider]} for provider in active_providers],
        "ports": card_rows,
        "selectedPort": {"code": selected.code, "name": selected.name},
        "selectedGrade": grade,
        "range": range_name,
        "history": history,
        "generatedAt": iso(utcnow()),
    }


def compare_payload(port_codes=None, grades=None):
    ports, grouped = ranked_ports(15)
    if port_codes:
        ports = [p for p in ports if p.code in port_codes]
    grades = [g for g in (grades or GRADES) if g in GRADES]
    rows = []
    for port in ports:
        for grade in grades:
            provider_values = {}
            prices = []
            for provider in PROVIDER_ORDER:
                values = grouped.get((port.code, grade, provider), [])
                payload = _observation_payload(values[0], values[1] if len(values) > 1 else None) if values else None
                provider_values[provider] = payload
                if payload:
                    prices.append(payload["price"])
            spread = round(max(prices) - min(prices), 2) if len(prices) >= 2 else None
            spread_pct = round(spread / min(prices) * 100, 2) if spread is not None and min(prices) else None
            rows.append(
                {
                    "portCode": port.code,
                    "port": port.name,
                    "country": port.country,
                    "grade": grade,
                    "providers": provider_values,
                    "spread": spread,
                    "spreadPct": spread_pct,
                }
            )
    return {"rows": rows, "generatedAt": iso(utcnow())}


def sources_payload():
    states = ProviderState.query.order_by(ProviderState.name).all()
    provider_rows = []
    for state in states:
        provider_rows.append(
            {
                "id": state.id,
                "name": state.name,
                "configured": state.configured,
                "status": state.status,
                "lastAttempt": iso(state.last_attempt_at),
                "lastSuccess": iso(state.last_success_at),
                "nextAllowed": iso(state.next_allowed_at),
                "lastError": state.last_error,
                "requestsToday": state.requests_today,
                "dailyQuota": state.daily_quota,
                "recordsLastRun": state.records_last_run,
                "portsLastRun": state.ports_last_run,
            }
        )
    observations = (
        Observation.query.order_by(Observation.source_time.desc(), Observation.id.desc())
        .limit(200)
        .all()
    )
    port_map = {port.code: port for port in Port.query.all()}
    preview = [
        {
            "provider": obs.provider_id,
            "portCode": obs.port_code,
            "port": port_map[obs.port_code].name,
            "country": port_map[obs.port_code].country,
            "grade": obs.grade,
            "price": round(obs.price, 2),
            "currency": obs.currency,
            "unit": obs.unit,
            "sourceTime": iso(obs.source_time),
            "retrievedAt": iso(obs.retrieved_at),
            "freshness": freshness(obs.source_time, obs.stale_upstream),
            "synthetic": obs.synthetic,
            "sourceLabel": obs.source_label,
        }
        for obs in observations
    ]
    last_run = RefreshRun.query.order_by(RefreshRun.started_at.desc()).first()
    upload = db.session.get(UploadState, 1)
    return {
        "providers": provider_rows,
        "preview": preview,
        "lastRun": {
            "status": last_run.status,
            "startedAt": iso(last_run.started_at),
            "finishedAt": iso(last_run.finished_at),
            "inserted": last_run.inserted_count,
            "error": last_run.error_summary,
        }
        if last_run
        else None,
        "upload": {
            "fileName": upload.file_name,
            "worksheet": upload.sheet_name,
            "uploadedAt": iso(upload.uploaded_at),
            "status": upload.status,
            "layout": upload.layout,
            "observations": upload.rows_received,
            "ports": upload.ports_received,
            "skippedCells": upload.skipped_cells,
            "formulaCacheMissing": upload.formula_cache_missing,
            "excelErrors": upload.excel_errors,
            "lastError": upload.last_error,
        } if upload else None,
    }
