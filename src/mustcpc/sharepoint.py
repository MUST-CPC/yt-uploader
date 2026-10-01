"""SharePoint access: browser login (home IP) + direct-download-link extraction.

MUST blocks logins from most cloud-provider IPs, so this module always runs
on your PC. The extracted DDL is then handed to the VPS module, which
downloads it where bandwidth is free.
"""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests


def parse_video_url(video_url: str) -> tuple[str, str]:
    """Parse a SharePoint video URL into (site, unique_id).

    Supports:
    - `.../_layouts/15/download.aspx?UniqueId=...`
    - `.../:v:/s/<SITE>/<SHARING_TOKEN>` (GUID is embedded in the token)
    """
    parsed = urlparse(video_url)
    host = parsed.netloc
    path = parsed.path

    if not host.endswith(".sharepoint.com"):
        raise ValueError("Not a SharePoint URL")

    query = parse_qs(parsed.query)
    unique_ids = query.get("UniqueId") or query.get("uniqueid") or query.get("uniqueId")
    if unique_ids:
        unique_id = unique_ids[0]
        marker = "/_layouts/"
        if marker not in path:
            raise ValueError("Could not determine SharePoint site from download URL")
        site_path = path.split(marker, 1)[0]
        return f"{parsed.scheme}://{host}{site_path}", unique_id

    parts = [p for p in path.split("/") if p]
    # Expected: [":v:", "s", "<SITE>", "<TOKEN>"]
    if len(parts) >= 4 and parts[0].startswith(":") and parts[1] == "s":
        site_name = parts[2]
        share_token = parts[3]
        padding = "=" * ((4 - len(share_token) % 4) % 4)
        raw = base64.urlsafe_b64decode(share_token + padding)
        if len(raw) < 18:
            raise ValueError("SharePoint sharing token is too short")
        # First 2 bytes are token metadata, next 16 are the file GUID (LE).
        guid_bytes = raw[2:18]
        unique_id = str(uuid.UUID(bytes_le=guid_bytes))
        return f"{parsed.scheme}://{host}/sites/{site_name}", unique_id

    raise ValueError(
        "Unsupported SharePoint URL. Use either the normal video sharing link "
        "or the download.aspx?UniqueId=... link."
    )


def load_session(state_file: str | Path) -> requests.Session:
    """Rebuild an authenticated requests session from Playwright storage state."""
    state_path = Path(state_file)
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)

    session = requests.Session()
    for cookie in state.get("cookies", []):
        if "sharepoint.com" in cookie.get("domain", ""):
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie["domain"],
                path=cookie.get("path", "/"),
            )
    session.headers.update({
        "Accept": "application/json;odata=nometadata",
        "User-Agent": "Mozilla/5.0",
    })
    return session


def get_file_info(
    session: requests.Session, site: str, unique_id: str
) -> tuple[str, str, str]:
    """Return (file_name, server_relative_url, library_path) for a file ID."""
    url = (
        f"{site}/_api/web/GetFileById('{unique_id}')"
        "?$select=Name,ServerRelativeUrl,"
        "ListItemAllFields/ParentList/RootFolder/ServerRelativeUrl"
        "&$expand=ListItemAllFields/ParentList/RootFolder"
    )
    r = session.get(url)
    r.raise_for_status()
    data = r.json()
    name = data["Name"]
    file_path = data["ServerRelativeUrl"]
    library_path = data["ListItemAllFields"]["ParentList"]["RootFolder"][
        "ServerRelativeUrl"
    ]
    return name, file_path, library_path


def find_drive(session: requests.Session, site: str, library_path: str) -> str:
    """Match a document library path to a Graph drive ID."""
    r = session.get(f"{site}/_api/v2.0/drives")
    r.raise_for_status()
    drives = r.json()["value"]

    wanted = unquote(library_path).rstrip("/").lower()
    for drive in drives:
        web_url = drive.get("webUrl")
        if not web_url:
            continue
        path = unquote(urlparse(web_url).path).rstrip("/").lower()
        if path == wanted:
            return drive["id"]

    available = "\n".join(
        f" - {d.get('name')} {d.get('webUrl')}" for d in drives
    )
    raise RuntimeError(f"Drive not found for library {library_path!r}.\n{available}")


def get_download_url(
    session: requests.Session,
    site: str,
    drive_id: str,
    file_path: str,
    library_path: str,
) -> str:
    """Ask the v2.0 API for a temporary `@content.downloadUrl`."""
    relative_path = file_path[len(library_path):].lstrip("/")
    encoded_path = quote(relative_path, safe="/()!$,-._~'")
    url = (
        f"{site}/_api/v2.0/drives/{quote(drive_id, safe='')}/root:/{encoded_path}"
    )
    r = session.get(url, headers={"Accept": "application/json"})
    r.raise_for_status()
    data = r.json()
    download_url = data.get("@content.downloadUrl") or data.get(
        "@microsoft.graph.downloadUrl"
    )
    if not download_url:
        raise RuntimeError(
            "No temporary download URL returned. Fields: "
            + ", ".join(sorted(data.keys()))
        )
    return download_url


def extract_ddl(video_url: str, state_file: str | Path) -> tuple[str, str]:
    """Full flow: parse URL -> session -> file info -> drive -> DDL.

    Returns (file_name, direct_download_url).
    """
    site, unique_id = parse_video_url(video_url)
    session = load_session(state_file)
    name, file_path, library_path = get_file_info(session, site, unique_id)
    drive_id = find_drive(session, site, library_path)
    return name, get_download_url(session, site, drive_id, file_path, library_path)


def must_login(profile_dir: str | Path, state_file: str | Path, start_url: str) -> Path:
    """Open a persistent Chromium profile so you can log in to MUST manually.

    Saves Playwright storage state to `state_file`. Import playwright lazily
    so the rest of the CLI works without browser deps installed.
    """
    from playwright.sync_api import sync_playwright

    profile_dir = str(profile_dir)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(profile_dir, headless=False)
        page = context.new_page()
        page.goto(start_url)
        input("Log in completely, then press Enter here... ")
        context.storage_state(path=str(state_file))
        context.close()
    return Path(state_file)
