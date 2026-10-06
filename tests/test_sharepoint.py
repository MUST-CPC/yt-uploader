"""Unit tests for SharePoint URL parsing (no network needed)."""

import base64
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, Mock
from urllib.parse import quote, unquote

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mustcpc.sharepoint import extract_ddl, get_file_info, parse_video_url


EXAMPLE_URL = (
    "https://mustedueg-my.sharepoint.com/personal/200053683_must_edu_eg/"
    "_layouts/15/download.aspx?SourceUrl=https%3A%2F%2Fmustedueg-my.sharepoint.com"
    "%2Fpersonal%2F200053683_must_edu_eg%2FDocuments%2FRecordings%2FMeeting%20with%20"
    "200053683-Mustafa%20Mahmoud%20Amin%20Ahmed%20Hussein-20261004_210837-Meeting%20Recording.mp4"
)
EXAMPLE_SITE = "https://mustedueg-my.sharepoint.com/personal/200053683_must_edu_eg"
EXAMPLE_PATH = (
    "/personal/200053683_must_edu_eg/Documents/Recordings/Meeting with "
    "200053683-Mustafa Mahmoud Amin Ahmed Hussein-20261004_210837-Meeting Recording.mp4"
)
STREAM_URL = (
    EXAMPLE_SITE + "/_layouts/15/stream.aspx?id=%2Fpersonal%2F200053683%5Fmust%5Fedu%5Feg"
    "%2FDocuments%2FRecordings%2FMeeting%20with%20200053683%2DMustafa%20Mahmoud%20Amin"
    "%20Ahmed%20Hussein%2D20261004%5F210837%2DMeeting%20Recording%2Emp4"
    "&nav=eyJyZWZlcnJhbEluZm8iOnsicmVmZXJyYWxBcHAiOiJTdHJlYW1XZWJBcHAiLCJyZWZlcnJhbFZp"
    "ZXciOiJTaGFyZURpYWxvZy1MaW5rIiwicmVmZXJyYWxBcHBQbGF0Zm9ybSI6IldlYiIsInJlZmVycmFs"
    "TW9kZSI6InZpZXcifX0&ga=1&referrer=StreamWebApp%2EWeb"
    "&referrerScenario=AddressBarCopied%2Eview%2Ef45b91b1%2Dbcb9%2D4ce3%2D81b3%2D09b389beb541"
)
SHARE_URL = (
    "https://mustedueg-my.sharepoint.com/:v:/g/personal/200053683_must_edu_eg/"
    + base64.urlsafe_b64encode(
        b"\x21\x00" + uuid.UUID("600ce640-c681-4d6f-8871-8f1b934322e0").bytes_le
        + b"test-signature"
    ).decode().rstrip("=")
    + "?nav=ignored%3D&e=test"
)


def test_download_aspx_url():
    site, uid = parse_video_url(
        "https://mustedueg.sharepoint.com/sites/MUSTCPC27/"
        "_layouts/15/download.aspx?UniqueId=d74df603-3cea-48d6-beee-c423bc953c87"
    )
    assert site == "https://mustedueg.sharepoint.com/sites/MUSTCPC27"
    assert uid == "d74df603-3cea-48d6-beee-c423bc953c87"


def test_rejects_non_sharepoint():
    try:
        parse_video_url("https://example.com/video.mp4")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_rejects_garbage_sharepoint_path():
    try:
        parse_video_url("https://mustedueg.sharepoint.com/sites/MUSTCPC27")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_personal_onedrive_example():
    assert parse_video_url(EXAMPLE_URL) == (EXAMPLE_SITE, EXAMPLE_PATH)


@pytest.mark.parametrize("site_path", ["/sites/Other", "/teams/Other", "/personal/other", ""])
def test_source_url_for_any_tenant(site_path):
    site = "https://another-my.sharepoint.com" + site_path
    path = site_path + "/Documents/Recordings/Session #1's 100%20.mp4"
    source = "https://another-my.sharepoint.com" + quote(path, safe="/")
    url = site + "/_layouts/15/download.aspx?SourceUrl=" + quote(source, safe="")
    assert parse_video_url(url) == (site, path)


@pytest.mark.parametrize("site_path", ["/sites/Other", "/teams/Other", "/personal/other", ""])
@pytest.mark.parametrize("prefix", ["", "/:v:/r"])
def test_direct_and_resource_links(site_path, prefix):
    path = site_path + "/Documents/Session #1's 100%20.mp4"
    url = "https://other.sharepoint.com" + prefix + quote(path, safe="/") + "?web=1"
    assert parse_video_url(url) == ("https://other.sharepoint.com" + site_path, path)


def test_viewer_id_is_decoded_once():
    path = "/personal/owner/Documents/Session #1's 100%20.mp4"
    url = (
        "https://other-my.sharepoint.com/personal/owner/_layouts/15/onedrive.aspx?id="
        + quote(path, safe="")
    )
    assert parse_video_url(url) == ("https://other-my.sharepoint.com/personal/owner", path)


def test_root_viewer_uses_file_site():
    path = "/personal/owner/Documents/Session.mp4"
    url = "https://other-my.sharepoint.com/_layouts/15/onedrive.aspx?id=" + quote(path, safe="")
    assert parse_video_url(url) == ("https://other-my.sharepoint.com/personal/owner", path)


@pytest.mark.parametrize("key", ["UniqueId", "UNIQUEID", "sourcedoc"])
def test_guid_links_on_personal_site(key):
    uid = "d74df603-3cea-48d6-beee-c423bc953c87"
    site = "https://other-my.sharepoint.com/personal/owner"
    assert parse_video_url(site + "/_layouts/15/stream.aspx?" + key + "=%7B" + uid + "%7D") == (site, uid)


@pytest.mark.parametrize("sharing_path,site_path", [
    ("/:v:/s/Other/", "/sites/Other"),
    ("/:v:/t/Other/", "/teams/Other"),
    ("/:v:/g/personal/owner/", "/personal/owner"),
])
def test_sharing_token_links(sharing_path, site_path):
    uid = uuid.UUID("d74df603-3cea-48d6-beee-c423bc953c87")
    token = base64.urlsafe_b64encode(b"\x01\x00" + uid.bytes_le + b"signature").decode().rstrip("=")
    assert parse_video_url("https://other.sharepoint.com" + sharing_path + token) == (
        "https://other.sharepoint.com" + site_path, str(uid)
    )


@pytest.mark.parametrize("url", [
    "http://other.sharepoint.com/Documents/a.mp4",
    "https://other.sharepoint.com.evil.test/Documents/a.mp4",
    "https://user:password@other.sharepoint.com/Documents/a.mp4",
    "https://other.sharepoint.com/sites/A/_layouts/15/download.aspx?SourceUrl=https%3A%2F%2Fevil.test%2Fa.mp4",
    "https://other.sharepoint.com/sites/A/_layouts/15/download.aspx?SourceUrl=%2Fsites%2FAB%2FDocuments%2Fa.mp4",
    "https://other.sharepoint.com/sites/A/_layouts/15/download.aspx?SourceUrl=relative.mp4",
    "https://other.sharepoint.com/:v:/s/Other/invalid!token",
    "https://other.sharepoint.com/:v:/s/Other/YQ",
])
def test_rejects_invalid_links(url):
    with pytest.raises(ValueError):
        parse_video_url(url)


def test_file_path_lookup_escapes_odata_and_url_characters():
    session = Mock()
    path = "/personal/owner/Documents/Session #1's 100%20.mp4"
    session.get.return_value.json.return_value = {
        "Name": "Session #1's 100%20.mp4",
        "ServerRelativeUrl": path,
        "ListItemAllFields": {"ParentList": {"RootFolder": {"ServerRelativeUrl": "/personal/owner/Documents"}}},
    }
    name, file_path, library = get_file_info(session, "https://other.sharepoint.com/personal/owner", path)
    url = session.get.call_args.args[0]
    assert "GetFileByServerRelativePath(decodedUrl='" in url
    assert "Session%20%231%27%27s%20100%2520.mp4" in url
    assert "Session #1''s 100%20.mp4" in unquote(url)
    assert (name, file_path, library) == ("Session #1's 100%20.mp4", path, "/personal/owner/Documents")
    session.get.return_value.raise_for_status.assert_called_once()


@pytest.mark.parametrize("download_field", ["@content.downloadUrl", "@microsoft.graph.downloadUrl"])
def test_example_extracts_download_url_using_actual_library(tmp_path, monkeypatch, download_field):
    import mustcpc.sharepoint as sp

    state = tmp_path / "state.json"
    state.write_text('{"cookies": []}')
    session = Mock()
    file_info = Mock()
    file_info.json.return_value = {
        "Name": EXAMPLE_PATH.rsplit("/", 1)[1],
        "ServerRelativeUrl": EXAMPLE_PATH,
        "ListItemAllFields": {"ParentList": {"RootFolder": {"ServerRelativeUrl": "/personal/200053683_must_edu_eg/Documents"}}},
    }
    drives = Mock()
    drives.json.return_value = {"value": [
        {"id": "wrong", "webUrl": EXAMPLE_SITE + "/Other"},
        {"id": "personal-drive", "webUrl": EXAMPLE_SITE + "/Documents"},
    ]}
    download = Mock()
    download.json.return_value = {download_field: "https://download.example/video"}
    session.get.side_effect = [file_info, drives, download]
    monkeypatch.setattr(sp.requests, "Session", lambda: session)

    assert extract_ddl(EXAMPLE_URL, state) == (
        EXAMPLE_PATH.rsplit("/", 1)[1], "https://download.example/video"
    )
    calls = session.get.call_args_list
    assert calls[0].args[0].startswith(EXAMPLE_SITE + "/_api/web/GetFileByServerRelativePath(")
    assert calls[1].args[0] == EXAMPLE_SITE + "/_api/v2.0/drives"
    assert calls[2].args[0] == (
        EXAMPLE_SITE + "/_api/v2.0/drives/personal-drive/root:/"
        + quote(EXAMPLE_PATH.split("/Documents/", 1)[1], safe="/()!$,-._~'")
    )


def test_guid_lookup_preserves_existing_api():
    session = Mock()
    uid = "d74df603-3cea-48d6-beee-c423bc953c87"
    library = "/sites/Other/Documents"
    session.get.return_value.json.return_value = {
        "Name": "Session.mp4",
        "ServerRelativeUrl": library + "/Session.mp4",
        "ListItemAllFields": {"ParentList": {"RootFolder": {"ServerRelativeUrl": library}}},
    }
    assert get_file_info(session, "https://other.sharepoint.com/sites/Other", uid) == (
        "Session.mp4", library + "/Session.mp4", library
    )
    assert session.get.call_args.args[0].startswith(
        f"https://other.sharepoint.com/sites/Other/_api/web/GetFileById('{uid}')?"
    )


def test_exact_stream_url_points_to_same_file():
    assert parse_video_url(STREAM_URL) == parse_video_url(EXAMPLE_URL)


def test_sharing_link_preserves_access_before_lookup(tmp_path, monkeypatch):
    import mustcpc.sharepoint as sp

    state = tmp_path / "state.json"
    state.write_text('{"cookies": []}')
    session = Mock()
    page = Mock()
    session.cookies = requests.cookies.RequestsCookieJar()
    page.url = STREAM_URL
    page.text = "<script>var g_fileInfo = " + json.dumps({
        "name": "Recording.mp4",
        "downloadUrl": "https://example.sharepoint.com/download.aspx?tempauth=signed",
        "downloadUrlNoAuth": "https://example.sharepoint.com/download.aspx",
    }) + ";</script>"
    session.get.return_value = page
    monkeypatch.setattr(sp.requests, "Session", lambda: session)

    assert extract_ddl(SHARE_URL, state) == (
        "Recording.mp4", "https://example.sharepoint.com/download.aspx?tempauth=signed"
    )
    assert session.get.call_args.args[0] == SHARE_URL
    assert session.get.call_count == 1


@pytest.mark.parametrize("url", [EXAMPLE_URL, STREAM_URL])
def test_host_auth_failure_restores_browser_session(url, tmp_path, monkeypatch):
    import mustcpc.sharepoint as sp

    state = tmp_path / "state.json"
    state.write_text('{"cookies": []}')
    session = Mock()
    forbidden = Mock(status_code=403)
    forbidden.raise_for_status.side_effect = requests.HTTPError(response=forbidden)
    login_page = Mock(url="https://login.microsoftonline.com/authorize", text="login")
    session.get.side_effect = [forbidden, login_page]
    monkeypatch.setattr(sp.requests, "Session", lambda: session)
    browser = Mock(return_value=("Recording.mp4", "https://example.sharepoint.com/signed"))
    monkeypatch.setattr(sp, "_extract_with_browser", browser, raising=False)

    assert extract_ddl(url, state) == ("Recording.mp4", "https://example.sharepoint.com/signed")
    viewer_url = session.get.call_args.args[0]
    assert "/stream.aspx?" in viewer_url
    assert parse_video_url(viewer_url) == (EXAMPLE_SITE, EXAMPLE_PATH)
    browser.assert_called_once_with(viewer_url, state)


def test_shared_access_cookies_persist_without_losing_other_login_state(tmp_path):
    from mustcpc.sharepoint import _save_session_cookies, load_session

    state = tmp_path / "state.json"
    original = {
        "cookies": [{"name": "other-login", "value": "fake", "domain": "login.microsoftonline.com", "path": "/"}],
        "origins": [{"origin": "https://login.microsoftonline.com", "localStorage": []}],
    }
    state.write_text(json.dumps(original))
    session = requests.Session()
    cookie = requests.cookies.create_cookie(
        "FedAuth", "fake-shared-access", domain="mustedueg-my.sharepoint.com",
        path="/", secure=True, expires=2000000000,
        rest={"HttpOnly": None, "SameSite": "None"},
    )
    session.cookies.set_cookie(cookie)
    _save_session_cookies(session, state)
    saved = json.loads(state.read_text())
    assert saved["origins"] == original["origins"]
    assert saved["cookies"][0] == original["cookies"][0]
    assert saved["cookies"][1]["httpOnly"] is True
    assert saved["cookies"][1]["secure"] is True
    assert saved["cookies"][1]["expires"] == 2000000000
    assert load_session(state).cookies.get("FedAuth", domain="mustedueg-my.sharepoint.com") == "fake-shared-access"
    _save_session_cookies(session, state)
    assert json.loads(state.read_text()) == saved


def test_download_url_without_auth_is_not_used_for_vps():
    from mustcpc.sharepoint import _viewer_download

    assert _viewer_download({"name": "Recording.mp4", "downloadUrlNoAuth": "https://example.sharepoint.com/download.aspx"}) is None


def test_download_restrictions_are_reported():
    from mustcpc.sharepoint import SharePointAccessError, _viewer_download

    with pytest.raises(SharePointAccessError, match="disabled downloads"):
        _viewer_download({"name": "Recording.mp4", "isDownloadBlocked": True, "downloadUrl": "https://example.sharepoint.com/signed"})


def test_cli_shows_access_error_without_traceback(monkeypatch, capsys):
    import importlib

    cli_module = importlib.import_module("mustcpc.cli")
    from mustcpc.sharepoint import SharePointAccessError

    monkeypatch.setattr(cli_module, "cli", Mock(side_effect=SharePointAccessError("Log in to the video host.")))
    with pytest.raises(SystemExit) as exc:
        cli_module.main()
    assert exc.value.code == 1
    assert capsys.readouterr().err == "Error: Log in to the video host.\n"


def test_existing_sharing_links_can_use_api_after_opening_page(tmp_path, monkeypatch):
    import mustcpc.sharepoint as sp

    state = tmp_path / "state.json"
    state.write_text('{"cookies": []}')
    session = Mock(cookies=requests.cookies.RequestsCookieJar())
    session.get.return_value = Mock(url=STREAM_URL, text="<html>Older video viewer</html>")
    monkeypatch.setattr(sp.requests, "Session", lambda: session)
    api = Mock(return_value=("Recording.mp4", "https://example.sharepoint.com/signed"))
    monkeypatch.setattr(sp, "_extract_with_api", api)
    assert extract_ddl(SHARE_URL, state) == ("Recording.mp4", "https://example.sharepoint.com/signed")
    assert session.get.call_args.args[0] == SHARE_URL
    api.assert_called_once_with(session, *parse_video_url(SHARE_URL))


@pytest.mark.parametrize("blocked", [False, True])
def test_browser_recovery_blocks_video_and_saves_only_successful_login(tmp_path, monkeypatch, blocked):
    import playwright.sync_api as pw
    from mustcpc.sharepoint import SharePointAccessError, _extract_with_browser

    state = tmp_path / "state.json"
    manager = MagicMock()
    playwright = manager.__enter__.return_value
    browser = playwright.chromium.launch.return_value
    context = browser.new_context.return_value
    page = context.new_page.return_value
    page.url = STREAM_URL
    page.evaluate.return_value = {
        "name": "Recording.mp4", "downloadUrl": "https://example.sharepoint.com/signed",
        "isDownloadBlocked": blocked,
    }
    monkeypatch.setattr(pw, "sync_playwright", lambda: manager)
    if blocked:
        with pytest.raises(SharePointAccessError, match="disabled downloads"):
            _extract_with_browser(STREAM_URL, state)
        context.storage_state.assert_not_called()
    else:
        assert _extract_with_browser(STREAM_URL, state) == ("Recording.mp4", "https://example.sharepoint.com/signed")
        context.storage_state.assert_called_once_with(path=str(state))
    browser.close.assert_called_once()

    route_handler = context.route.call_args.args[1]
    for resource, url in [
        ("media", "https://example.sharepoint.com/Recording.mp4"),
        ("fetch", "https://example.sharepoint.com/player"),
        ("document", "https://example.sharepoint.com/_layouts/15/download.aspx"),
    ]:
        route = Mock()
        route.request.resource_type = resource
        route.request.url = url
        route_handler(route)
        route.abort.assert_called_once()
        route.continue_.assert_not_called()
    auth = Mock()
    auth.request.resource_type = "fetch"
    auth.request.url = "https://login.microsoftonline.com/session"
    route_handler(auth)
    auth.continue_.assert_called_once()
