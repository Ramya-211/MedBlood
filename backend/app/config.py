"""
config.py

Central, environment-driven configuration. Nothing sensitive is hard-coded.
The application refuses to start with a missing or placeholder JWT secret.
"""

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

_PLACEHOLDER_SECRETS = {"", "change_me_to_a_long_random_string"}


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    jwt_secret: str
    jwt_algorithm: str
    jwt_expire_minutes: int
    cors_origins: list
    near_expiry_days: int = 30
    as_of_date_override: str = ""
    forecast_horizon_days: int = 30
    forecast_shortage_horizon_days: int = 7
    llm_provider: str = "none"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    chat_context_turns: int = 6
    chat_context_ttl_minutes: int = 60


def _load() -> Settings:
    secret = os.environ.get("JWT_SECRET", "")
    if secret in _PLACEHOLDER_SECRETS or len(secret) < 32:
        raise RuntimeError(
            "JWT_SECRET is missing, a placeholder, or shorter than 32 characters. "
            "Set a long random value in backend/.env (see .env.example)."
        )
    return Settings(
        db_host=os.environ.get("DB_HOST", "localhost"),
        db_port=int(os.environ.get("DB_PORT", "3306")),
        db_name=os.environ.get("DB_NAME", "medblood_db"),
        db_user=os.environ.get("DB_USER", "medblood_app"),
        db_password=os.environ.get("DB_PASSWORD", ""),
        jwt_secret=secret,
        jwt_algorithm=os.environ.get("JWT_ALGORITHM", "HS256"),
        jwt_expire_minutes=int(os.environ.get("JWT_EXPIRE_MINUTES", "60")),
        cors_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
        near_expiry_days=int(os.environ.get("NEAR_EXPIRY_DAYS", "30")),
        as_of_date_override=os.environ.get("AS_OF_DATE", "").strip(),
        forecast_horizon_days=int(os.environ.get("FORECAST_HORIZON_DAYS", "30")),
        forecast_shortage_horizon_days=int(os.environ.get("FORECAST_SHORTAGE_HORIZON_DAYS", "7")),
        llm_provider=os.environ.get("LLM_PROVIDER", "none").strip().lower(),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        llm_model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        llm_base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
        chat_context_turns=int(os.environ.get("CHAT_CONTEXT_TURNS", "6")),
        chat_context_ttl_minutes=int(os.environ.get("CHAT_CONTEXT_TTL_MINUTES", "60")),
    )


_settings = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = _load()
    return _settings
