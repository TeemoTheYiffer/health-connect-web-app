"""One-time: run locally to create a Drive read-only OAuth token.

Prereq: Desktop OAuth client downloaded as `.secrets/drive_credentials.json`.
Visit https://console.cloud.google.com/apis/credentials, create a new OAuth client of type
"Desktop app", download the JSON, save it to that path.

Then:
    python scripts/bootstrap_drive_oauth.py

Pops a browser, prompts for consent, writes `.secrets/drive_token.json`.
That JSON is what gets injected into the Cloud Run Job in production.
"""

from __future__ import annotations

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from health_connect_web.config import get_settings
from health_connect_web.sync.drive import DRIVE_SCOPES


def main() -> int:
    s = get_settings()
    creds_path: Path = s.drive_credentials_json_path
    token_path: Path = s.drive_token_json_path

    if not creds_path.exists():
        print(f"Missing credentials JSON at {creds_path}.")
        print("Download the OAuth Desktop client from Google Cloud Console and save it there.")
        return 2

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), DRIVE_SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"Wrote {token_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
