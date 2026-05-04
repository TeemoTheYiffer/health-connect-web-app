"""Pull the latest Health Connect export from Google Drive.

The phone uploads a zipped SQLite to a known Drive folder on a schedule. We:
1. List the folder, sort by modifiedTime desc, pick the newest .zip.
2. Download it to a temp dir.
3. Unzip the .db and return its path + the source file's metadata.

Authentication uses OAuth user creds (bootstrapped once via scripts/bootstrap_drive_oauth.py),
mirroring the homebase-gcal pattern. The token JSON is read from the path in settings.
"""

from __future__ import annotations

import io
import json
import logging
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from health_connect_web.config import get_settings

log = logging.getLogger(__name__)

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


@dataclass
class DriveExport:
    file_id: str
    file_name: str
    modified_time: datetime
    sqlite_path: Path  # Path to the unzipped .db, in a temp dir the caller should clean up.


def _load_credentials() -> Credentials:
    s = get_settings()
    token_path = s.drive_token_json_path
    if not token_path.exists():
        raise RuntimeError(
            f"Drive token not found at {token_path}. "
            "Run `python scripts/bootstrap_drive_oauth.py` once to create it."
        )
    creds = Credentials.from_authorized_user_file(str(token_path), DRIVE_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _drive_service():
    return build("drive", "v3", credentials=_load_credentials(), cache_discovery=False)


def latest_export_metadata() -> dict | None:
    """Return Drive metadata for the newest export zip in the configured folder, or None."""
    s = get_settings()
    if not s.drive_folder_id:
        raise RuntimeError("DRIVE_FOLDER_ID is not set.")

    svc = _drive_service()
    # Health Connect's exports are typically .zip; match name suffix to be tolerant.
    q = (
        f"'{s.drive_folder_id}' in parents and trashed = false and "
        "(name contains '.zip' or mimeType = 'application/zip')"
    )
    resp = (
        svc.files()
        .list(
            q=q,
            orderBy="modifiedTime desc",
            pageSize=1,
            fields="files(id, name, modifiedTime, size)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = resp.get("files", [])
    return files[0] if files else None


def download_latest_export() -> DriveExport:
    """Download the newest export zip and unzip the .db into a temp dir.

    The caller is responsible for cleaning up the parent directory of `sqlite_path`.
    """
    meta = latest_export_metadata()
    if meta is None:
        raise RuntimeError("No Health Connect export found in the configured Drive folder.")

    svc = _drive_service()
    request = svc.files().get_media(fileId=meta["id"], supportsAllDrives=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buf.seek(0)

    tmpdir = Path(tempfile.mkdtemp(prefix="hcw-export-"))
    with zipfile.ZipFile(buf) as zf:
        # Find the .db member; Health Connect exports usually contain exactly one.
        db_members = [n for n in zf.namelist() if n.endswith(".db")]
        if not db_members:
            raise RuntimeError(f"No .db file inside Drive export {meta['name']!r}")
        if len(db_members) > 1:
            log.warning("Export has %d .db members, using first: %s", len(db_members), db_members[0])
        zf.extract(db_members[0], tmpdir)
        sqlite_path = tmpdir / db_members[0]

    log.info("Downloaded Drive export %s (%s) -> %s", meta["name"], meta["id"], sqlite_path)
    return DriveExport(
        file_id=meta["id"],
        file_name=meta["name"],
        modified_time=datetime.fromisoformat(meta["modifiedTime"].replace("Z", "+00:00")),
        sqlite_path=sqlite_path,
    )


def write_token_from_json_blob(blob: str | dict, dest: Path | None = None) -> Path:
    """Helper for CI: write a token JSON to disk from a string/dict (e.g. a CI variable).

    Returns the path where the token was written.
    """
    s = get_settings()
    target = dest or s.drive_token_json_path
    target.parent.mkdir(parents=True, exist_ok=True)
    text = blob if isinstance(blob, str) else json.dumps(blob)
    target.write_text(text, encoding="utf-8")
    return target
