# mustcpc-yt-upload

Session recordings live on MUST's SharePoint. This tool gets them to the
community YouTube channel without burning your home bandwidth and without
the Entra ID app bureaucracy.

## Why this shape

- MUST blocks logins from most cloud-provider IPs, so SharePoint auth must
  happen **on your PC** (home IP) via a real browser session.
- The official Microsoft Graph/Entra route needs app registration, admin
  consent, and sometimes a credit card. Instead we reuse your browser
  cookies to ask SharePoint for a temporary DDL.
- The VPS does the heavy lifting: it `wget`s the DDL and uploads to YouTube
  from there. Your PC only exchanges small API calls.

```
PC (home IP)                          VPS (datacenter IP)
─────────────                         ───────────────────
mustcpc auth must-login  (browser)
mustcpc ddl "<share-url>" ── cookies ──> SharePoint API ──> DDL
mustcpc upload "<share-url>"
        │── ssh: mkdir workdir
        │── scp: remote_upload.py + requirements.txt + youtube-token.json
        │── ssh: wget "DDL" ──> video file
        │── ssh: python -m venv .mustcpc-venv; pip install -r requirements.txt
        └───── ssh: .mustcpc-venv/bin/python remote_upload.py ──> youtu.be/...
                (cleanup: rm video + venv unless --keep-remote)
```

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium   # only needed for `auth must-login`
cp .env.example .env          # then fill in VPS_HOST, VPS_USER, YT_CHANNEL_ID
```

## First-time setup

```bash
mustcpc auth must-login   # browser opens, log in to MUST, press Enter
mustcpc auth yt-login     # Google OAuth for the community channel
mustcpc vps test          # SSH check + remote python deps check
```

## Everyday use

```bash
# Full pipeline (DDL -> VPS download -> YouTube upload -> cleanup of video + venv)
mustcpc upload "<sharepoint-video-url>" --title "CPC Session 5 - Graphs" --privacy unlisted

# Just print the DDL + wget command
mustcpc ddl "<sharepoint-video-url>"

# Download to VPS without uploading (then upload later / manually)
mustcpc vps download "<sharepoint-video-url>"

# Re-push YouTube credentials after re-auth
mustcpc vps push-auth

# Health check
mustcpc doctor
```

See [docs/USAGE.md](docs/USAGE.md) for all commands, `.env` keys, VPS
requirements, and troubleshooting.

## Layout

```
src/mustcpc/    CLI + modules (config, sharepoint, youtube, vps, pipeline)
remote/         remote_upload.py — auto-deployed to the VPS, runs there
data/           gitignored: browser profile, must-state.json, tokens (NEVER commit)
tests/          offline unit tests (no network)
```

## Security notes

- `data/`, `.env`, `*token*.json`, `client_secret*.json` are gitignored.
  Real credentials live only in `data/` on your PC and in the VPS workdir
  (mode 600). What you commit: code, `.env.example`, docs.
- The DDL is a short-lived signed URL. Treat it like a password: it goes
  over your existing SSH session only, never into git or chat logs.
