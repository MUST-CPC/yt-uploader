"""`mustcpc` command line interface.

Typical first-time flow:
  1. cp .env.example .env   (fill in VPS_HOST, VPS_USER, YT_CHANNEL_ID)
  2. mustcpc auth must-login        # browser login to MUST (home IP)
  3. mustcpc auth yt-login          # Google OAuth for YouTube (local)
  4. mustcpc vps test               # check ssh + remote python deps
  5. mustcpc upload "<share-url>" --title "Session 1"

Everyday use is just step 5.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import click

from . import __version__, sharepoint as sp, vps as vps_mod, youtube as yt
from .config import load_config
from .pipeline import full_upload, resolve_title, sanitize_filename


def _cfg(env_file):
    return load_config(env_file)


@click.group()
@click.option("--env-file", default=None, help="Path to .env file.")
@click.version_option(__version__)
@click.pass_context
def cli(ctx, env_file):
    ctx.ensure_object(dict)
    ctx.obj["env_file"] = env_file


# ---------------- config ----------------

@cli.group()
def config():
    """Inspect configuration."""


@config.command("show")
@click.pass_context
def config_show(ctx):
    """Print effective config (secrets redacted)."""
    cfg = _cfg(ctx.obj["env_file"])
    for k, v in cfg.redacted().items():
        click.echo(f"{k}={v}")
    missing = cfg.check_vps()
    if missing:
        click.echo()
        click.echo("VPS config issues:")
        for m in missing:
            click.echo(f"  - {m}")


@cli.command()
@click.pass_context
def doctor(ctx):
    """Check local files, credentials, and VPS connectivity."""
    cfg = _cfg(ctx.obj["env_file"])
    ok = True

    def check(label, cond, hint=""):
        nonlocal ok
        click.echo(f"[{'OK' if cond else '!!'}] {label}" + ("" if cond else f" -- {hint}"))
        if not cond:
            ok = False

    check("SharePoint state", cfg.must_state_path.exists(),
          f"run `mustcpc auth must-login` (looked at {cfg.must_state_path})")
    check("YouTube client secret", cfg.yt_client_secret_path.exists(),
          f"place it at {cfg.yt_client_secret_path}")
    check("YouTube token", cfg.yt_token_path.exists(),
          "run `mustcpc auth yt-login`")
    check("VPS settings", not cfg.check_vps(),
          "; ".join(cfg.check_vps()) or "")

    if not cfg.check_vps():
        try:
            res = vps_mod.run(cfg, "echo ok")
            check("VPS ssh", res.ok and res.stdout == "ok", res.stderr)
        except Exception as e:  # noqa: BLE001
            check("VPS ssh", False, str(e))
    sys.exit(0 if ok else 1)


# ---------------- auth ----------------

@cli.group()
def auth():
    """Log in to SharePoint and YouTube."""


@auth.command("must-login")
@click.option("--start-url", default=None, help="SharePoint site or OneDrive video URL to log in to.")
@click.pass_context
def auth_must_login(ctx, start_url):
    """Browser login to SharePoint/OneDrive, saves session for DDL extraction."""
    cfg = _cfg(ctx.obj["env_file"])
    cfg.must_profile_path.mkdir(parents=True, exist_ok=True)
    click.echo(f"Profile: {cfg.must_profile_path}")
    sp.must_login(
        cfg.must_profile_path, cfg.must_state_path, start_url or cfg.must_start_url
    )
    click.echo(f"Saved session: {cfg.must_state_path}")


@auth.command("yt-login")
@click.pass_context
def auth_yt_login(ctx):
    """Google OAuth for YouTube (runs locally, saves token)."""
    cfg = _cfg(ctx.obj["env_file"])
    if not cfg.yt_client_secret_path.exists():
        raise click.ClickException(
            f"Client secret not found: {cfg.yt_client_secret_path}"
        )
    path = yt.obtain_token(cfg.yt_client_secret_path, cfg.yt_token_path)
    click.echo(f"Saved: {path}")
    click.echo("Next: mustcpc vps push-auth")


@auth.command("status")
@click.pass_context
def auth_status(ctx):
    """Show which credentials exist locally."""
    cfg = _cfg(ctx.obj["env_file"])
    for label, p in [
        ("SharePoint state", cfg.must_state_path),
        ("YouTube client secret", cfg.yt_client_secret_path),
        ("YouTube token", cfg.yt_token_path),
    ]:
        exists = Path(p).exists()
        click.echo(f"[{'OK' if exists else '--'}] {label}: {p}")


# ---------------- ddl ----------------

@cli.command()
@click.argument("share_url")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
@click.option("--wget/--no-wget", default=True, help="Also print the VPS wget command.")
@click.pass_context
def ddl(ctx, share_url, as_json, wget):
    """Extract the direct download link from a SharePoint video URL."""
    cfg = _cfg(ctx.obj["env_file"])
    if not cfg.must_state_path.exists():
        raise click.ClickException(
            f"SharePoint session not found: {cfg.must_state_path}. "
            "Run `mustcpc auth must-login` first."
        )
    filename, ddl_url = sp.extract_ddl(share_url, cfg.must_state_path)
    filename = sanitize_filename(filename)
    if as_json:
        click.echo(json.dumps({"filename": filename, "ddl": ddl_url}))
        return
    click.echo(f"File: {filename}")
    click.echo()
    click.echo("DIRECT DOWNLOAD URL:")
    click.echo(ddl_url)
    if wget:
        click.echo()
        click.echo("VPS command:")
        click.echo(f"wget --content-disposition {shlex.quote(ddl_url)}")


# ---------------- vps ----------------

@cli.group()
def vps():
    """VPS operations over ssh/scp."""


@vps.command("test")
@click.pass_context
def vps_test(ctx):
    """Test SSH and check the remote uploader venv."""
    cfg = _cfg(ctx.obj["env_file"])
    vps_mod.ensure_workdir(cfg)
    click.echo(f"[OK] SSH works, workdir ready: {cfg.vps_workdir}")
    res = vps_mod.test_connection(cfg)
    click.echo(f"[OK] Remote {res.stdout.splitlines()[0] if res.stdout else 'python found'}")
    venv = vps_mod.venv_ready(cfg)
    if "uploader-deps-ok" in venv.stdout:
        click.echo("[OK] Remote uploader venv ready.")
    else:
        click.echo(
            "[..] Remote uploader venv not set up yet. "
            "Run `mustcpc vps bootstrap` once, or just `mustcpc upload` "
            "(it provisions the venv automatically)."
        )


@vps.command("bootstrap")
@click.option(
    "--recreate",
    is_flag=True,
    help="Delete the remote venv and build it from scratch.",
)
@click.pass_context
def vps_bootstrap(ctx, recreate):
    """Deploy the bundle and (re)build the remote uploader venv."""
    cfg = _cfg(ctx.obj["env_file"])
    uploader = cfg.repo_root / "remote" / "remote_upload.py"
    vps_mod.deploy_bundle(cfg, uploader, cfg.yt_client_secret_path, cfg.yt_token_path)
    click.echo(f"[OK] Bundle deployed to {cfg.vps_workdir}")
    vps_mod.ensure_remote_venv(cfg, recreate=recreate)
    click.echo("[OK] Remote uploader venv ready.")


@vps.command("push-auth")
@click.pass_context
def vps_push_auth(ctx):
    """Copy YouTube token + client secret to the VPS workdir."""
    cfg = _cfg(ctx.obj["env_file"])
    for p, label in [
        (cfg.yt_client_secret_path, "client secret"),
        (cfg.yt_token_path, "YouTube token"),
    ]:
        if not Path(p).exists():
            raise click.ClickException(f"{label} not found: {p}")
    uploader = cfg.repo_root / "remote" / "remote_upload.py"
    vps_mod.deploy_bundle(cfg, uploader, cfg.yt_client_secret_path, cfg.yt_token_path)
    click.echo(f"[OK] Auth bundle deployed to {cfg.vps_workdir}")


@vps.command("download")
@click.argument("share_url")
@click.option("--filename", default=None, help="Override remote filename.")
@click.option("--no-deploy", is_flag=True, help="Skip deploying the upload bundle.")
@click.pass_context
def vps_download(ctx, share_url, filename, no_deploy):
    """Extract DDL locally, then wget it into the VPS workdir."""
    cfg = _cfg(ctx.obj["env_file"])
    probed, ddl_url = sp.extract_ddl(share_url, cfg.must_state_path)
    filename = sanitize_filename(filename or probed)
    click.echo(f"[1/3] DDL ready for: {filename}")
    vps_mod.ensure_workdir(cfg)
    click.echo(f"[2/3] Workdir ready: {cfg.vps_workdir}")
    if not no_deploy:
        uploader = cfg.repo_root / "remote" / "remote_upload.py"
        vps_mod.deploy_bundle(
            cfg, uploader, cfg.yt_client_secret_path, cfg.yt_token_path
        )
        click.echo("[2/3] Upload bundle deployed.")
    click.echo("[3/3] Downloading (live progress below)...")
    remote_video = vps_mod.download_to_vps(cfg, ddl_url, filename)
    click.echo(f"[3/3] Downloaded: {remote_video}")


@vps.command("exec")
@click.argument("command")
@click.pass_context
def vps_exec(ctx, command):
    """Run an arbitrary command on the VPS (for debugging)."""
    cfg = _cfg(ctx.obj["env_file"])
    res = vps_mod.run(cfg, command)
    click.echo(res.stdout)


# ---------------- upload ----------------

@cli.command()
@click.argument("share_url")
@click.option("--title", default=None, help="YouTube title (default: filename).")
@click.option("--description", default="", help="YouTube description.")
@click.option(
    "--privacy",
    type=click.Choice(["private", "unlisted", "public"]),
    default=None,
    help="Defaults to MUSTCPC_YT_PRIVACY_DEFAULT.",
)
@click.option(
    "--keep-remote",
    is_flag=True,
    help="Keep the video file and uploader venv on the VPS after upload.",
)
@click.pass_context
def upload(ctx, share_url, title, description, privacy, keep_remote):
    """Full pipeline: DDL (PC) -> download (VPS) -> YouTube upload -> cleanup."""
    cfg = _cfg(ctx.obj["env_file"])
    if not cfg.must_state_path.exists():
        raise click.ClickException("Run `mustcpc auth must-login` first.")
    if not cfg.yt_token_path.exists():
        raise click.ClickException("Run `mustcpc auth yt-login` first.")

    info = full_upload(cfg, share_url, title, description, privacy, keep_remote,
                       log=click.echo)
    click.echo(f"Title: {resolve_title(title, info['filename'])}")
    click.echo(info["video_url"])


def main():
    try:
        cli()
    except sp.SharePointAccessError as exc:
        click.ClickException(str(exc)).show()
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
