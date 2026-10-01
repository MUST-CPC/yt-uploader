"""One-command pipeline: SharePoint URL (PC) -> VPS download -> YouTube upload."""

from __future__ import annotations

import re
from pathlib import Path

from . import config as config_mod
from . import sharepoint as sp
from . import vps as vps_mod


def sanitize_filename(name: str) -> str:
    """Make a SharePoint file name safe for the VPS filesystem."""
    name = name.strip().replace("\x00", "")
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    if name in ("", ".", ".."):
        return "video.mp4"
    if not Path(name).suffix:
        name += ".mp4"
    return name


def resolve_title(explicit: str | None, filename: str) -> str:
    if explicit:
        return explicit
    return Path(filename).stem


def full_upload(
    cfg: config_mod.Config,
    share_url: str,
    title: str | None = None,
    description: str = "",
    privacy: str | None = None,
    keep_remote: bool = False,
    log=print,
) -> dict:
    """Run the whole pipeline, logging each stage as it happens.

    Download/upload progress streams live through `log`'s stdout.
    Returns info dict with file/video_url.
    """
    privacy = privacy or cfg.yt_privacy_default
    uploader = cfg.repo_root / "remote" / "remote_upload.py"
    if not uploader.exists():
        raise RuntimeError(f"Remote uploader not found: {uploader}")

    log("[1/4] Extracting direct download link...")
    filename, ddl = sp.extract_ddl(share_url, cfg.must_state_path)
    filename = sanitize_filename(filename)
    video_title = resolve_title(title, filename)
    log(f"      File: {filename}")

    log("[2/4] Deploying bundle and downloading on VPS...")
    vps_mod.ensure_workdir(cfg)
    vps_mod.deploy_bundle(
        cfg, uploader, cfg.yt_client_secret_path, cfg.yt_token_path
    )
    remote_video = vps_mod.download_to_vps(cfg, ddl, filename)

    log("[3/4] Uploading to YouTube from VPS...")
    # run_remote_upload provisions the venv itself (idempotent).
    video_url = vps_mod.run_remote_upload(
        cfg,
        remote_video,
        title=video_title,
        description=description,
        privacy=privacy,
        expected_channel_id=cfg.yt_channel_id,
    )

    log("[4/4] Cleaning up VPS...")
    if not keep_remote:
        vps_mod.remove_remote(cfg, remote_video)
        vps_mod.remove_remote_venv(cfg)
        log("      Remote video and uploader venv removed.")
    else:
        log("      Remote video and uploader venv kept.")

    return {
        "filename": filename,
        "title": video_title,
        "remote_video": remote_video,
        "video_url": video_url,
        "kept_remote": keep_remote,
    }
