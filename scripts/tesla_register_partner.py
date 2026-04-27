"""One-shot script to register our domain as a Tesla Fleet API partner.

Tesla fetches our public key from
  https://<TESLA_DOMAIN>/.well-known/appspecific/com.tesla.3p.public-key.pem
and stores it as proof that we control that domain.

Run once after the public key is hosted:
  uv run python scripts/tesla_register_partner.py
"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ["TESLA_CLIENT_ID"]
CLIENT_SECRET = os.environ["TESLA_CLIENT_SECRET"]
DOMAIN = os.environ["TESLA_DOMAIN"]

# North America region (the VIN starting with 7SA = Austin/Texas factory).
AUDIENCE = "https://fleet-api.prd.na.vn.cloud.tesla.com"
TOKEN_URL = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"

print(f"Registering domain: {DOMAIN}")
print()

# Step 1 — client_credentials token (server-to-server, no user yet).
print("Step 1/2: requesting client_credentials token...")
token_resp = requests.post(
    TOKEN_URL,
    data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "openid vehicle_device_data vehicle_cmds vehicle_charging_cmds",
        "audience": AUDIENCE,
    },
    timeout=15,
)
if not token_resp.ok:
    print(f"  ✗ Token request failed: {token_resp.status_code}")
    print(f"  Body: {token_resp.text}")
    sys.exit(1)
access_token = token_resp.json()["access_token"]
print("  ✓ Got token")
print()

# Step 2 — register the partner. Tesla fetches our public key behind the scenes.
print("Step 2/2: registering partner account (Tesla fetches public key)...")
reg_resp = requests.post(
    f"{AUDIENCE}/api/1/partner_accounts",
    headers={"Authorization": f"Bearer {access_token}"},
    json={"domain": DOMAIN},
    timeout=15,
)
print(f"  Status: {reg_resp.status_code}")
print(f"  Body: {reg_resp.text}")
if not reg_resp.ok:
    sys.exit(1)
print()
print("✓ Partner registered.")
