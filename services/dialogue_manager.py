"""
Dialogue manager (state machine).

We deliberately use a state machine, not free-form LLM generation.
Reason: LLM cross-questioning drifts, misses red flags, and can't be audited.
The states are small and legible.

States:
  GREETING          → asks for chief complaint
  ASK_CROSS_QS      → asks N follow-up questions from cross_questions.py
  ASK_LOCATION      → asks user's city or shares-location
  SHOW_TRIAGE       → returns triage decision + doctor list
  BOOK_CONFIRM      → user picks a doctor, we confirm booking
  DONE              → conversation closed
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

from loguru import logger

from services.huggingface_service import hf_service
from services.triage_engine import triage, TriageResult
from services.doctor_service import doctor_service
from knowledge.cross_questions import questions_for
from config import settings


class State(str, Enum):
    GREETING = "GREETING"
    ASK_CROSS_QS = "ASK_CROSS_QS"
    ASK_LOCATION = "ASK_LOCATION"
    SHOW_TRIAGE = "SHOW_TRIAGE"
    BOOK_CONFIRM = "BOOK_CONFIRM"
    DONE = "DONE"


@dataclass
class Session:
    user_id: str                                        # phone number or web-session id
    state: State = State.GREETING
    channel: str = "sms"                                # sms | whatsapp | web
    chief_complaint: str = ""
    cross_questions: list[str] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)
    all_symptoms: list[str] = field(default_factory=list)
    full_text: str = ""                                 # concatenation of user turns
    city: str = ""
    triage_result: dict[str, Any] | None = None
    doctor_options: list[dict[str, Any]] = field(default_factory=list)
    booked_doctor: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Session":
        d = dict(d)
        d["state"] = State(d.get("state", "GREETING"))
        return cls(**d)


# ----------------------------------------------------------------------
# Reply object — the manager returns this, transport layers render it.
# ----------------------------------------------------------------------
@dataclass
class BotReply:
    text: str                                           # main message
    quick_replies: list[str] = field(default_factory=list)   # WhatsApp buttons
    numbered_options: list[str] = field(default_factory=list) # SMS numbered list
    end_of_flow: bool = False


class DialogueManager:
    """Owns session state + drives the state machine."""

    def __init__(self) -> None:
        # In-memory store; production wires this to Redis via session_store.
        self._sessions: dict[str, Session] = {}

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------
    def get_or_create(self, user_id: str, channel: str = "sms") -> Session:
        if user_id not in self._sessions:
            self._sessions[user_id] = Session(user_id=user_id, channel=channel)
        return self._sessions[user_id]

    def reset(self, user_id: str) -> None:
        self._sessions.pop(user_id, None)

    # ------------------------------------------------------------------
    # Main entrypoint
    # ------------------------------------------------------------------
    async def handle_message(
        self,
        user_id: str,
        text: str,
        channel: str = "sms",
    ) -> BotReply:
        text = (text or "").strip()
        session = self.get_or_create(user_id, channel)
        session.channel = channel
        session.full_text += " " + text.lower()

        # Global commands
        low = text.lower()
        if low in {"reset", "restart", "start over"}:
            self.reset(user_id)
            return BotReply(text=self._greeting())
        if low in {"stop", "unsubscribe"}:
            self.reset(user_id)
            return BotReply(
                text="You've been unsubscribed. Reply START anytime to use SWASTHYA AI again.",
                end_of_flow=True,
            )

        # State dispatch
        handler = {
            State.GREETING: self._on_greeting,
            State.ASK_CROSS_QS: self._on_cross_qs,
            State.ASK_LOCATION: self._on_location,
            State.SHOW_TRIAGE: self._on_show_triage,
            State.BOOK_CONFIRM: self._on_book_confirm,
            State.DONE: self._on_done,
        }[session.state]
        try:
            return await handler(session, text)
        except Exception as e:
            logger.exception(f"Dialogue error: {e}")
            return BotReply(
                text="Sorry, something went wrong on my side. Reply RESET to start over.",
            )

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------
    def _greeting(self) -> str:
        return (
            "👋 Hi, I'm SWASTHYA AI - an AI triage assistant.\n\n"
            f"{settings.DISCLAIMER}\n\n"
            "In one line, what's bothering you today? (e.g. 'fever and cough for 2 days')"
        )

    async def _on_greeting(self, session: Session, text: str) -> BotReply:
        if not text:
            return BotReply(text=self._greeting())

        # Empty-ish → send greeting
        if text.lower() in {"hi", "hello", "start", "hey"}:
            return BotReply(text=self._greeting())

        # Parse the chief complaint
        parsed = await hf_service.parse_message(text)
        symptoms = parsed["symptoms"] or [text.lower()]
        session.chief_complaint = symptoms[0]
        session.all_symptoms.extend(symptoms)

        # CRITICAL: run red-flag check on the very first message too
        early_triage = triage(
            chief_complaint=session.chief_complaint,
            parsed={"symptoms": session.all_symptoms, "severity": parsed["severity"]},
            full_conversation_text=session.full_text,
        )
        if early_triage.urgency == "EMERGENCY":
            session.triage_result = asdict(early_triage)
            session.state = State.DONE
            return BotReply(
                text=f"{early_triage.advice}\n\nSpecialty needed: {early_triage.specialty}",
                end_of_flow=True,
            )

        session.cross_questions = questions_for(session.chief_complaint)
        session.state = State.ASK_CROSS_QS

        first_q = session.cross_questions.pop(0)
        session.answers.append("")   # placeholder; filled on next reply
        return BotReply(
            text=f"Got it — you mentioned *{session.chief_complaint}*. "
                 f"A few quick questions.\n\n{first_q}",
        )

    async def _on_cross_qs(self, session: Session, text: str) -> BotReply:
        # Store the user's answer to the previous question
        parsed = await hf_service.parse_message(text)
        session.all_symptoms.extend(parsed["symptoms"])
        session.answers[-1] = text

        # After each answer, check for red flags on cumulative text
        result = triage(
            chief_complaint=session.chief_complaint,
            parsed={"symptoms": session.all_symptoms, "severity": parsed["severity"]},
            full_conversation_text=session.full_text,
        )
        if result.urgency == "EMERGENCY":
            session.triage_result = asdict(result)
            session.state = State.DONE
            return BotReply(
                text=f"{result.advice}\n\nSpecialty needed: {result.specialty}",
                end_of_flow=True,
            )

        # Ask next question if any remain
        if session.cross_questions:
            next_q = session.cross_questions.pop(0)
            session.answers.append("")
            return BotReply(text=next_q)

        # No more questions → ask location
        session.state = State.ASK_LOCATION
        return BotReply(
            text="Thanks. Which city are you in? "
                 "(so I can suggest nearby doctors)",
        )

    async def _on_location(self, session: Session, text: str) -> BotReply:
        session.city = text.strip().title()
        session.state = State.SHOW_TRIAGE
        return await self._render_triage(session)

    async def _render_triage(self, session: Session) -> BotReply:
        parsed = {"symptoms": session.all_symptoms, "severity": []}
        result = triage(
            session.chief_complaint,
            parsed,
            session.full_text,
        )
        session.triage_result = asdict(result)

        # Fetch doctors
        docs = doctor_service.find_nearby(
            specialty=result.specialty,
            city=session.city,
            limit=3,
        )
        session.doctor_options = docs

        # Build reply text
        lines = [
            f"📋 *Triage summary*",
            f"• Urgency: *{result.urgency.replace('_', ' ').title()}*",
            f"• Suggested specialty: *{result.specialty}*",
        ]
        if result.likely_causes:
            lines.append(
                f"• Possible causes to discuss: {', '.join(result.likely_causes)}"
            )
        lines.append("")
        lines.append(result.advice)

        if docs:
            lines.append("\n👩‍⚕️ *Doctors near you:*")
            for i, d in enumerate(docs, start=1):
                lines.append(
                    f"{i}. *{d['name']}* — {d['specialty']}\n"
                    f"   {d['clinic']}, {d['city']}\n"
                    f"   Next slot: {d['next_slot']} • ₹{d['fee_inr']} • ⭐ {d['rating']}"
                )
            if session.channel == "sms":
                lines.append("\nReply BOOK 1, BOOK 2 or BOOK 3 to book.")
                session.state = State.BOOK_CONFIRM
                return BotReply(
                    text="\n".join(lines),
                    numbered_options=[f"BOOK {i+1}" for i in range(len(docs))],
                )
            else:
                session.state = State.BOOK_CONFIRM
                return BotReply(
                    text="\n".join(lines),
                    quick_replies=[f"Book {d['name'].split()[-1]}" for d in docs],
                )
        else:
            session.state = State.DONE
            return BotReply(text="\n".join(lines), end_of_flow=True)

    async def _on_book_confirm(self, session: Session, text: str) -> BotReply:
        low = text.lower().strip()
        idx: int | None = None

        # Parse "BOOK 1" / "1" / "book dr sharma"
        if low.startswith("book"):
            rest = low.replace("book", "").strip()
            if rest.isdigit():
                idx = int(rest) - 1
            else:
                # match by surname
                for i, d in enumerate(session.doctor_options):
                    if rest and rest in d["name"].lower():
                        idx = i
                        break
        elif low.isdigit():
            idx = int(low) - 1

        if idx is None or idx < 0 or idx >= len(session.doctor_options):
            return BotReply(
                text="I didn't catch which doctor. Reply with BOOK 1, BOOK 2 or BOOK 3.",
            )

        doc = session.doctor_options[idx]
        booking = doctor_service.book(doc["id"], user_id=session.user_id)
        session.booked_doctor = booking
        session.state = State.DONE

        return BotReply(
            text=(
                f"✅ *Booked!*\n\n"
                f"Dr. {doc['name'].replace('Dr. ', '')} — {doc['specialty']}\n"
                f"📍 {doc['clinic']}, {doc['city']}\n"
                f"🗓️ {doc['next_slot']}\n"
                f"💳 ₹{doc['fee_inr']}\n"
                f"📞 {doc['phone']}\n\n"
                f"Booking ID: *{booking['booking_id']}*\n\n"
                f"The clinic will call you to confirm. "
                f"Reply RESET to start a new consultation."
            ),
            end_of_flow=True,
        )

    async def _on_show_triage(self, session: Session, text: str) -> BotReply:
        return await self._render_triage(session)

    async def _on_done(self, session: Session, text: str) -> BotReply:
        return BotReply(
            text="This consultation is complete. Reply RESET to start a new one.",
            end_of_flow=True,
        )


# module-level singleton
dialogue_manager = DialogueManager()
