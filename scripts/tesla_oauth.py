"""Run the Tesla OAuth dance and persist tokens to SQLite.

Flow:
  1. Script prints an authorization URL.
  2. User opens it, signs in to Tesla, grants consent.
  3. Tesla redirects to TESLA_REDIRECT_URI?code=...&state=... — the page
     itself 404s (expected — our redirect URI hits Cloudflare Pages with
     no matching path) but the URL in the address bar has the code.
  4. User copies that URL from the address bar and pastes it back here.
  5. Script exchanges the code for an access token + refresh token and
     saves them to data/jarvis.sqlite.

Run once:
  uv run python scripts/tesla_oauth.py
"""

import os
import secrets
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ["TESLA_CLIENT_ID"]
CLIENT_SECRET = os.environ["TESLA_CLIENT_SECRET"]
REDIRECT_URI = os.environ["TESLA_REDIRECT_URI"]

AUTH_URL = "https://auth.tesla.com/oauth2/v3/authorize"
TOKEN_URL = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"
AUDIENCE = "https://fleet-api.prd.na.vn.cloud.tesla.com"
SCOPES = (
    "openid offline_access vehicle_device_data "
    "vehicle_cmds vehicle_charging_cmds"
)

DB_PATH = Path("data/jarvis.sqlite")
DB_PATH.parent.mkdir(exist_ok=True)


def main() -> int:
    state = secrets.token_urlsafe(16)
    auth_url = AUTH_URL + "?" + urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
        }
    )

    print("1. Open this URL in your browser and sign in / authorize:")
    print()
    print(f"   {auth_url}")
    print()
    print("2. After you authorize, you'll be redirected to a page that 404s")
    print("   — that's expected. Just copy the FULL URL from the address bar.")
    print(f"   It'll look like {REDIRECT_URI}?code=...&state=...")
    print()
    callback_url = input("3. Paste the redirected URL here: ").strip()

    qs = parse_qs(urlparse(callback_url).query)
    returned_state = qs.get("state", [None])[0]
    code = qs.get("code", [None])[0]

    if returned_state != state:
        print(f"✗ State mismatch (expected {state!r}, got {returned_state!r})")
        return 1
    if not code:
        print("✗ No 'code' in the URL.")
        return 1

    print()
    print("Exchanging code for tokens...")
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "audience": AUDIENCE,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=15,
    )
    if not resp.ok:
        print(f"✗ Token exchange failed: {resp.status_code}")
        print(resp.text)
        return 1

    tokens = resp.json()
    expires_at = time.time() + tokens["expires_in"]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tesla_tokens (
                id            INTEGER PRIMARY KEY,
                access_token  TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at    REAL NOT NULL,
                updated_at    REAL NOT NULL
            )
            """
        )
        conn.execute("DELETE FROM tesla_tokens WHERE id = 1")
        conn.execute(
            "INSERT INTO tesla_tokens (id, access_token, refresh_token, expires_at, updated_at)"
            " VALUES (1, ?, ?, ?, ?)",
            (
                tokens["access_token"],
                tokens["refresh_token"],
                expires_at,
                time.time(),
            ),
        )

    print()
    print("✓ Tokens saved to data/jarvis.sqlite.")
    print(f"  Access token expires in {tokens['expires_in']}s.")
    print("  Refresh token will be used to renew automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
