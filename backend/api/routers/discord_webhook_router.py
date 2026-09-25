"""Discord Application Webhook Events receiver.

Handles events delivered by Discord to this endpoint when configured at:
discord.com/developers/applications > Webhooks > Events Endpoint URL

Supported event types:
  APPLICATION_AUTHORIZED  — app added to a new guild / user install
  ENTITLEMENT_CREATE      — premium subscription started
  ENTITLEMENT_UPDATE      — premium subscription changed
  ENTITLEMENT_DELETE      — premium subscription ended
"""

from __future__ import annotations

import json
import logging
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from core.config import get_settings

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/discord", tags=["discord-webhook"])

_PING = 0
_EVENT = 1


def _verify_signature(public_key_hex: str, signature_hex: str, timestamp: str, body: bytes) -> bool:
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        public_key.verify(bytes.fromhex(signature_hex), timestamp.encode() + body)
        return True
    except (InvalidSignature, ValueError):
        return False


@router.post("/webhook")
async def discord_webhook(request: Request) -> Response:
    """Receive and verify Discord Application Webhook Events."""
    settings = get_settings()

    if not settings.discord_public_key:
        LOGGER.error("DISCORD_PUBLIC_KEY not configured — rejecting webhook request")
        raise HTTPException(status_code=501, detail="Webhook not configured")

    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")

    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing signature headers")

    body = await request.body()

    if not _verify_signature(settings.discord_public_key, signature, timestamp, body):
        raise HTTPException(status_code=401, detail="Invalid request signature")

    try:
        payload: Any = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    payload_type = payload.get("type")

    if payload_type == _PING:
        LOGGER.info("Discord webhook PING received — endpoint verified")
        return Response(status_code=204, media_type="application/json")

    if payload_type == _EVENT:
        event = payload.get("event")
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise HTTPException(status_code=400, detail="Invalid event payload")

        data = event.get("data", {})
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="Invalid event data")

        event_type = event["type"]
        _dispatch_event(event_type, data)
        return Response(status_code=204, media_type="application/json")

    raise HTTPException(status_code=400, detail="Unsupported webhook type")


def _dispatch_event(event_type: str, data: dict[str, Any]) -> None:
    handlers = {
        "APPLICATION_AUTHORIZED": _on_application_authorized,
        "APPLICATION_DEAUTHORIZED": _on_application_deauthorized,
        "ENTITLEMENT_CREATE": _on_entitlement_create,
        "ENTITLEMENT_UPDATE": _on_entitlement_update,
        "ENTITLEMENT_DELETE": _on_entitlement_delete,
    }
    handler = handlers.get(event_type)
    if handler:
        handler(data)
    else:
        LOGGER.debug("Unhandled Discord webhook event type: %s", event_type)


def _on_application_authorized(data: dict[str, Any]) -> None:
    guild = data.get("guild", {})
    user = data.get("user", {})
    install_type = data.get("integration_type", 0)

    if guild:
        LOGGER.info(
            "App authorized | Guild: %s (%s) | By: %s",
            guild.get("name"),
            guild.get("id"),
            user.get("username"),
        )
    else:
        LOGGER.info(
            "App authorized (user install) | User: %s (%s) | install_type: %s",
            user.get("username"),
            user.get("id"),
            install_type,
        )


def _on_application_deauthorized(data: dict[str, Any]) -> None:
    LOGGER.info(
        "App deauthorized | user: %s (%s)",
        data.get("user", {}).get("username"),
        data.get("user", {}).get("id"),
    )


def _on_entitlement_create(data: dict[str, Any]) -> None:
    LOGGER.info(
        "Entitlement created | id: %s | sku: %s | user: %s | guild: %s",
        data.get("id"),
        data.get("sku_id"),
        data.get("user_id"),
        data.get("guild_id"),
    )


def _on_entitlement_update(data: dict[str, Any]) -> None:
    LOGGER.info(
        "Entitlement updated | id: %s | sku: %s | ends_at: %s",
        data.get("id"),
        data.get("sku_id"),
        data.get("ends_at"),
    )


def _on_entitlement_delete(data: dict[str, Any]) -> None:
    LOGGER.info(
        "Entitlement deleted | id: %s | sku: %s | user: %s",
        data.get("id"),
        data.get("sku_id"),
        data.get("user_id"),
    )
