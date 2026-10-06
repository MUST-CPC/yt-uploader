"""Unit tests for SharePoint URL parsing (no network needed)."""

import base64
import sys
import uuid
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import quote, unquote

import pytest

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
