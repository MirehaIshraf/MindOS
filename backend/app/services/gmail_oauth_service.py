import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.schemas.gmail import REQUIRED_GMAIL_SCOPES
from app.services.gmail_credentials_store import GmailCredentialsError, gmail_credentials_store
from app.services.gmail_token_store import gmail_token_store, utc_now_iso


GMAIL_REDIRECT_URI = "http://localhost:8000/connectors/gmail/oauth/callback"


class GmailOAuthError(ValueError):
    pass


class GmailOAuthService:
    def start_oauth(self) -> str:
        credentials = gmail_credentials_store.load_credentials()
        state_value = secrets.token_urlsafe(32)
        state = gmail_credentials_store.load_state()
        state.update(
            {
                "oauth_state": state_value,
                "connected": False,
                "reconnect_required": False,
                "last_error": None,
            }
        )
        gmail_credentials_store.save_state(state)
        params = {
            "client_id": credentials.client_id,
            "redirect_uri": GMAIL_REDIRECT_URI,
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "scope": " ".join(REQUIRED_GMAIL_SCOPES),
            "state": state_value,
        }
        return f"{credentials.auth_uri}?{urlencode(params)}"

    def handle_callback(self, code: str | None, state: str | None, error: str | None = None) -> dict[str, Any]:
        if error:
            self._mark_error("OAuth login was cancelled.")
            raise GmailOAuthError("OAuth login was cancelled.")
        if not code:
            self._mark_error("Authorization code missing.")
            raise GmailOAuthError("Authorization code missing.")
        saved_state = gmail_credentials_store.load_state()
        expected_state = saved_state.get("oauth_state")
        if not state or state != expected_state:
            self._mark_error("OAuth state mismatch.")
            raise GmailOAuthError("OAuth state mismatch.")
        token = self.exchange_code(code)
        saved_state.pop("oauth_state", None)
        saved_state.update(
            {
                "connected": True,
                "reconnect_required": False,
                "scopes": token.get("scopes", []),
                "connected_at": utc_now_iso(),
                "last_error": None,
            }
        )
        gmail_credentials_store.save_state(saved_state)
        return token

    def exchange_code(self, code: str) -> dict[str, Any]:
        credentials = gmail_credentials_store.load_credentials()
        try:
            response = httpx.post(
                credentials.token_uri,
                data={
                    "code": code,
                    "client_id": credentials.client_id,
                    "client_secret": credentials.client_secret,
                    "redirect_uri": GMAIL_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                timeout=30,
            )
        except httpx.RequestError as error:
            self._mark_error("Network error while connecting Gmail.")
            raise GmailOAuthError("Network error while connecting Gmail.") from error
        if response.status_code >= 400:
            self._mark_error("Token exchange failed.")
            raise GmailOAuthError("Token exchange failed. Check that the Gmail API is enabled and credentials are valid.")
        data = response.json()
        token = self._normalize_token(data)
        self._validate_required_scopes(token.get("scopes", []))
        gmail_token_store.save_token(token)
        return token

    def refresh_token(self, token: dict[str, Any]) -> dict[str, Any]:
        credentials = gmail_credentials_store.load_credentials()
        refresh_token = str(token.get("refresh_token") or "")
        if not refresh_token:
            self._mark_reconnect_required("Gmail connection expired. Please reconnect.")
            raise GmailOAuthError("Gmail connection expired. Please reconnect.")
        try:
            response = httpx.post(
                credentials.token_uri,
                data={
                    "client_id": credentials.client_id,
                    "client_secret": credentials.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=30,
            )
        except httpx.RequestError as error:
            self._mark_reconnect_required("Token refresh failed.")
            raise GmailOAuthError("Token refresh failed.") from error
        if response.status_code >= 400:
            self._mark_reconnect_required("Token expired or revoked; please reconnect.")
            raise GmailOAuthError("Token expired or revoked; please reconnect.")
        data = response.json()
        next_token = {
            **token,
            **self._normalize_token(data, existing_refresh_token=refresh_token),
        }
        gmail_token_store.save_token(next_token)
        self._clear_error()
        return next_token

    def ensure_access_token(self) -> str:
        token = gmail_token_store.load_token()
        if not token:
            raise GmailOAuthError("Gmail is not connected. Please connect Gmail from Connectors.")
        expires_at = _parse_datetime(token.get("expires_at"))
        if not expires_at or expires_at <= datetime.now(timezone.utc) + timedelta(seconds=60):
            token = self.refresh_token(token)
        access_token = str(token.get("access_token") or "")
        if not access_token:
            self._mark_reconnect_required("Gmail connection expired. Please reconnect.")
            raise GmailOAuthError("Gmail connection expired. Please reconnect.")
        return access_token

    def disconnect(self) -> None:
        gmail_token_store.remove_token()
        state = gmail_credentials_store.load_state()
        state.update({"connected": False, "reconnect_required": False, "email_address": None, "last_error": None})
        gmail_credentials_store.save_state(state)

    def remove_credentials(self) -> None:
        gmail_token_store.remove_token()
        gmail_credentials_store.remove_credentials()

    def _normalize_token(self, data: dict[str, Any], existing_refresh_token: str | None = None) -> dict[str, Any]:
        expires_in = int(data.get("expires_in") or 3600)
        scopes = str(data.get("scope") or "").split()
        return {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token") or existing_refresh_token,
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
            "scopes": scopes,
            "token_type": data.get("token_type", "Bearer"),
        }

    def _validate_required_scopes(self, scopes: list[str]) -> None:
        missing = [scope for scope in REQUIRED_GMAIL_SCOPES if scope not in scopes]
        if missing:
            self._mark_error("Required scopes were not granted.")
            raise GmailOAuthError("Required scopes were not granted.")

    def _mark_error(self, message: str) -> None:
        state = gmail_credentials_store.load_state()
        state.update({"connected": False, "last_error": message})
        gmail_credentials_store.save_state(state)

    def _mark_reconnect_required(self, message: str) -> None:
        state = gmail_credentials_store.load_state()
        state.update({"connected": False, "reconnect_required": True, "last_error": message})
        gmail_credentials_store.save_state(state)

    def _clear_error(self) -> None:
        state = gmail_credentials_store.load_state()
        state.update({"last_error": None, "reconnect_required": False})
        gmail_credentials_store.save_state(state)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


gmail_oauth_service = GmailOAuthService()
