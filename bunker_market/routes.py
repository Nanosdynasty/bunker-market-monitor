import secrets
import tempfile
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request, session
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from .excel_import import import_excel_result, mark_upload_error, parse_workbook
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


@bp.post("/api/uploads/excel")
def upload_excel_api():
    supplied = request.headers.get("X-CSRF-Token", "")
    expected = session.get("csrf_token", "")
    if not supplied or not expected or not secrets.compare_digest(supplied, expected):
        return jsonify({"status": "error", "error": "Invalid upload token"}), 403
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"status": "error", "error": "Choose an .xlsx workbook first"}), 400
    file_name = secure_filename(uploaded.filename)
    if Path(file_name).suffix.lower() != ".xlsx":
        return jsonify({"status": "error", "error": "Only .xlsx workbooks are supported"}), 415

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as temporary:
            temp_path = Path(temporary.name)
            uploaded.save(temporary)
        result = parse_workbook(temp_path, file_name)
        import_excel_result(result)
        return jsonify({
            "status": "current",
            "fileName": result.file_name,
            "worksheet": result.sheet_name,
            "worksheets": result.sheet_names,
            "layout": result.layout,
            "observations": len(result.observations),
            "ports": len({item.port_name.casefold() for item in result.observations}),
            "skippedCells": result.skipped_cells,
            "formulaCacheMissing": result.formula_cache_missing,
            "excelErrors": result.excel_errors,
        })
    except ValueError as exc:
        mark_upload_error(str(exc))
        return jsonify({"status": "error", "error": str(exc)}), 422
    except Exception:
        current_app.logger.exception("Excel import failed")
        message = "The workbook could not be read. Confirm it is a valid, unencrypted .xlsx file."
        mark_upload_error(message)
        return jsonify({"status": "error", "error": message}), 422
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


@bp.app_errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    size_mb = current_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return jsonify({"status": "error", "error": f"Workbook exceeds the {size_mb} MB upload limit"}), 413


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
