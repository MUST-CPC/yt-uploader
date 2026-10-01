"""VPS access over system ssh/scp. No Paramiko, no extra daemons.

Every function shells out to the `ssh`/`scp` binaries so your
~/.ssh/config, ssh-agent, and key files keep working as usual.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Config


@dataclass
class VPSResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _ssh_prefix(cfg: Config) -> list[str]:
    cmd = ["ssh", "-p", str(cfg.vps_port)]
    if cfg.vps_key:
        cmd += ["-i", str(cfg.vps_key_path)]
    cmd += ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    cmd += [f"{cfg.vps_user}@{cfg.vps_host}"]
    return cmd


def _scp_prefix(cfg: Config) -> list[str]:
    cmd = ["scp", "-P", str(cfg.vps_port)]
    if cfg.vps_key:
        cmd += ["-i", str(cfg.vps_key_path)]
    cmd += ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    return cmd


def run(cfg: Config, remote_cmd: str, check: bool = True) -> VPSResult:
    """Run a shell command on the VPS. Raises RuntimeError on failure if check."""
    problems = cfg.check_vps()
    if problems:
        raise RuntimeError("; ".join(problems) + ". Run `mustcpc config show`.")
    full = _ssh_prefix(cfg) + [remote_cmd]
    proc = subprocess.run(full, capture_output=True, text=True)
    res = VPSResult(proc.returncode, proc.stdout.strip(), proc.stderr.strip())
    if check and not res.ok:
        raise RuntimeError(f"SSH command failed: {remote_cmd}\n{res.stderr}")
    return res


def scp_to(cfg: Config, local: str | Path, remote_path: str) -> None:
    """Copy a local file to an absolute remote path."""
    problems = cfg.check_vps()
    if problems:
        raise RuntimeError("; ".join(problems) + ". Run `mustcpc config show`.")
    local = str(local)
    dest = f"{cfg.vps_user}@{cfg.vps_host}:{remote_path}"
    proc = subprocess.run(_scp_prefix(cfg) + [local, dest], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"scp failed for {local}: {proc.stderr.strip()}")


def ssh_cmd_string(cfg: Config, remote_cmd: str) -> str:
    """Render the equivalent ssh command (for --dry-run / debugging)."""
    return " ".join(shlex.quote(p) for p in _ssh_prefix(cfg)) + " " + shlex.quote(
        remote_cmd
    )


def ensure_workdir(cfg: Config) -> None:
    run(cfg, f"mkdir -p {shlex.quote(cfg.vps_workdir)}")


def test_connection(cfg: Config) -> VPSResult:
    """Check SSH works and report remote python version."""
    run(cfg, "echo ok")
    py = run(
        cfg,
        f"{shlex.quote(cfg.vps_python)} --version && "
        f"{shlex.quote(cfg.vps_python)} -c "
        f"\"import googleapiclient; print('uploader-deps-ok')\"",
        check=False,
    )
    return py


def download_to_vps(cfg: Config, ddl: str, filename: str) -> str:
    """wget the DDL into the VPS workdir. Returns the remote file path."""
    safe_dir = shlex.quote(cfg.vps_workdir)
    # --content-disposition keeps SharePoint's real filename; we then rename
    # to our sanitized filename for predictable later steps.
    remote_tmp = f"{cfg.vps_workdir}/.mustcpc-dl.tmp"
    remote_final = f"{cfg.vps_workdir}/{filename}"
    run(cfg, f"mkdir -p {safe_dir}")
    # Use a temp file then move, so interrupted downloads never look complete.
    cmd = (
        f"rm -f {shlex.quote(remote_tmp)} && "
        f"wget --content-disposition -O {shlex.quote(remote_tmp)} "
        f"{shlex.quote(ddl)} && "
        f"mv {shlex.quote(remote_tmp)} {shlex.quote(remote_final)} && "
        f"ls -la {shlex.quote(remote_final)}"
    )
    run(cfg, cmd)
    return remote_final


def deploy_bundle(
    cfg: Config, uploader_script: str | Path, client_secret: str | Path, token: str | Path
) -> None:
    """Push the remote uploader + YouTube credentials into the VPS workdir."""
    ensure_workdir(cfg)
    scp_to(cfg, uploader_script, f"{cfg.vps_workdir}/remote_upload.py")
    scp_to(cfg, client_secret, f"{cfg.vps_workdir}/client_secret.json")
    scp_to(cfg, token, f"{cfg.vps_workdir}/youtube-token.json")
    run(cfg, f"chmod 600 {shlex.quote(cfg.vps_workdir)}/client_secret.json "
        f"{shlex.quote(cfg.vps_workdir)}/youtube-token.json")


def run_remote_upload(
    cfg: Config,
    remote_video: str,
    title: str,
    description: str = "",
    privacy: str = "unlisted",
    expected_channel_id: str = "",
) -> str:
    """Execute the uploader on the VPS. Returns the YouTube video URL."""
    cmd = (
        f"cd {shlex.quote(cfg.vps_workdir)} && "
        f"{shlex.quote(cfg.vps_python)} remote_upload.py "
        f"{shlex.quote(remote_video)} "
        f"--title {shlex.quote(title)} "
        f"--description {shlex.quote(description)} "
        f"--privacy {shlex.quote(privacy)}"
    )
    if expected_channel_id:
        cmd += f" --expected-channel-id {shlex.quote(expected_channel_id)}"
    res = run(cfg, cmd)
    # remote_upload.py prints the youtu.be link on its last line.
    for line in reversed(res.stdout.splitlines()):
        if "youtu.be/" in line or "youtube.com/watch" in line:
            return line.strip().split()[-1]
    return res.stdout


def remove_remote(cfg: Config, remote_path: str) -> None:
    run(cfg, f"rm -f {shlex.quote(remote_path)}")
