import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DEFAULT_DB = PROJECT_ROOT / "instance" / "bunker-market-monitor.db"

    SECRET_KEY = os.getenv("SECRET_KEY", "local-development-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{os.getenv('DATABASE_PATH', str(DEFAULT_DB))}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    DEMO_MODE = _bool("DEMO_MODE", True)
    ENABLE_SCHEDULER = _bool("ENABLE_SCHEDULER", True)
    REFRESH_INTERVAL_MINUTES = int(os.getenv("REFRESH_INTERVAL_MINUTES", "30"))
    MANUAL_REFRESH_COOLDOWN_SECONDS = int(
        os.getenv("MANUAL_REFRESH_COOLDOWN_SECONDS", "600")
    )
    STALE_AFTER_MINUTES = int(os.getenv("STALE_AFTER_MINUTES", "180"))
    PROVIDER_TIMEOUT_SECONDS = int(os.getenv("PROVIDER_TIMEOUT_SECONDS", "15"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)

    MSAL_CLIENT_ID = os.getenv("MSAL_CLIENT_ID", "")
    MSAL_CLIENT_SECRET = os.getenv("MSAL_CLIENT_SECRET", "")
    MSAL_TENANT = os.getenv("MSAL_TENANT", "common")
    MSAL_REDIRECT_URI = os.getenv("MSAL_REDIRECT_URI", "http://localhost:5070/auth/callback")
    GRAPH_SCOPES = ["User.Read", "Files.Read", "offline_access"]
    GRAPH_REFRESH_INTERVAL_MINUTES = int(os.getenv("GRAPH_REFRESH_INTERVAL_MINUTES", "5"))
