import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.gmail_credentials_store import GMAIL_APP_DIR


GMAIL_TOKEN_PATH = GMAIL_APP_DIR / "token.json"


class GmailTokenStore:
    def load_token(self) -> dict[str, Any] | None:
        if not GMAIL_TOKEN_PATH.exists():
            return None
        try:
            value = json.loads(GMAIL_TOKEN_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def save_token(self, token: dict[str, Any]) -> None:
        # TODO: replace JSON storage with OS keychain storage for packaged desktop builds.
        GMAIL_APP_DIR.mkdir(parents=True, exist_ok=True)
        GMAIL_TOKEN_PATH.write_text(json.dumps(token, indent=2), encoding="utf-8")

    def remove_token(self) -> None:
        try:
            GMAIL_TOKEN_PATH.unlink()
        except FileNotFoundError:
            pass

    def token_exists(self) -> bool:
        return Path(GMAIL_TOKEN_PATH).exists()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


gmail_token_store = GmailTokenStore()
