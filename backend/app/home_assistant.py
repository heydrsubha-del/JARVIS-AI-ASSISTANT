from __future__ import annotations
from typing import Any
import httpx

from .config import get_settings

settings = get_settings()


def _client() -> httpx.AsyncClient:
    if not settings.ha_url or not settings.ha_long_lived_token:
        raise RuntimeError("Home Assistant is not configured")
    return httpx.AsyncClient(
        base_url=settings.ha_url.rstrip("/"),
        headers={"Authorization": f"Bearer {settings.ha_long_lived_token}", "Content-Type": "application/json"},
        timeout=httpx.Timeout(8.0, connect=3.0),
    )


def result_ok(data: Any = None) -> dict:
    return {"ok": True, "data": data, "error": None}


def result_error(code: str, message: str) -> dict:
    return {"ok": False, "data": None, "error": {"code": code, "message": message}}


async def _service(domain: str, service: str, payload: dict) -> dict:
    try:
        async with _client() as client:
            response = await client.post(f"/api/services/{domain}/{service}", json=payload)
        if response.is_error:
            # Do not echo the raw HA body; it may contain private entity metadata.
            return result_error("home_assistant_error", f"Home Assistant returned HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError:
            body = None
        return result_ok({"service": f"{domain}.{service}", "response": body})
    except httpx.TimeoutException:
        return result_error("timeout", "Home Assistant did not respond in time")
    except (httpx.HTTPError, RuntimeError):
        return result_error("connection_error", "Could not connect to Home Assistant; check server configuration")


async def get_state(entity_id: str) -> dict:
    if entity_id not in settings.readonly_entities:
        return result_error("not_allowed", "This entity is not in the read-only allowlist")
    if not entity_id.startswith(("sensor.", "binary_sensor.")):
        return result_error("not_allowed", "Only allowlisted sensors are readable through this tool")
    try:
        async with _client() as client:
            response = await client.get(f"/api/states/{entity_id}")
        if response.status_code == 404:
            return result_error("not_found", "The configured Home Assistant entity was not found")
        if response.is_error:
            return result_error("home_assistant_error", f"Home Assistant returned HTTP {response.status_code}")
        body = response.json()
        # Keep the response small and avoid exposing all attributes by default.
        return result_ok({
            "entity_id": body.get("entity_id"),
            "state": body.get("state"),
            "last_changed": body.get("last_changed"),
            "unit_of_measurement": body.get("attributes", {}).get("unit_of_measurement"),
            "friendly_name": body.get("attributes", {}).get("friendly_name"),
        })
    except httpx.TimeoutException:
        return result_error("timeout", "Home Assistant did not respond in time")
    except (httpx.HTTPError, RuntimeError, ValueError):
        return result_error("connection_error", "Could not retrieve the Home Assistant state")


async def set_light_power(entity_id: str, on: bool) -> dict:
    if entity_id not in settings.allowed_lights:
        return result_error("not_allowed", "This light is not in the allowlist")
    return await _service("light", "turn_on" if on else "turn_off", {"entity_id": entity_id})


async def set_light_brightness(entity_id: str, brightness: int) -> dict:
    if entity_id not in settings.allowed_lights:
        return result_error("not_allowed", "This light is not in the allowlist")
    if not 1 <= brightness <= 255:
        return result_error("invalid_argument", "Brightness must be between 1 and 255")
    return await _service("light", "turn_on", {"entity_id": entity_id, "brightness": brightness})


async def set_light_color(entity_id: str, red: int, green: int, blue: int) -> dict:
    if entity_id not in settings.allowed_lights:
        return result_error("not_allowed", "This light is not in the allowlist")
    if any(channel < 0 or channel > 255 for channel in (red, green, blue)):
        return result_error("invalid_argument", "RGB channels must be between 0 and 255")
    return await _service("light", "turn_on", {"entity_id": entity_id, "rgb_color": [red, green, blue]})


async def set_switch_power(entity_id: str, on: bool) -> dict:
    if entity_id not in settings.allowed_switches:
        return result_error("not_allowed", "This plug is not in the allowlist")
    return await _service("switch", "turn_on" if on else "turn_off", {"entity_id": entity_id})


async def execute_confirmed_automation(automation_id: str) -> dict:
    if automation_id not in settings.allowed_automations:
        return result_error("not_allowed", "This automation is not in the allowlist")
    return await _service("automation", "trigger", {"entity_id": automation_id})
