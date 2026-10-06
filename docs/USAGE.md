# Usage guide

## 1. `.env` reference

| Key | Required | Default | Meaning |
| --- | --- | --- | --- |
| `MUSTCPC_VPS_HOST` | yes | — | VPS hostname/IP for ssh |
| `MUSTCPC_VPS_USER` | yes | — | SSH user |
| `MUSTCPC_VPS_PORT` | no | `22` | SSH port |
| `MUSTCPC_VPS_KEY` | no | ssh-agent | Private key path, e.g. `~/.ssh/id_rsa` |
| `MUSTCPC_VPS_WORKDIR` | no | `/home/ubuntu/mustcpc-videos` | Remote dir for videos + bundle |
| `MUSTCPC_VPS_PYTHON` | no | `python3` | Remote python binary |
| `MUSTCPC_MUST_PROFILE_DIR` | no | `data/must-profile` | Persistent browser profile |
| `MUSTCPC_MUST_STATE_FILE` | no | `data/must-state.json` | Playwright storage state (cookies) |
| `MUSTCPC_MUST_START_URL` | no | MUST CPC site | Where `auth must-login` opens |
| `MUSTCPC_YT_CLIENT_SECRET` | yes | `data/client_secret.json` | Google OAuth client (Desktop app) |
| `MUSTCPC_YT_TOKEN_FILE` | yes | `data/youtube-token.json` | Saved OAuth token (created by `auth yt-login`) |
| `MUSTCPC_YT_CHANNEL_ID` | recommended | — | Target channel; uploads abort on mismatch |
| `MUSTCPC_YT_PRIVACY_DEFAULT` | no | `unlisted` | Default for `upload --privacy` |

`mustcpc config show` prints the effective config. `mustcpc --env-file X`
uses a different env file.

## 2. Command reference

```
mustcpc auth must-login [--start-url URL]   browser login, saves data/must-state.json
mustcpc auth yt-login                       Google OAuth, saves data/youtube-token.json
mustcpc auth status                          which local credentials exist
mustcpc ddl URL [--json] [--no-wget]         print filename + DDL (+wget line)
mustcpc vps test                              ssh + workdir + uploader venv check
mustcpc vps bootstrap [--recreate]            deploy bundle + build remote venv
mustcpc vps push-auth                         scp token + secret + uploader to VPS
mustcpc vps download URL [--filename N]       DDL then wget on the VPS
mustcpc vps exec "CMD"                        debug: run anything on the VPS
mustcpc upload URL --title T [--description D]
                   [--privacy private|unlisted|public] [--keep-remote]
mustcpc config show / mustcpc doctor
```

Accepted SharePoint Online URL forms, across `*.sharepoint.com` tenants:

- Team-site sharing links: `:v:/s/<SITE>/<TOKEN>` and `:v:/t/<TEAM>/<TOKEN>`.
- Personal OneDrive sharing links: `:v:/g/personal/<OWNER>/<TOKEN>`.
- Download links with `UniqueId=<GUID>` or `SourceUrl=<file-url>`.
- Viewer links with `id=<server-relative-file-path>` or `sourcedoc=<GUID>`.
- Direct video file URLs and `:v:/r/...` file links.

Sites under `/sites/`, `/teams/`, and `/personal/`, plus root sites, are
supported. Download and upload progress streams live in the terminal.

For a different tenant or personal OneDrive host, save a session on that host:

```bash
mustcpc auth must-login --start-url "<sharepoint-video-url>"
mustcpc ddl "<sharepoint-video-url>"
mustcpc vps download "<sharepoint-video-url>"
```

Log in with an account that can access the recording and wait until it opens
before pressing Enter. Cookies belong to their SharePoint host; a session for
`tenant.sharepoint.com` may need another login for `tenant-my.sharepoint.com`.
The existing command names and environment variable names still apply.

For a shared recording, start with the original `:v:` sharing link. A file GUID
or path alone does not carry the sharing link's permission. The tool opens the
sharing link, reads Stream's signed download URL, and saves any new access
cookies. Subsequent Stream and `SourceUrl` links to that recording use the
saved access.

If the API returns 401 or 403, extraction tries the Stream viewer, then restores
the saved Microsoft login with headless Chromium. Browser recovery blocks video
and background data requests. It refreshes `MUSTCPC_MUST_STATE_FILE` after
successful extraction. Install Chromium with `playwright install chromium` if
it is missing. If login or download permission is still unavailable, the CLI
reports the required action without a traceback.

## 3. VPS requirements

- OpenSSH reachable from your PC with your key (`ssh user@host` works).
- `wget` and `python3` **with the venv module** on the VPS
  (`python3 -m venv --help` should work; on Debian/Ubuntu that may mean
  installing `python3-venv` once via apt).
- Nothing else to maintain: every `upload` auto-deploys `remote_upload.py` +
  `requirements.txt` + fresh credentials, builds `.mustcpc-venv` inside the
  workdir if missing, and pip-installs the uploader deps into it. After a
  successful upload the video file **and** the venv are deleted, unless you
  pass `--keep-remote` (keeps both, so the next upload skips the pip step).
- `mustcpc vps bootstrap` does the deploy + venv build as a standalone step
  (handy after wiping the workdir); `vps test` reports whether the venv is
  ready without building it.

## 4. YouTube notes

- Create the OAuth client as **Desktop app** in Google Cloud Console, download
  the JSON to `data/client_secret.json`. Enable the **YouTube Data API v3**.
- Auth always happens on your PC (`auth yt-login` opens a browser). The VPS
  copy is non-interactive: if the token is missing/invalid, the remote script
  fails fast and tells you to re-run `auth yt-login` + `vps push-auth`.
- If `MUSTCPC_YT_CHANNEL_ID` is set, both local and remote code refuse to
  upload from the wrong channel. Find yours at
  YouTube Studio → Settings → Channel, or `mustcpc` prints what it sees.

## 5. Troubleshooting

- **SharePoint 401/403 on DDL**: log in to the video's host with
  `auth must-login --start-url "<sharepoint-video-url>"`. Check that your account
  can read the recording. MUST blocks cloud IPs, so log in from your PC.
- **Shared recording opens but a Stream or download link fails**: use its
  original `:v:` sharing link once to save access, then retry. Access to the
  MUST CPC host does not automatically grant access to a personal OneDrive
  recording. Download restrictions still apply.
- **`mustcpc vps test` ssh fails**: check `.env` host/user/port/key, and that
  `ssh -i KEY user@host` works by hand. The CLI uses `BatchMode=yes`, so it
  never prompts for a password — use a key or ssh-agent.
- **Remote venv build fails**: the VPS needs `python3` with the venv module
  (`python3-venv` on Debian/Ubuntu via apt). For a fresh start:
  `mustcpc vps bootstrap --recreate`.
- **Wrong YouTube channel**: you authed a personal account. Re-run
  `auth yt-login` with the community account and pick the right channel in
  the consent screen, then `vps push-auth`.
- **Upload stalls at X%**: the remote uploader retries HTTP 500/502/503/504
  automatically; other errors abort and the remote file is kept for inspection
  (re-run without cleanup confusion: pass `--keep-remote` deliberately).
- **Filename looks wrong**: SharePoint names are sanitized
  (`\/:*?"<>|` → `_`). Override with `vps download --filename` or
  `upload --title` (title defaults to the filename stem).
