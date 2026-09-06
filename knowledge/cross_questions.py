"""
Cross-question bank.

Each entry maps a chief-complaint keyword to an ordered list of
follow-up questions. The dialogue manager pops questions off in order
until either:
  * a red-flag rule fires,          or
  * we've asked N questions and can triage.

Questions come from clinical OPQRST/SOCRATES history-taking:
  Onset • Provocation • Quality • Radiation • Severity • Time
"""
from __future__ import annotations


CROSS_QUESTIONS: dict[str, list[str]] = {
    "chest pain": [
        "When did the chest pain start? Was it sudden or gradual?",
        "Can you point to where it hurts? Does the pain move to your arm, jaw, or back?",
        "On a scale of 1 to 10, how bad is it right now?",
        "Are you also sweating, short of breath, or feeling nauseous?",
    ],
    "headache": [
        "When did the headache start, and how long has it lasted?",
        "Is this the worst headache of your life, or similar to ones before?",
        "Do you also have fever, neck stiffness, vision changes, or vomiting?",
        "On a scale of 1 to 10, how severe is it?",
    ],
    "fever": [
        "What is your temperature, and for how many days have you had fever?",
        "Any other symptoms — cough, sore throat, rash, urine burning, loose motions?",
        "Have you travelled recently or been around anyone sick?",
        "Any neck stiffness, confusion, or trouble breathing?",
    ],
    "cough": [
        "How long have you been coughing? Dry or with phlegm?",
        "If phlegm — what colour is it? Any blood?",
        "Do you also have fever, chest pain, or shortness of breath?",
        "Do you smoke, or have asthma / any lung condition?",
    ],
    "shortness of breath": [
        "Did it come on suddenly or slowly?",
        "Does it get worse when you lie flat, walk, or with exertion?",
        "Any chest pain, cough, leg swelling, or wheezing?",
        "On a scale of 1 to 10, how bad is it?",
    ],
    "abdominal pain": [
        "Where in your belly does it hurt — upper, lower, left, right, or all over?",
        "When did it start? Constant or comes in waves?",
        "Any vomiting, diarrhea, fever, or blood in stool?",
        "On a scale of 1 to 10, how bad is it?",
    ],
    "vomiting": [
        "How many times have you vomited in the last 24 hours?",
        "Any blood in the vomit? What colour is it?",
        "Also having diarrhea, fever, or abdominal pain?",
        "Are you able to keep any fluids down?",
    ],
    "diarrhea": [
        "How many loose stools in the last 24 hours?",
        "Any blood or mucus in the stool?",
        "Also having fever, vomiting, or abdominal pain?",
        "Feeling dizzy on standing? (sign of dehydration)",
    ],
    "back pain": [
        "Where exactly — upper, middle, or lower back?",
        "Did it start after an injury or lifting something?",
        "Any weakness or numbness in your legs, or trouble controlling urine?",
        "On a scale of 1 to 10, how bad is it?",
    ],
    "dizziness": [
        "Is the room spinning, or do you feel like you'll faint?",
        "Any hearing loss, ear ringing, or headache?",
        "Does it happen when you stand up quickly, or all the time?",
        "Any chest pain, palpitations, or weakness on one side?",
    ],
}

# Generic fallback if no chief complaint matches
GENERIC_QUESTIONS: list[str] = [
    "When did this start, and has it changed since?",
    "On a scale of 1 to 10, how bothersome is it?",
    "Are there any other symptoms happening at the same time?",
    "Any existing medical conditions, or medicines you take regularly?",
]


import random

def questions_for(chief_complaint: str) -> list[str]:
    cc = chief_complaint.lower().strip()
    if cc in CROSS_QUESTIONS:
        return list(CROSS_QUESTIONS[cc])
    # partial match
    for key, qs in CROSS_QUESTIONS.items():
        if key in cc or cc in key:
            return list(qs)
            
    # if generic, shuffle to avoid asking the exact same every time, and limit to 2
    shuffled = list(GENERIC_QUESTIONS)
    random.shuffle(shuffled)
    return shuffled[:2]


# Specialty routing: chief complaint → best-fit doctor specialty
SPECIALTY_MAP: dict[str, str] = {
    "chest pain": "Cardiology",
    "shortness of breath": "Pulmonology",
    "headache": "Neurology",
    "dizziness": "Neurology",
    "fever": "General Physician",
    "cough": "Pulmonology",
    "abdominal pain": "Gastroenterology",
    "vomiting": "Gastroenterology",
    "diarrhea": "Gastroenterology",
    "back pain": "Orthopedics",
    "rash": "Dermatology",
    "eye pain": "Ophthalmology",
}


def specialty_for(chief_complaint: str) -> str:
    cc = chief_complaint.lower().strip()
    if cc in SPECIALTY_MAP:
        return SPECIALTY_MAP[cc]
    for key, spec in SPECIALTY_MAP.items():
        if key in cc or cc in key:
            return spec
    return "General Physician"
