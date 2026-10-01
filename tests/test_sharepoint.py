"""Unit tests for SharePoint URL parsing (no network needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mustcpc.sharepoint import parse_video_url


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
