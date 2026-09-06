"""
WhatsApp transport via the Meta WhatsApp Cloud API.

Setup summary (do this OUTSIDE the app):
  1. Create a Meta Business account.
  2. Add a WhatsApp Business Account (WABA).
  3. Get a permanent access token + phone_number_id.
  4. Configure webhook: your public URL /webhook/whatsapp
     verify_token: whatever you set in META_VERIFY_TOKEN.
  5. Subscribe to `messages` webhook events.

Meta approval for health/medical bots is stricter — plan 1-4 weeks.
While waiting, use the SMS channel (it works today).
"""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from config import settings

GRAPH_API_BASE = "https://graph.facebook.com/v20.0"


class WhatsAppService:
    def __init__(self) -> None:
        self.token = settings.META_WHATSAPP_TOKEN
        self.phone_id = settings.META_PHONE_NUMBER_ID
        self.verify_token = settings.META_VERIFY_TOKEN
        self.enabled = bool(self.token and self.phone_id)
        if not self.enabled:
            logger.warning(
                "WhatsApp Cloud API disabled — "
                "set META_WHATSAPP_TOKEN and META_PHONE_NUMBER_ID."
            )

    # ------------------------------------------------------------------
    # Webhook verification (GET /webhook/whatsapp)
    # Meta calls this once when you register the webhook.
    # ------------------------------------------------------------------
    def verify_webhook(
        self,
        mode: str | None,
        token: str | None,
        challenge: str | None,
    ) -> str | None:
        if mode == "subscribe" and token == self.verify_token and challenge:
            logger.info("WhatsApp webhook verified.")
            return challenge
        return None

    # ------------------------------------------------------------------
    # Parse incoming webhook payload
    # Meta sends nested JSON; we pull out (from, text).
    # ------------------------------------------------------------------
    @staticmethod
    def parse_incoming(payload: dict[str, Any]) -> tuple[str, str] | None:
        try:
            entry = payload["entry"][0]["changes"][0]["value"]
            msg = entry["messages"][0]
            from_number = msg["from"]                # e.g. "919812345678"
            if msg.get("type") == "text":
                text = msg["text"]["body"]
            elif msg.get("type") == "interactive":
                # Button reply — from quick_replies
                text = (
                    msg["interactive"].get("button_reply", {}).get("title")
                    or msg["interactive"].get("list_reply", {}).get("title")
                    or ""
                )
            else:
                text = ""
            return from_number, text
        except (KeyError, IndexError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Outbound — plain text
    # ------------------------------------------------------------------
    async def send_text(self, to_number: str, body: str) -> dict[str, Any] | None:
        if not self.enabled:
            logger.warning(f"WA not sent: {to_number} :: {body[:60]}")
            return None
        url = f"{GRAPH_API_BASE}/{self.phone_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": body[:4096]},
        }
        return await self._post(url, payload)

    # ------------------------------------------------------------------
    # Outbound — with quick-reply buttons (max 3)
    # ------------------------------------------------------------------
    async def send_with_buttons(
        self,
        to_number: str,
        body: str,
        buttons: list[str],
    ) -> dict[str, Any] | None:
        if not self.enabled:
            logger.warning(f"WA not sent: {to_number} :: {body[:60]}")
            return None
        url = f"{GRAPH_API_BASE}/{self.phone_id}/messages"
        wa_buttons = [
            {
                "type": "reply",
                "reply": {"id": f"btn_{i}", "title": btn[:20]},   # 20-char limit
            }
            for i, btn in enumerate(buttons[:3])
        ]
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body[:1024]},
                "action": {"buttons": wa_buttons},
            },
        }
        return await self._post(url, payload)

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                return r.json()
        except Exception as e:
            logger.error(f"WhatsApp send error: {e}")
            return None


whatsapp_service = WhatsAppService()
