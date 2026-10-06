"""SharePoint access: browser login (home IP) + direct-download-link extraction.

MUST blocks logins from most cloud-provider IPs, so this module always runs
on your PC. The extracted DDL is then handed to the VPS module, which
downloads it where bandwidth is free.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests


def parse_video_url(video_url: str) -> tuple[str, str]:
    """Return (site, file_reference), where the reference is a GUID or decoded path.

    Supports:
    - `.../_layouts/15/download.aspx?UniqueId=...`
    - `.../_layouts/15/download.aspx?SourceUrl=<file-url>`
    - Direct file URLs, `:v:/r/...`, and viewer URLs with an `id` file path
    - `.../:v:/s/<SITE>/<TOKEN>`, `:v:/t/...`, `:v:/g/personal/<OWNER>/<TOKEN>`
    """
    parsed = urlparse(video_url)
    host = parsed.hostname or ""
    path = parsed.path

    if (
        parsed.scheme != "https" or not host.endswith(".sharepoint.com")
        or parsed.username or parsed.password or parsed.port not in (None, 443)
    ):
        raise ValueError("Not a SharePoint URL")

    origin = f"https://{host}"
    query = {key.lower(): value for key, value in parse_qs(parsed.query).items()}
    unique_ids = query.get("uniqueid") or query.get("sourcedoc")
    if unique_ids:
        unique_id = unique_ids[0]
        marker = "/_layouts/"
        if marker not in path:
            raise ValueError("Could not determine SharePoint site from download URL")
        site_path = path.split(marker, 1)[0]
        return f"{origin}{site_path}", str(uuid.UUID(unique_id.strip("{}")))

    source_urls = query.get("sourceurl")
    file_ids = query.get("id")
    if source_urls or file_ids:
        reference = (source_urls or file_ids)[0]
        source = urlparse(reference)
        if source.netloc:
            if (
                source.scheme != "https" or source.hostname != host
                or source.username or source.password
                or source.port not in (None, 443)
            ):
                raise ValueError("File URL must belong to the same SharePoint host")
            file_path = unquote(source.path)
        else:
            # An id query value is already a decoded server-relative path.
            file_path = reference
        if not file_path.startswith("/") or file_path.startswith("//"):
            raise ValueError("Expected a server-relative SharePoint file path")
        if "/_layouts/" in path:
            site_path = path.split("/_layouts/", 1)[0]
            if site_path:
                if not file_path.startswith(unquote(site_path).rstrip("/") + "/"):
                    raise ValueError("File path must belong to the SharePoint site")
                return f"{origin}{site_path}", file_path
        return _site_for_file(origin, file_path), file_path

    if path.startswith("/:v:/r/"):
        file_path = unquote(path[len("/:v:/r"):])
        return _site_for_file(origin, file_path), file_path

    if path.lower().endswith((".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")):
        file_path = unquote(path)
        return _site_for_file(origin, file_path), file_path

    parts = [p for p in path.split("/") if p]
    site_path = None
    if len(parts) == 4 and parts[0] == ":v:" and parts[1] in {"s", "t"}:
        prefix = "sites" if parts[1] == "s" else "teams"
        site_path = f"/{prefix}/{parts[2]}"
        share_token = parts[3]
    elif len(parts) == 5 and parts[:3] == [":v:", "g", "personal"]:
        site_path = f"/personal/{parts[3]}"
        share_token = parts[4]
    if site_path is not None:
        padding = "=" * ((4 - len(share_token) % 4) % 4)
        try:
            raw = base64.b64decode(share_token + padding, altchars=b"-_", validate=True)
        except binascii.Error as exc:
            raise ValueError("Invalid SharePoint sharing token") from exc
        if len(raw) < 18:
            raise ValueError("SharePoint sharing token is too short")
        # First 2 bytes are token metadata, next 16 are the file GUID (LE).
        guid_bytes = raw[2:18]
        unique_id = str(uuid.UUID(bytes_le=guid_bytes))
        return f"{origin}{site_path}", unique_id

    raise ValueError(
        "Unsupported SharePoint URL. Use either the normal video sharing link "
        "or a download.aspx link with UniqueId or SourceUrl, a viewer link with "
        "an id file path, or a direct MP4 URL."
    )


def _site_for_file(origin: str, file_path: str) -> str:
    """Infer the site collection for a decoded server-relative file path."""
    parts = file_path.lstrip("/").split("/")
    if parts[0].lower() in {"sites", "teams", "personal"}:
        if len(parts) < 4 or not parts[1]:
            raise ValueError("Expected a SharePoint file path inside a library")
        return origin + "/" + quote("/".join(parts[:2]), safe="/")
    if len(parts) < 2:
        raise ValueError("Expected a SharePoint file path inside a library")
    return origin


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
    session: requests.Session, site: str, file_reference: str
) -> tuple[str, str, str]:
    """Return (file_name, server_relative_url, library_path) for a GUID or path."""
    if file_reference.startswith("/"):
        escaped_path = quote(file_reference.replace("'", "''"), safe="/")
        lookup = f"GetFileByServerRelativePath(decodedUrl='{escaped_path}')"
    else:
        lookup = f"GetFileById('{uuid.UUID(file_reference)}')"
    url = (
        f"{site}/_api/web/{lookup}"
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
    site, file_reference = parse_video_url(video_url)
    session = load_session(state_file)
    name, file_path, library_path = get_file_info(session, site, file_reference)
    drive_id = find_drive(session, site, library_path)
    return name, get_download_url(session, site, drive_id, file_path, library_path)


def must_login(profile_dir: str | Path, state_file: str | Path, start_url: str) -> Path:
    """Open a persistent Chromium profile to log in to the target SharePoint tenant.

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
