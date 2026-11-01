"""Offline tests for the dialogue state machine (the NLP service is stubbed)."""
import asyncio

import pytest

from services import dialogue_manager as dm_mod
from services.dialogue_manager import DialogueManager, State


@pytest.fixture
def dm(monkeypatch):
    async def fake_parse(text):
        return {"symptoms": [text.lower()], "severity": []}

    monkeypatch.setattr(dm_mod.hf_service, "parse_message", fake_parse)
    monkeypatch.setattr(dm_mod, "questions_for", lambda cc: ["Q1?", "Q2?"])
    return DialogueManager()


def say(dm, text, user="u1", channel="sms"):
    return asyncio.run(dm.handle_message(user, text, channel))


def test_greeting_words_do_not_start_triage(dm):
    reply = say(dm, "hello")
    assert "what's bothering you" in reply.text
    assert dm.get_or_create("u1").state == State.GREETING


def test_complaint_starts_cross_questions_in_order(dm):
    reply = say(dm, "mild headache")
    s = dm.get_or_create("u1")
    assert s.state == State.ASK_CROSS_QS and reply.text.endswith("Q1?")
    assert say(dm, "since morning").text == "Q2?"
    assert "Which city" in say(dm, "no").text
    assert s.state == State.ASK_LOCATION
    assert s.answers == ["since morning", "no"]


def test_reset_and_stop_clear_the_session(dm):
    say(dm, "mild headache")
    say(dm, "reset")
    assert dm.get_or_create("u1").state == State.GREETING
    say(dm, "mild headache")
    reply = say(dm, "STOP")
    assert reply.end_of_flow and "unsubscribed" in reply.text


def test_emergency_in_first_message_ends_flow(dm):
    reply = say(dm, "severe chest pain and difficulty breathing")
    assert reply.end_of_flow
    assert dm.get_or_create("u1").state == State.DONE
    assert "complete" in say(dm, "anything").text


def test_booking_flow_and_bad_choice(dm, monkeypatch):
    docs = [{"id": "d1", "name": "Dr. Rao", "specialty": "GP", "clinic": "C", "city": "Pune",
             "next_slot": "10:00", "fee_inr": 300, "rating": 4.5, "phone": "000"}]
    monkeypatch.setattr(dm_mod.doctor_service, "find_nearby", lambda **kw: docs)
    monkeypatch.setattr(dm_mod.doctor_service, "book", lambda doc_id, user_id: {"booking_id": "B1"})
    say(dm, "mild headache"); say(dm, "a"); say(dm, "b")
    reply = say(dm, "pune")
    assert reply.numbered_options == ["BOOK 1"]
    assert dm.get_or_create("u1").state == State.BOOK_CONFIRM
    assert "didn't catch" in say(dm, "book 9").text
    done = say(dm, "book 1")
    assert "B1" in done.text and done.end_of_flow
    assert dm.get_or_create("u1").state == State.DONE
