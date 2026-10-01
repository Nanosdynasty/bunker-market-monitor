import base64
import json

from bunker_market import create_app


def _principal(extra_claims=None, group="group-1"):
    claims = [
        {"typ": "tid", "val": "tenant-1"},
        {"typ": "preferred_username", "val": "user@example.com"},
        {"typ": "groups", "val": group},
        {"typ": "oid", "val": "object-1"},
    ]
    claims.extend(extra_claims or [])
    payload = {"auth_typ": "aad", "claims": claims}
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _app(tmp_path):
    return create_app({
        "TESTING": True,
        "ENABLE_SCHEDULER": False,
        "DEMO_MODE": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "APP_SERVICE_AUTH_ENABLED": True,
        "EXPECTED_ENTRA_TENANT_ID": "tenant-1",
        "ALLOWED_EMAIL_DOMAIN": "example.com",
        "AUTHORIZED_GROUP_OBJECT_ID": "group-1",
        "TRUST_APP_SERVICE_IDENTITY_HEADERS": True,
    })


def test_easy_auth_requires_and_accepts_valid_claims(tmp_path):
    client = _app(tmp_path).test_client()
    assert client.get("/").status_code == 401
    assert client.get("/", headers={"X-MS-CLIENT-PRINCIPAL": _principal()}).status_code == 200
    assert client.get("/health").status_code == 200


def test_easy_auth_rejects_wrong_group(tmp_path):
    client = _app(tmp_path).test_client()
    response = client.get("/", headers={"X-MS-CLIENT-PRINCIPAL": _principal(group="other-group")})
    assert response.status_code == 403
    assert response.get_json()["error"] == "group_not_allowed"
