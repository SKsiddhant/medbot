"""
Red-flag rules.

These are hard-coded, conservative rules. If a rule fires we short-circuit
the state machine and tell the user to call 112 / go to ER immediately.
Never rely on the LLM alone for this — LLMs miss and hallucinate.

Format: each rule has a name, a matcher (all keywords must be present
somewhere in the accumulated symptom set), and a message.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RedFlagRule:
    name: str
    must_have: list[str]         # ALL of these terms must appear
    any_of: list[str] = field(default_factory=list)  # AT LEAST ONE if provided
    urgency: str = "EMERGENCY"   # EMERGENCY | URGENT
    specialty: str = "Emergency"
    message: str = ""


RED_FLAGS: list[RedFlagRule] = [
    RedFlagRule(
        name="cardiac_event",
        must_have=["chest pain"],
        any_of=["arm", "jaw", "sweating", "shortness of breath", "left"],
        specialty="Cardiology / ER",
        message=(
            "🚨 Chest pain with these features can indicate a heart attack. "
            "Please call 112 or go to the nearest emergency room NOW. "
            "Do not drive yourself."
        ),
    ),
    RedFlagRule(
        name="stroke",
        must_have=[],
        any_of=[
            "face drooping", "slurred speech", "sudden weakness",
            "arm weakness", "vision loss", "sudden confusion",
        ],
        specialty="Neurology / ER",
        message=(
            "🚨 These are stroke warning signs (FAST test). "
            "Every minute matters. Call 112 immediately."
        ),
    ),
    RedFlagRule(
        name="meningitis",
        must_have=["fever"],
        any_of=["neck stiffness", "stiff neck", "photophobia", "rash"],
        specialty="Emergency",
        message=(
            "🚨 Fever with neck stiffness can indicate meningitis. "
            "Go to the ER now — this needs urgent treatment."
        ),
    ),
    RedFlagRule(
        name="anaphylaxis",
        must_have=[],
        any_of=[
            "difficulty breathing", "swelling face", "swelling throat",
            "swelling tongue", "hives all over",
        ],
        specialty="Emergency",
        message=(
            "🚨 Possible severe allergic reaction. "
            "If you have an EpiPen use it now, then call 112."
        ),
    ),
    RedFlagRule(
        name="severe_bleeding",
        must_have=[],
        any_of=[
            "heavy bleeding", "vomiting blood", "coughing blood",
            "blood in stool", "black stool",
        ],
        specialty="Emergency",
        message=(
            "🚨 Signs of severe internal or external bleeding. "
            "Call 112 immediately."
        ),
    ),
    RedFlagRule(
        name="suicidal_ideation",
        must_have=[],
        any_of=["kill myself", "end my life", "suicide", "want to die"],
        specialty="Mental Health Crisis",
        message=(
            "I'm really glad you told me. You are not alone. "
            "Please call iCall India on 9152987821 or Vandrevala Foundation "
            "on 1860-2662-345 right now — they will listen 24/7."
        ),
    ),
    RedFlagRule(
        name="pregnancy_emergency",
        must_have=["pregnant"],
        any_of=["bleeding", "severe pain", "no fetal movement"],
        specialty="Obstetrics ER",
        message=(
            "🚨 Bleeding or severe pain in pregnancy needs immediate care. "
            "Go to your maternity hospital or call 102 now."
        ),
    ),
]


def check_red_flags(symptoms: list[str], full_text: str = "") -> RedFlagRule | None:
    """Return the first matching rule, or None."""
    haystack = " ".join(symptoms + [full_text.lower()])
    for rule in RED_FLAGS:
        if all(term in haystack for term in rule.must_have):
            if rule.any_of and not any(term in haystack for term in rule.any_of):
                continue
            if not rule.must_have and not any(term in haystack for term in rule.any_of):
                continue
            return rule
    return None
