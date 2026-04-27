"""Tesla Fleet API tools.

Reads (status) work via plain Fleet API GETs with a bearer token.

Writes (lock, start_climate) hit the simple REST command endpoints. Tesla
deprecated these for newer vehicles in favor of signed commands via the
Vehicle Command Protocol — if the user's car needs that, the writes will
return a clear error and we'll address it (likely by adding the
tesla-http-proxy sidecar).
"""

import os
import sqlite3
import time
import warnings
from pathlib import Path
from typing import Any

import requests
import urllib3

from ._result import ToolResult

TOKEN_URL = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"
API_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"
# Writes go through the local tesla-http-proxy, which signs commands using
# our EC private key. Reads stay direct.
PROXY_BASE = os.getenv("TESLA_PROXY_URL", "https://localhost:4443")
DB_PATH = Path("data/jarvis.sqlite")

# Proxy uses a self-signed cert; suppress the "insecure" warning for it.
warnings.filterwarnings(
    "ignore", category=urllib3.exceptions.InsecureRequestWarning
)


def _get_access_token() -> str:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT access_token, refresh_token, expires_at FROM tesla_tokens "
            "WHERE id = 1"
        ).fetchone()
    if row is None:
        raise RuntimeError(
            "No Tesla tokens. Run: uv run python scripts/tesla_oauth.py"
        )
    access_token, refresh_token, expires_at = row
    # Refresh proactively if expiring in <5 minutes.
    if expires_at - time.time() < 300:
        access_token = _refresh(refresh_token)
    return access_token


def _refresh(refresh_token: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": os.environ["TESLA_CLIENT_ID"],
            "refresh_token": refresh_token,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    new_access = data["access_token"]
    new_refresh = data.get("refresh_token", refresh_token)
    expires_at = time.time() + data["expires_in"]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE tesla_tokens SET access_token = ?, refresh_token = ?, "
            "expires_at = ?, updated_at = ? WHERE id = 1",
            (new_access, new_refresh, expires_at, time.time()),
        )
    return new_access


def _api(method: str, path: str, **kwargs: Any) -> requests.Response:
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {_get_access_token()}"
    return requests.request(
        method, f"{API_BASE}{path}", headers=headers, timeout=20, **kwargs
    )


def _proxy(method: str, path: str, **kwargs: Any) -> requests.Response:
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {_get_access_token()}"
    return requests.request(
        method,
        f"{PROXY_BASE}{path}",
        headers=headers,
        timeout=20,
        verify=False,
        **kwargs,
    )


def _vin() -> str:
    resp = _api("GET", "/api/1/vehicles")
    resp.raise_for_status()
    vehicles = resp.json().get("response") or []
    if not vehicles:
        raise RuntimeError("No vehicles on this Tesla account.")
    return vehicles[0]["vin"]


def _status(args: dict[str, Any]) -> ToolResult:
    try:
        vin = _vin()
        resp = _api("GET", f"/api/1/vehicles/{vin}/vehicle_data")
        if resp.status_code == 408:
            return ToolResult(
                text="The car is asleep. Try again in a moment to wake it."
            )
        resp.raise_for_status()
        data = resp.json()["response"]
        charge = data.get("charge_state", {})
        veh = data.get("vehicle_state", {})

        battery = charge.get("battery_level")
        miles = charge.get("battery_range")
        charging_state = charge.get("charging_state")
        locked = veh.get("locked")

        parts: list[str] = []
        if battery is not None:
            parts.append(f"Battery is at {battery} percent")
            if miles is not None:
                parts[-1] += f" with about {round(miles)} miles of range"
            parts[-1] += "."
        if locked is True:
            parts.append("Doors are locked.")
        elif locked is False:
            parts.append("Doors are unlocked.")
        if charging_state == "Charging":
            parts.append("Currently charging.")
        elif charging_state == "Disconnected":
            parts.append("Not plugged in.")
        elif charging_state == "Stopped":
            parts.append("Plugged in but charging stopped.")
        elif charging_state == "Complete":
            parts.append("Charging complete.")
        return ToolResult(text=" ".join(parts) or "No status fields returned.")
    except Exception as e:
        return ToolResult(text=f"Couldn't reach the car: {e}")


def _wait_for_online(vin: str, timeout_s: float = 30.0) -> bool:
    """Trigger wake_up and poll the vehicle list until it reports state=online."""
    _api("POST", f"/api/1/vehicles/{vin}/wake_up")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(2)
        resp = _api("GET", "/api/1/vehicles")
        if resp.ok:
            for v in resp.json().get("response") or []:
                if v.get("vin") == vin and v.get("state") == "online":
                    return True
    return False


def _safety_block_reason(data: dict[str, Any]) -> str | None:
    """If a write would be unsafe (someone in/driving the car), return a reason."""
    veh = data.get("vehicle_state") or {}
    drive = data.get("drive_state") or {}
    if veh.get("is_user_present") is True:
        return "someone is in the car"
    shift = drive.get("shift_state")
    if shift and shift != "P":
        return f"the car is in gear ({shift})"
    speed = drive.get("speed")
    if speed is not None and speed > 0:
        return "the car is moving"
    return None


def _command(action_label: str, command_path: str) -> ToolResult:
    try:
        vin = _vin()

        # Pre-flight safety check: only proceed if the car is unattended and parked.
        state_resp = _api("GET", f"/api/1/vehicles/{vin}/vehicle_data")
        if state_resp.status_code == 408:
            # Asleep means nobody is in or driving it. Wake and re-check.
            if not _wait_for_online(vin):
                return ToolResult(
                    text="Couldn't wake the car in time. Try again in a moment."
                )
            state_resp = _api("GET", f"/api/1/vehicles/{vin}/vehicle_data")
        if not state_resp.ok:
            return ToolResult(
                text=(
                    f"Couldn't read vehicle state (HTTP {state_resp.status_code}) — "
                    "refusing the command to be safe."
                )
            )

        reason = _safety_block_reason(state_resp.json()["response"])
        if reason:
            return ToolResult(text=f"Holding off on {action_label.lower()} — {reason}.")

        resp = _proxy("POST", f"/api/1/vehicles/{vin}/command/{command_path}")
        if resp.status_code == 200:
            body = resp.json().get("response") or {}
            if body.get("result"):
                return ToolResult(text=f"{action_label} succeeded.")
            why = body.get("reason") or "no reason given"
            return ToolResult(text=f"{action_label} failed: {why}")
        return ToolResult(
            text=(
                f"{action_label} failed (HTTP {resp.status_code}). "
                f"Body: {resp.text[:200]}"
            )
        )
    except requests.exceptions.ConnectionError:
        return ToolResult(
            text="Tesla command proxy isn't running — can't send the command."
        )
    except Exception as e:
        return ToolResult(text=f"Couldn't reach the car: {e}")


def _lock(args: dict[str, Any]) -> ToolResult:
    return _command("Lock", "door_lock")


def _start_climate(args: dict[str, Any]) -> ToolResult:
    return _command("Start climate", "auto_conditioning_start")


TOOLS: list[tuple[dict[str, Any], Any]] = [
    (
        {
            "type": "function",
            "function": {
                "name": "tesla_status",
                "description": (
                    "Get the user's Tesla status: battery percent, range in "
                    "miles, charging state (charging / not plugged in / "
                    "complete), and lock state."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _status,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "lock_tesla",
                "description": "Lock the doors of the user's Tesla.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _lock,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "start_tesla_climate",
                "description": (
                    "Start the Tesla climate control (HVAC) to pre-condition "
                    "the cabin. Use for 'cool the car', 'start the AC', "
                    "'warm up the car'."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _start_climate,
    ),
]
