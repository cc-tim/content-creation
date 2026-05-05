from __future__ import annotations

import contextlib
import stat
from pathlib import Path
from typing import Any

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = structlog.get_logger()

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "content-creation" / "youtube"


class AuthError(RuntimeError):
    """Raised for any OAuth / token / channel-verification failure."""


def token_path_for(profile: str, *, base: Path = DEFAULT_CONFIG_DIR) -> Path:
    """Return the token JSON path for a profile."""
    return base / f"{profile}.json"


def client_secret_path(*, base: Path = DEFAULT_CONFIG_DIR) -> Path:
    return base / "client_secret.json"


def save_credentials(creds: Credentials, path: Path) -> None:
    """Write credentials to a file with mode 0600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600


def load_credentials(path: Path) -> Credentials:
    """Load credentials, refreshing if expired. Raises AuthError on failure."""
    if not path.exists():
        raise AuthError(
            f"token file not found at {path}. Run: pipeline publish auth --profile <name>"
        )
    creds = Credentials.from_authorized_user_file(str(path), scopes=SCOPES)
    if not creds.valid:
        if not creds.expired or not creds.refresh_token:
            raise AuthError(
                f"token at {path} is invalid and cannot be refreshed. "
                f"Run: pipeline publish auth --profile <name> --reauth"
            )
        try:
            creds.refresh(Request())
        except Exception as exc:
            raise AuthError(
                f"token refresh failed: {exc}. Run: pipeline publish auth --profile <name> --reauth"
            ) from exc
        # Best-effort persist of refreshed token; skip on failure (e.g. in tests)
        with contextlib.suppress(TypeError):
            save_credentials(creds, path)
    return creds


def run_oauth_flow(
    client_secret_file: Path,
    *,
    extra_scopes: list[str] | None = None,
) -> Credentials:
    """Run the browser OAuth consent flow. Returns new Credentials."""
    if not client_secret_file.exists():
        raise AuthError(
            f"client_secret.json not found at {client_secret_file}. See spec for GCP setup steps."
        )
    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secret_file),
        scopes=SCOPES + (extra_scopes or []),
    )
    return flow.run_local_server(port=0)


def verify_channel_ownership(youtube_api: Any, *, expected_channel_id: str) -> str:
    """Call channels.list(mine=true) and verify the discovered id matches expected.

    If expected is empty (placeholder in config), returns the discovered id so
    the caller can write it back to config.
    """
    response = youtube_api.channels().list(part="id", mine=True).execute()
    items = response.get("items", [])
    if not items:
        raise AuthError(
            "authenticated account has no YouTube channel. "
            "Sign in to Google with an account that owns a channel."
        )
    discovered = items[0]["id"]

    if not expected_channel_id:
        logger.info("auth.channel_id.discovered", channel_id=discovered)
        return discovered

    if discovered != expected_channel_id:
        raise AuthError(
            f"channel id mismatch: expected {expected_channel_id}, got {discovered}. "
            f"The Google account you consented with does not own the configured channel."
        )
    return discovered
