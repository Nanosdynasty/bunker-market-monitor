"""Optional authorization for Azure App Service Authentication (Easy Auth).

Azure App Service validates the Entra token and forwards the resulting claims
in ``X-MS-CLIENT-PRINCIPAL``. This module performs application-level checks on
those claims. It is deliberately opt-in; the normal local/cloud connector
login remains the MSAL authorization-code flow in :mod:`graph_connector`.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass
from typing import Any, Iterable

from flask import Flask, Response, g, jsonify, request

_MAX_PRINCIPAL_HEADER_BYTES = 32 * 1024
_TENANT_CLAIMS = {"tid", "http://schemas.microsoft.com/identity/claims/tenantid"}
_EMAIL_CLAIMS = {
    "email", "emails", "preferred_username", "upn",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn",
}
_GROUP_CLAIMS = {"groups", "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups"}
_OBJECT_ID_CLAIMS = {"oid", "http://schemas.microsoft.com/identity/claims/objectidentifier"}


@dataclass(frozen=True, slots=True)
class EntraIdentity:
    tenant_id: str
    object_id: str
    email: str


@dataclass(frozen=True, slots=True)
class AuthConfig:
    tenant_id: str
    email_domain: str
    group_object_id: str
    trust_identity_headers: bool

    @property
    def complete(self) -> bool:
        return bool(self.tenant_id and self.email_domain and self.group_object_id and self.trust_identity_headers)


def init_app_service_auth(app: Flask) -> AuthConfig:
    """Register optional Easy Auth authorization and return its configuration."""
    config = _load_config(app)
    app.extensions["app_service_auth_config"] = config

    if not any(rule.rule == "/healthz" for rule in app.url_map.iter_rules()):
        app.add_url_rule("/healthz", "app_service_auth_healthz", _healthz, methods=["GET", "HEAD"])

    @app.before_request
    def authorize_request() -> Response | tuple[Response, int] | None:
        # Azure health probes must remain unauthenticated. Easy Auth itself
        # handles the interactive sign-in before application requests arrive.
        if request.path in {"/health", "/ready", "/healthz"}:
            return None
        if not config.complete:
            return _error(503, "authentication_not_configured", "Azure authentication is not fully configured.")

        principal = _parse_principal(request.headers.get("X-MS-CLIENT-PRINCIPAL"))
        if principal is None:
            return _error(401, "authentication_required", "Microsoft Entra authentication is required.")
        if str(principal.get("auth_typ", "")).casefold() != "aad":
            return _denied("identity_provider_not_allowed")

        tenant_ids = _claim_values(principal, _TENANT_CLAIMS)
        if config.tenant_id not in {value.casefold() for value in tenant_ids}:
            return _denied("tenant_not_allowed")
        email = _authorized_email(_claim_values(principal, _EMAIL_CLAIMS), config.email_domain)
        if email is None:
            return _denied("email_domain_not_allowed")
        groups = {value.casefold() for value in _claim_values(principal, _GROUP_CLAIMS)}
        if config.group_object_id not in groups:
            return _denied("group_not_allowed")
        object_ids = _claim_values(principal, _OBJECT_ID_CLAIMS)
        if not object_ids:
            return _denied("object_id_missing")

        g.entra_identity = EntraIdentity(config.tenant_id, object_ids[0], email)
        return None

    return config


def _load_config(app: Flask) -> AuthConfig:
    def value(name: str, default: str = "") -> str:
        raw = app.config.get(name, os.getenv(name, default))
        return str(raw).strip()

    return AuthConfig(
        tenant_id=value("EXPECTED_ENTRA_TENANT_ID").casefold(),
        email_domain=value("ALLOWED_EMAIL_DOMAIN").lstrip("@").casefold(),
        group_object_id=value("AUTHORIZED_GROUP_OBJECT_ID").casefold(),
        trust_identity_headers=value("TRUST_APP_SERVICE_IDENTITY_HEADERS").casefold() in {"1", "true", "yes"},
    )


def _parse_principal(header_value: str | None) -> dict[str, Any] | None:
    if not header_value or len(header_value) > _MAX_PRINCIPAL_HEADER_BYTES:
        return None
    try:
        padded = header_value + ("=" * (-len(header_value) % 4))
        principal = json.loads(base64.b64decode(padded, validate=True).decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    return principal if isinstance(principal, dict) and isinstance(principal.get("claims"), list) else None


def _claim_values(principal: dict[str, Any], accepted_types: Iterable[str]) -> list[str]:
    accepted = {item.casefold() for item in accepted_types}
    values = []
    for claim in principal.get("claims", []):
        if isinstance(claim, dict) and str(claim.get("typ", "")).casefold() in accepted:
            value = str(claim.get("val", "")).strip()
            if value:
                values.append(value)
    return values


def _authorized_email(values: Iterable[str], domain: str) -> str | None:
    suffix = f"@{domain}"
    for value in values:
        normalized = value.strip().casefold()
        if normalized.count("@") == 1 and normalized.endswith(suffix) and normalized[:-len(suffix)]:
            return normalized
    return None


def _healthz() -> Response:
    return jsonify({"status": "ok"})


def _denied(code: str) -> tuple[Response, int]:
    return _error(403, code, "Access denied.")


def _error(status: int, code: str, message: str) -> tuple[Response, int]:
    response = jsonify({"error": code, "message": message})
    response.headers["Cache-Control"] = "no-store"
    return response, status
