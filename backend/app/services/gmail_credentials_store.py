import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


GMAIL_APP_DIR = Path.home() / ".mindos" / "connectors" / "gmail"
GMAIL_CREDENTIALS_PATH = GMAIL_APP_DIR / "credentials.json"
GMAIL_STATE_PATH = GMAIL_APP_DIR / "state.json"


class GmailCredentialsError(ValueError):
    pass


@dataclass(frozen=True)
class GmailOAuthCredentials:
    client_id: str
    client_secret: str
    auth_uri: str
    token_uri: str
    redirect_uris: list[str]


class GmailCredentialsStore:
    def save_uploaded_credentials(self, filename: str, content: str) -> dict[str, Any]:
        try:
            raw = json.loads(content)
        except json.JSONDecodeError as error:
            raise GmailCredentialsError("credentials.json is invalid.") from error
        parsed = self._parse_credentials(raw)
        GMAIL_APP_DIR.mkdir(parents=True, exist_ok=True)
        GMAIL_CREDENTIALS_PATH.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        state = self.load_state()
        state.update(
            {
                "credentials_configured": True,
                "credential_file_name": filename or "credentials.json",
                "last_error": None,
                "connected": False,
                "reconnect_required": False,
            }
        )
        self.save_state(state)
        return {"credential_file_name": filename or "credentials.json", "client_id": parsed.client_id}

    def load_credentials(self) -> GmailOAuthCredentials:
        if not GMAIL_CREDENTIALS_PATH.exists():
            raise GmailCredentialsError("Please upload Google OAuth credentials.json first.")
        try:
            raw = json.loads(GMAIL_CREDENTIALS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise GmailCredentialsError("credentials.json is invalid.") from error
        return self._parse_credentials(raw)

    def credentials_exist(self) -> bool:
        return GMAIL_CREDENTIALS_PATH.exists()

    def remove_credentials(self) -> None:
        for path in [GMAIL_CREDENTIALS_PATH, GMAIL_STATE_PATH]:
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def load_state(self) -> dict[str, Any]:
        if not GMAIL_STATE_PATH.exists():
            return {}
        try:
            value = json.loads(GMAIL_STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def save_state(self, state: dict[str, Any]) -> None:
        GMAIL_APP_DIR.mkdir(parents=True, exist_ok=True)
        GMAIL_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _parse_credentials(self, raw: dict[str, Any]) -> GmailOAuthCredentials:
        payload = raw.get("installed") or raw.get("web") or raw
        if not isinstance(payload, dict):
            raise GmailCredentialsError("credentials.json is invalid.")
        client_id = str(payload.get("client_id") or "").strip()
        client_secret = str(payload.get("client_secret") or "").strip()
        auth_uri = str(payload.get("auth_uri") or "https://accounts.google.com/o/oauth2/auth").strip()
        token_uri = str(payload.get("token_uri") or "https://oauth2.googleapis.com/token").strip()
        redirect_uris = payload.get("redirect_uris") or []
        if isinstance(redirect_uris, str):
            redirect_uris = [redirect_uris]
        redirect_uris = [str(item) for item in redirect_uris if str(item).strip()]
        if not client_id or not client_secret or not auth_uri or not token_uri:
            raise GmailCredentialsError("credentials.json is missing OAuth client fields.")
        return GmailOAuthCredentials(
            client_id=client_id,
            client_secret=client_secret,
            auth_uri=auth_uri,
            token_uri=token_uri,
            redirect_uris=redirect_uris,
        )


gmail_credentials_store = GmailCredentialsStore()
