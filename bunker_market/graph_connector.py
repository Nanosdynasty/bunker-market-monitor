"""Small Microsoft Graph connector for OneDrive and SharePoint workbooks."""
import base64
import json
import secrets
import threading
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import msal
import requests
from flask import current_app

from .excel_import import import_excel_result, parse_workbook
from .models import CloudWorkbookState, db, utcnow

_caches = {}
_refresh_lock = threading.Lock()


def session_key(session):
    key = session.get("cloud_session_id")
    if not key:
        key = secrets.token_urlsafe(32)
        session["cloud_session_id"] = key
    return key


def _authority():
    return f"https://login.microsoftonline.com/{current_app.config['MSAL_TENANT']}"


def _client(cache=None):
    return msal.ConfidentialClientApplication(
        current_app.config["MSAL_CLIENT_ID"],
        authority=_authority(),
        client_credential=current_app.config["MSAL_CLIENT_SECRET"],
        token_cache=cache,
    )


def auth_url(state):
    if not current_app.config["MSAL_CLIENT_ID"] or not current_app.config["MSAL_CLIENT_SECRET"]:
        raise RuntimeError("Microsoft Entra credentials are not configured")
    return _client().get_authorization_request_url(
        current_app.config["GRAPH_SCOPES"],
        state=state,
        redirect_uri=current_app.config["MSAL_REDIRECT_URI"],
        prompt="select_account",
    )


def redeem_code(code, key):
    cache = msal.SerializableTokenCache()
    result = _client(cache).acquire_token_by_authorization_code(
        code, scopes=current_app.config["GRAPH_SCOPES"], redirect_uri=current_app.config["MSAL_REDIRECT_URI"]
    )
    if "access_token" not in result:
        raise RuntimeError(result.get("error_description") or "Microsoft sign-in failed")
    _caches[key] = cache


def access_token(key):
    cache = _caches.get(key)
    if not cache:
        raise PermissionError("Microsoft sign-in has expired. Connect again.")
    accounts = _client(cache).get_accounts()
    result = _client(cache).acquire_token_silent(current_app.config["GRAPH_SCOPES"], account=accounts[0]) if accounts else None
    if result and result.get("access_token"):
        return result["access_token"]
    raise PermissionError("Microsoft sign-in has expired. Connect again.")


def _graph(method, path, key, **kwargs):
    response = requests.request(
        method, f"https://graph.microsoft.com/v1.0{path}",
        headers={"Authorization": f"Bearer {access_token(key)}", "Accept": "application/json"},
        timeout=current_app.config["PROVIDER_TIMEOUT_SECONDS"], **kwargs,
    )
    if response.status_code in (401, 403):
        raise PermissionError("Microsoft Graph denied access to this file")
    if response.status_code == 404:
        raise FileNotFoundError("The OneDrive or SharePoint file was not found")
    if response.status_code == 429:
        raise RuntimeError("Microsoft Graph is rate limiting requests. Try again shortly.")
    response.raise_for_status()
    return response


def list_files(key, parent_id=None):
    path = f"/me/drive/items/{parent_id}/children" if parent_id else "/me/drive/root/children"
    data = _graph("GET", path + "?$select=id,name,size,file,folder,parentReference,lastModifiedDateTime,eTag", key).json()
    return [item for item in data.get("value", []) if item.get("folder") or item.get("name", "").lower().endswith(".xlsx")]


def resolve_link(key, link):
    encoded = base64.urlsafe_b64encode(link.encode()).decode().rstrip("=")
    item = _graph("GET", f"/shares/u!{encoded}/driveItem?$select=id,name,size,file,parentReference,lastModifiedDateTime,eTag", key).json()
    return item


def _state(key):
    state = db.session.get(CloudWorkbookState, key)
    if not state:
        state = CloudWorkbookState(session_id=key)
        db.session.add(state)
    return state


def metadata(key):
    state = _state(key)
    if not state.drive_id or not state.item_id:
        return None
    return _graph("GET", f"/drives/{state.drive_id}/items/{state.item_id}?$select=id,name,parentReference,lastModifiedDateTime,eTag", key).json()


def _apply_item(state, item):
    state.drive_id = (item.get("parentReference") or {}).get("driveId") or state.drive_id
    state.item_id = item.get("id") or state.item_id
    state.file_name = item.get("name") or state.file_name
    parent = item.get("parentReference") or {}
    state.file_path = parent.get("path") or state.file_path
    state.etag = item.get("eTag")
    modified = item.get("lastModifiedDateTime")
    state.last_modified = datetime.fromisoformat(modified.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None) if modified else None


def select_item(key, item):
    state = _state(key)
    _apply_item(state, item)
    state.status = "selected"
    state.last_error = None
    db.session.commit()
    return refresh_workbook(key, force=True)


def select_link(key, link):
    return select_item(key, resolve_link(key, link))


def refresh_workbook(key, force=False):
    if not _refresh_lock.acquire(blocking=False):
        return {"status": "already_running"}
    try:
        return _refresh_workbook_locked(key, force)
    finally:
        _refresh_lock.release()


def _refresh_workbook_locked(key, force=False):
    state = _state(key)
    if not state.item_id:
        return {"status": "not_connected"}
    now = utcnow()
    try:
        item = metadata(key)
        new_etag = item.get("eTag")
        item_modified = item.get("lastModifiedDateTime")
        current_modified = state.last_modified.isoformat(timespec="seconds") + "Z" if state.last_modified else None
        changed = force or new_etag != state.etag or item_modified != current_modified
        state.last_checked = now
        if not changed:
            state.changed = False
            state.status = "current"
            db.session.commit()
            return state_payload(state)
        _apply_item(state, item)
        response = _graph("GET", f"/drives/{state.drive_id}/items/{state.item_id}/content", key, allow_redirects=True)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(response.content)
            temp_path = Path(tmp.name)
        try:
            result = parse_workbook(temp_path, state.file_name or "workbook.xlsx")
            import_excel_result(result)
        finally:
            temp_path.unlink(missing_ok=True)
        state.worksheet = result.sheet_name
        state.worksheets_json = json.dumps(result.sheet_names)
        state.last_success = now
        state.changed = True
        state.status = "current"
        state.last_error = None
        db.session.commit()
        return state_payload(state)
    except PermissionError as exc:
        state.status, state.last_error, state.last_checked = "permission_denied", str(exc), now
    except FileNotFoundError as exc:
        state.status, state.last_error, state.last_checked = "missing", str(exc), now
    except Exception as exc:
        current_app.logger.exception("Cloud workbook refresh failed")
        state.status, state.last_error, state.last_checked = "unavailable", str(exc), now
    db.session.commit()
    return state_payload(state)


def disconnect(key):
    _caches.pop(key, None)
    state = db.session.get(CloudWorkbookState, key)
    if state:
        db.session.delete(state)
        db.session.commit()


def state_payload(state):
    return {
        "connected": bool(state and state.item_id), "status": state.status if state else "waiting",
        "driveId": state.drive_id if state else None, "itemId": state.item_id if state else None,
        "fileName": state.file_name if state else None, "filePath": state.file_path if state else None,
        "worksheet": state.worksheet if state else None,
        "worksheets": json.loads(state.worksheets_json) if state and state.worksheets_json else [],
        "lastModified": state.last_modified.isoformat() + "Z" if state and state.last_modified else None,
        "lastChecked": state.last_checked.isoformat() + "Z" if state and state.last_checked else None,
        "lastSuccess": state.last_success.isoformat() + "Z" if state and state.last_success else None,
        "changed": bool(state.changed) if state else False, "error": state.last_error if state else None,
    }


def status(key):
    return state_payload(db.session.get(CloudWorkbookState, key))


def refresh_all_cloud():
    for key in list(_caches):
        refresh_workbook(key)
