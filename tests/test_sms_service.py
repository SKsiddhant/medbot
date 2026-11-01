"""SMS TwiML builder: the no-SDK fallback must emit well-formed XML."""
import xml.etree.ElementTree as ET

from services import sms_service as mod


def test_fallback_twiml_escapes_ampersand_and_angle_brackets(monkeypatch):
    monkeypatch.setattr(mod, "TWILIO_AVAILABLE", False)
    xml = mod.SMSService().build_twiml_reply("Fever & cough <3 days", ["1. Yes", "2. No"])
    msg = ET.fromstring(xml).find("Message").text
    assert "Fever & cough <3 days" in msg and "2. No" in msg


def test_reply_is_truncated_to_sms_limit(monkeypatch):
    monkeypatch.setattr(mod, "TWILIO_AVAILABLE", False)
    xml = mod.SMSService().build_twiml_reply("x" * 3000)
    assert len(ET.fromstring(xml).find("Message").text) <= 1500
