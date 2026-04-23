from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.publish.auth import (
    AuthError,
    load_credentials,
    save_credentials,
    token_path_for,
    verify_channel_ownership,
)


def test_token_path_for_profile(tmp_path: Path) -> None:
    assert token_path_for("my-profile", base=tmp_path) == tmp_path / "my-profile.json"


def test_save_and_load_credentials(tmp_path: Path) -> None:
    creds = MagicMock()
    creds.to_json.return_value = json.dumps({"token": "abc", "refresh_token": "def"})
    save_credentials(creds, tmp_path / "p.json")

    path = tmp_path / "p.json"
    assert path.exists()
    assert path.stat().st_mode & 0o777 == 0o600

    with patch("pipeline.publish.auth.Credentials.from_authorized_user_file") as loader:
        loader.return_value = MagicMock(valid=True, expired=False)
        loaded = load_credentials(path)
    assert loaded is not None


def test_load_credentials_missing_file(tmp_path: Path) -> None:
    with pytest.raises(AuthError, match="token file not found"):
        load_credentials(tmp_path / "missing.json")


def test_load_credentials_refreshes_when_expired(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text("{}", encoding="utf-8")

    creds = MagicMock(valid=False, expired=True, refresh_token="rt")
    with patch("pipeline.publish.auth.Credentials.from_authorized_user_file", return_value=creds):
        loaded = load_credentials(path)
    creds.refresh.assert_called_once()
    assert loaded is creds


def test_load_credentials_refresh_failure_raises(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text("{}", encoding="utf-8")

    creds = MagicMock(valid=False, expired=True, refresh_token="rt")
    creds.refresh.side_effect = RuntimeError("revoked")
    with patch("pipeline.publish.auth.Credentials.from_authorized_user_file", return_value=creds):
        with pytest.raises(AuthError, match="token refresh failed"):
            load_credentials(path)


def test_verify_channel_ownership_matches() -> None:
    api = MagicMock()
    api.channels.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "UC_expected"}]
    }
    # Must not raise
    verify_channel_ownership(api, expected_channel_id="UC_expected")


def test_verify_channel_ownership_mismatch() -> None:
    api = MagicMock()
    api.channels.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "UC_wrong"}]
    }
    with pytest.raises(AuthError, match="expected UC_expected.*got UC_wrong"):
        verify_channel_ownership(api, expected_channel_id="UC_expected")


def test_verify_channel_ownership_empty_placeholder_passes() -> None:
    api = MagicMock()
    api.channels.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "UC_discovered"}]
    }
    # When expected is empty, we accept any channel id and return it
    discovered = verify_channel_ownership(api, expected_channel_id="")
    assert discovered == "UC_discovered"
