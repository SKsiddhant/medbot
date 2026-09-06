"""
SMS transport via Twilio.

Why Twilio for SMS?
  * Works globally, sandbox-free for outbound in most countries.
  * India (DLT) requires template registration for A2P — for the MVP,
    2-way conversational SMS via a Twilio long-code is fine.

Webhook flow:
  Twilio POSTs form-encoded x-www-form-urlencoded to /webhook/sms:
    { From: "+919812345678", Body: "fever for 2 days", ... }
  We reply with TwiML  <Response><Message>...</Message></Response>
  which Twilio sends back to the user as SMS.

Outbound (proactive) send uses the REST API — not needed for
request/reply, but wired in below for completeness.
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from config import settings


try:
    from twilio.rest import Client
    from twilio.twiml.messaging_response import MessagingResponse
    TWILIO_AVAILABLE = True
except ImportError:                             # pragma: no cover
    TWILIO_AVAILABLE = False
    Client = None                               # type: ignore
    MessagingResponse = None                    # type: ignore


class SMSService:
    def __init__(self) -> None:
        self.enabled = bool(
            TWILIO_AVAILABLE
            and settings.TWILIO_ACCOUNT_SID
            and settings.TWILIO_AUTH_TOKEN
        )
        self._client = None
        if self.enabled:
            self._client = Client(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN,
            )
            logger.info("Twilio SMS client initialised.")
        else:
            logger.warning(
                "Twilio SMS disabled — set TWILIO_ACCOUNT_SID / AUTH_TOKEN."
            )

    # ------------------------------------------------------------------
    # Inbound → build TwiML response
    # ------------------------------------------------------------------
    def build_twiml_reply(
        self,
        body: str,
        numbered_options: list[str] | None = None,
    ) -> str:
        """Return a TwiML XML string that Twilio will send as SMS."""
        # SMS has no rich cards; append numbered options as a footer.
        full = body
        if numbered_options:
            full += "\n\n" + "\n".join(numbered_options)
        # SMS length is 1600 chars max; truncate defensively.
        if len(full) > 1500:
            full = full[:1497] + "..."

        if TWILIO_AVAILABLE:
            resp = MessagingResponse()
            resp.message(full)
            return str(resp)

        # Fallback if Twilio SDK isn't installed
        safe = full.replace("<", "&lt;").replace(">", "&gt;")
        return f"<Response><Message>{safe}</Message></Response>"

    # ------------------------------------------------------------------
    # Outbound (proactive / follow-up messages)
    # ------------------------------------------------------------------
    def send(self, to_number: str, body: str) -> dict[str, Any] | None:
        if not self.enabled or self._client is None:
            logger.warning(f"SMS not sent (Twilio disabled): {to_number} :: {body[:60]}")
            return None
        msg = self._client.messages.create(
            body=body[:1500],
            from_=settings.TWILIO_SMS_FROM,
            to=to_number,
        )
        return {"sid": msg.sid, "status": msg.status}


sms_service = SMSService()
