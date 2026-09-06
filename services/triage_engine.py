"""
Triage engine.

Consumes the parsed NER output + accumulated conversation state and
returns a triage decision:

  urgency: EMERGENCY | URGENT_24H | ROUTINE | SELF_CARE
  specialty: Cardiology / Neurology / General Physician / ...
  likely_causes: list[str]         (framed as possibilities, never diagnostic)
  advice: str                      (user-facing plain text)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from knowledge.red_flags import check_red_flags
from knowledge.cross_questions import specialty_for


Urgency = Literal["EMERGENCY", "URGENT_24H", "ROUTINE", "SELF_CARE"]


@dataclass
class TriageResult:
    urgency: Urgency
    specialty: str
    likely_causes: list[str] = field(default_factory=list)
    red_flag_name: str | None = None
    advice: str = ""
    should_book_doctor: bool = True


# Lightweight symptom → possible-cause map.
# We word these as "possible causes", never diagnoses.
CAUSE_MAP: dict[str, list[str]] = {
    "fever": ["viral infection", "flu", "urinary tract infection", "typhoid", "malaria"],
    "cough": ["common cold", "bronchitis", "asthma flare-up", "COVID-19"],
    "headache": ["tension headache", "migraine", "dehydration", "sinusitis"],
    "chest pain": ["muscle strain", "acid reflux", "anxiety", "cardiac cause"],
    "abdominal pain": ["gastritis", "food poisoning", "IBS", "appendicitis"],
    "vomiting": ["gastroenteritis", "food poisoning", "migraine"],
    "diarrhea": ["gastroenteritis", "food poisoning", "IBS"],
    "back pain": ["muscle strain", "poor posture", "disc issue"],
    "shortness of breath": ["asthma", "anxiety", "chest infection", "cardiac cause"],
    "dizziness": ["low blood pressure", "inner-ear issue", "dehydration", "anemia"],
    "rash": ["allergic reaction", "eczema", "viral rash"],
    "sore throat": ["viral pharyngitis", "strep throat", "post-nasal drip"],
}


def _causes_for(symptoms: list[str]) -> list[str]:
    out: list[str] = []
    for s in symptoms:
        for key, causes in CAUSE_MAP.items():
            if key in s or s in key:
                out.extend(causes)
                break
    # de-dupe preserving order
    seen: set[str] = set()
    return [c for c in out if not (c in seen or seen.add(c))][:5]


def _severity_to_urgency(severity_tokens: list[str], symptoms: list[str]) -> Urgency:
    text = " ".join(severity_tokens + symptoms).lower()
    if any(w in text for w in ["severe", "unbearable", "worst", "10/10"]):
        return "URGENT_24H"
    if any(w in text for w in ["mild", "slight", "little"]):
        return "SELF_CARE"
    return "ROUTINE"


def triage(
    chief_complaint: str,
    parsed: dict[str, list[str]],
    full_conversation_text: str = "",
) -> TriageResult:
    """Main entry point. Feed it the chief complaint + parsed message +
    the concatenation of every user message so far."""
    symptoms = parsed.get("symptoms", []) or [chief_complaint.lower()]
    severity = parsed.get("severity", [])

    # 1. Red-flag check — always first, always wins.
    rule = check_red_flags(symptoms, full_conversation_text)
    if rule is not None:
        return TriageResult(
            urgency="EMERGENCY",
            specialty=rule.specialty,
            likely_causes=[],
            red_flag_name=rule.name,
            advice=rule.message,
            should_book_doctor=False,   # we tell them to call 112, not book
        )

    # 2. Severity → urgency
    urgency = _severity_to_urgency(severity, symptoms)

    # 3. Specialty
    specialty = specialty_for(chief_complaint)

    # 4. Possible causes
    causes = _causes_for(symptoms)

    # 5. Advice text
    advice = _advice_for(urgency, specialty, causes)

    return TriageResult(
        urgency=urgency,
        specialty=specialty,
        likely_causes=causes,
        advice=advice,
        should_book_doctor=urgency in ("URGENT_24H", "ROUTINE"),
    )


def _advice_for(urgency: Urgency, specialty: str, causes: list[str]) -> str:
    causes_line = (
        f"Possible causes to discuss with a doctor: {', '.join(causes)}."
        if causes else ""
    )
    if urgency == "URGENT_24H":
        return (
            f"Your symptoms sound significant. I recommend seeing a "
            f"{specialty} within the next 24 hours. {causes_line}"
        )
    if urgency == "ROUTINE":
        return (
            f"This can usually wait for a routine visit. Booking a "
            f"{specialty} in the next few days is a good idea. {causes_line}"
        )
    if urgency == "SELF_CARE":
        return (
            f"This sounds mild. Try rest, fluids and monitor for 24-48 hours. "
            f"If it gets worse, book a {specialty}. {causes_line}"
        )
    return causes_line
