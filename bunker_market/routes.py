import secrets

from flask import Blueprint, current_app, jsonify, render_template, request, session

from .models import Observation, ProviderState, db
from .queries import compare_payload, dashboard_payload, sources_payload
from .refresh import perform_refresh


bp = Blueprint("main", __name__)


def _csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(24)
    return session["csrf_token"]


@bp.get("/")
def index():
    return render_template("index.html", csrf_token=_csrf_token())


@bp.get("/api/dashboard")
def dashboard_api():
    return jsonify(
        dashboard_payload(
            request.args.get("port"),
            request.args.get("grade", "VLSFO"),
            request.args.get("range", "7D"),
        )
    )


@bp.get("/api/compare")
def compare_api():
    ports = {v for v in request.args.get("ports", "").split(",") if v}
    grades = {v.upper() for v in request.args.get("grades", "").split(",") if v}
    return jsonify(compare_payload(ports or None, grades or None))


@bp.get("/api/sources")
def sources_api():
    return jsonify(sources_payload())


@bp.post("/api/refresh")
def refresh_api():
    supplied = request.headers.get("X-CSRF-Token", "")
    expected = session.get("csrf_token", "")
    if not supplied or not expected or not secrets.compare_digest(supplied, expected):
        return jsonify({"status": "error", "error": "Invalid refresh token"}), 403
    result = perform_refresh(trigger="manual", force=False)
    code = 409 if result["status"] == "already_running" else 200
    return jsonify(result), code


@bp.get("/health")
def health():
    return jsonify({"status": "ok", "service": "bunker-market-monitor"})


@bp.get("/ready")
def ready():
    try:
        db.session.execute(db.select(ProviderState).limit(1)).first()
        return jsonify({"status": "ready", "observations": Observation.query.count()})
    except Exception:
        current_app.logger.exception("Readiness check failed")
        return jsonify({"status": "not_ready"}), 503
