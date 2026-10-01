"""Runs ON THE VPS. Deployed automatically by `mustcpc` (see vps.deploy_bundle).

Non-interactive: it only uses the youtube-token.json pushed from your PC.
If the token is missing/expired it fails with a message telling you to run
`mustcpc auth yt-login && mustcpc vps push-auth` locally.

VPS requirements: python3 with the venv module + wget. The CLI creates
a `.mustcpc-venv` inside the workdir and pip-installs
remote/requirements.txt into it automatically (deleted after a successful
upload unless --keep-remote is passed).
"""

import argparse
import os
import sys
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube-token.json")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def get_credentials():
    if not os.path.exists(TOKEN_FILE):
        sys.exit(
            "[ERROR] youtube-token.json not found next to remote_upload.py. "
            "On your PC run: mustcpc auth yt-login && mustcpc vps push-auth"
        )
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        print("[AUTH] Refreshing expired access token...")
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    if not creds or not creds.valid:
        sys.exit(
            "[ERROR] Saved YouTube credentials are invalid. "
            "On your PC run: mustcpc auth yt-login && mustcpc vps push-auth"
        )
    return creds


def verify_channel(youtube, expected_channel_id):
    response = youtube.channels().list(part="snippet", mine=True).execute()
    channels = response.get("items", [])
    if not channels:
        sys.exit("[ERROR] No YouTube channel found for the authenticated account.")
    if not expected_channel_id:
        ch = channels[0]
        print(f"[CHANNEL] Using: {ch['snippet']['title']} ({ch['id']})")
        return
    for channel in channels:
        if channel["id"] == expected_channel_id:
            print(f"[CHANNEL] Confirmed: {channel['snippet']['title']}")
            return
    sys.exit(
        f"[ERROR] Wrong YouTube channel. Expected {expected_channel_id}, refusing."
    )


def upload_video(youtube, path, title, description, privacy):
    size = os.path.getsize(path)
    print(f"[UPLOAD] File: {path} ({size / 1024 / 1024:.1f} MB)")
    print(f"[UPLOAD] Title: {title} | Privacy: {privacy}")

    media = MediaFileUpload(path, chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": "27",  # Education
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        },
        media_body=media,
    )

    response = None
    last_percent = -1
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                percent = int(status.progress() * 100)
                if percent != last_percent:
                    print(f"[UPLOAD] {percent}%", flush=True)
                    last_percent = percent
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504):
                print(f"[UPLOAD] Transient error {e.resp.status}, retrying in 5s...")
                time.sleep(5)
                continue
            raise

    video_id = response["id"]
    url = f"https://youtu.be/{video_id}"
    print(f"[DONE] Video ID: {video_id}")
    print(url)
    return url


def main():
    parser = argparse.ArgumentParser(description="Upload a file to YouTube (VPS side).")
    parser.add_argument("video", help="Path to the video file")
    parser.add_argument("--title", help="YouTube title (defaults to filename)")
    parser.add_argument("--description", default="")
    parser.add_argument(
        "--privacy", choices=["private", "unlisted", "public"], default="unlisted"
    )
    parser.add_argument("--expected-channel-id", default="")
    args = parser.parse_args()

    if not os.path.isfile(args.video):
        sys.exit(f"[ERROR] File not found: {args.video}")

    title = args.title or os.path.splitext(os.path.basename(args.video))[0]
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    verify_channel(youtube, args.expected_channel_id)
    upload_video(youtube, args.video, title, args.description, args.privacy)


if __name__ == "__main__":
    main()
