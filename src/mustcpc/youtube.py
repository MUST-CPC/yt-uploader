"""YouTube OAuth for the community channel. Auth happens LOCALLY on your PC.

Run `mustcpc auth yt-login` once in a browser, then `mustcpc vps push-auth`
copies the token to the VPS. The VPS never runs an interactive flow.
"""

from __future__ import annotations

from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def obtain_token(client_secret: str | Path, token_file: str | Path) -> Path:
    """Run the installed-app OAuth flow and save credentials JSON."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    credentials = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )
    token_path = Path(token_file)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w") as f:
        f.write(credentials.to_json())
    return token_path


def load_credentials(token_file: str | Path):
    """Load saved credentials, refreshing the access token if needed."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_path = Path(token_file)
    if not token_path.exists():
        raise FileNotFoundError(
            f"YouTube token not found: {token_path}. "
            "Run `mustcpc auth yt-login` first."
        )
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    if not creds or not creds.valid:
        raise RuntimeError(
            "Saved YouTube credentials are invalid. "
            "Run `mustcpc auth yt-login` again."
        )
    return creds


def verify_channel(youtube, expected_channel_id: str) -> str:
    """Confirm the authenticated account owns the target channel.

    Returns the channel title. Raises on mismatch (unless no ID configured,
    in which case it just reports what it found).
    """
    response = youtube.channels().list(part="snippet", mine=True).execute()
    channels = response.get("items", [])
    if not channels:
        raise RuntimeError("No YouTube channel found for the authenticated account.")
    if not expected_channel_id:
        ch = channels[0]
        return ch["snippet"]["title"]
    for channel in channels:
        if channel["id"] == expected_channel_id:
            return channel["snippet"]["title"]
    raise RuntimeError(
        f"Wrong YouTube channel. Expected {expected_channel_id}, refusing to upload."
    )
