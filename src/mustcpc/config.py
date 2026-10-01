"""Central configuration: .env + defaults, resolved relative to the repo root.

All secrets stay out of git. Copy `.env.example` to `.env` and fill it in.
`mustcpc config show` prints the effective config with secrets redacted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from `start` (or this file) until pyproject.toml is found."""
    here = Path(start) if start else Path(__file__).resolve()
    if here.is_file():
        here = here.parent
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


@dataclass
class Config:
    repo_root: Path = field(default_factory=lambda: find_repo_root())

    # --- VPS (system ssh/scp) ---
    vps_host: str = ""
    vps_user: str = ""
    vps_port: int = 22
    vps_key: str = ""  # path to private key, e.g. ~/.ssh/id_rsa
    vps_workdir: str = "/home/ubuntu/mustcpc-videos"
    vps_python: str = "python3"

    # --- SharePoint (client side, home IP only) ---
    must_profile_dir: str = "data/must-profile"
    must_state_file: str = "data/must-state.json"
    must_start_url: str = "https://mustedueg.sharepoint.com/sites/MUSTCPC27"

    # --- YouTube ---
    yt_client_secret: str = "data/client_secret.json"
    yt_token_file: str = "data/youtube-token.json"
    yt_channel_id: str = ""
    yt_privacy_default: str = "unlisted"

    def resolve(self, path_str: str) -> Path:
        p = Path(os.path.expanduser(path_str))
        if not p.is_absolute():
            p = self.repo_root / p
        return p

    @property
    def vps_key_path(self) -> Path | None:
        if not self.vps_key:
            return None
        return Path(os.path.expanduser(self.vps_key))

    @property
    def must_profile_path(self) -> Path:
        return self.resolve(self.must_profile_dir)

    @property
    def must_state_path(self) -> Path:
        return self.resolve(self.must_state_file)

    @property
    def yt_client_secret_path(self) -> Path:
        return self.resolve(self.yt_client_secret)

    @property
    def yt_token_path(self) -> Path:
        return self.resolve(self.yt_token_file)

    def check_vps(self) -> list[str]:
        """Return a list of missing/invalid VPS settings (empty = OK)."""
        problems = []
        if not self.vps_host:
            problems.append("MUSTCPC_VPS_HOST is not set")
        if not self.vps_user:
            problems.append("MUSTCPC_VPS_USER is not set")
        if self.vps_key and not self.vps_key_path.exists():
            problems.append(f"VPS key not found: {self.vps_key}")
        return problems

    def redacted(self) -> dict:
        return {
            "repo_root": str(self.repo_root),
            "vps_host": self.vps_host or "(unset)",
            "vps_user": self.vps_user or "(unset)",
            "vps_port": self.vps_port,
            "vps_key": self.vps_key or "(default ssh agent/config)",
            "vps_workdir": self.vps_workdir,
            "vps_python": self.vps_python,
            "must_profile_dir": str(self.must_profile_path),
            "must_state_file": str(self.must_state_path),
            "must_start_url": self.must_start_url,
            "yt_client_secret": str(self.yt_client_secret_path),
            "yt_token_file": str(self.yt_token_path),
            "yt_channel_id": self.yt_channel_id or "(unset)",
            "yt_privacy_default": self.yt_privacy_default,
        }


def load_config(env_file: str | Path | None = None) -> Config:
    """Load .env (repo root by default) and build a Config."""
    root = find_repo_root()
    dotenv_path = Path(env_file) if env_file else root / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path, override=False)
    else:
        load_dotenv(override=False)  # fall back to environment only
    return Config(
        repo_root=root,
        vps_host=_env("MUSTCPC_VPS_HOST"),
        vps_user=_env("MUSTCPC_VPS_USER"),
        vps_port=_env_int("MUSTCPC_VPS_PORT", 22),
        vps_key=_env("MUSTCPC_VPS_KEY"),
        vps_workdir=_env("MUSTCPC_VPS_WORKDIR", "/home/ubuntu/mustcpc-videos"),
        vps_python=_env("MUSTCPC_VPS_PYTHON", "python3"),
        must_profile_dir=_env("MUSTCPC_MUST_PROFILE_DIR", "data/must-profile"),
        must_state_file=_env("MUSTCPC_MUST_STATE_FILE", "data/must-state.json"),
        must_start_url=_env(
            "MUSTCPC_MUST_START_URL",
            "https://mustedueg.sharepoint.com/sites/MUSTCPC27",
        ),
        yt_client_secret=_env("MUSTCPC_YT_CLIENT_SECRET", "data/client_secret.json"),
        yt_token_file=_env("MUSTCPC_YT_TOKEN_FILE", "data/youtube-token.json"),
        yt_channel_id=_env("MUSTCPC_YT_CHANNEL_ID"),
        yt_privacy_default=_env("MUSTCPC_YT_PRIVACY_DEFAULT", "unlisted"),
    )
