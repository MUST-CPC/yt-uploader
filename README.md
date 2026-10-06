# mustcpc-yt-upload

This CLI transfers recordings from SharePoint Online or OneDrive for Business
to YouTube through your VPS, without using your home connection for video data
or requiring Entra ID app registration. It accepts any `*.sharepoint.com`
tenant, including personal `*-my.sharepoint.com` sites.

## How it works

You run everything from your PC. After two one-time logins (MUST in a
browser, Google for YouTube), a single command does the whole job:

```bash
mustcpc upload "<sharepoint-video-url>" --title "CPC Session 5 - Graphs"
```

That command extracts a temporary direct download link (DDL) using your
saved SharePoint browser session, then drives the VPS over SSH: it downloads the
video there, uploads it to the community YouTube channel from there, and
deletes the remote files afterwards. Progress for each step streams live in
your terminal. Your local internet never touches the video bytes.

## Why this shape

- MUST blocks logins from most cloud-provider IPs, so SharePoint auth must
  happen on your PC (home IP) via a real browser session.
- The official Microsoft Graph/Entra route needs app registration, admin
  consent, sometimes a credit card, and it may or may not work. Instead we reuse your browser
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
playwright install chromium   # browser login and automatic session recovery
cp .env.example .env          # then fill in VPS_HOST, VPS_USER, YT_CHANNEL_ID
```

## First-time setup

```bash
mustcpc auth must-login   # browser opens, log in to MUST, press Enter
mustcpc auth yt-login     # Google OAuth for the community channel
mustcpc vps test          # SSH check + remote python deps check
```

## Everyday use

For another SharePoint tenant or a personal OneDrive site, first save a login
for that host. Open the video with an account that has permission to read it,
then press Enter in the terminal:

```bash
mustcpc auth must-login --start-url "<sharepoint-video-url>"
mustcpc ddl "<sharepoint-video-url>"
```

The command name and `MUSTCPC_MUST_*` settings remain the same. Download links
with `SourceUrl`, including personal meeting recordings, work with `ddl`,
`vps download`, and `upload`.

For a recording shared with you, use its original `:v:` sharing link first.
The tool opens that link and saves the access cookies for its OneDrive host.
You can then use the same recording's Stream `stream.aspx?id=...` link or
`download.aspx?SourceUrl=...` link. Extraction restores the saved browser login
automatically if the API needs authentication on another host.

```bash
# Full pipeline with live progress (DDL -> VPS download bar -> YouTube upload % -> cleanup)
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
