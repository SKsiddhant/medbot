from services.triage_engine import triage


def test_red_flag_wins_and_does_not_book_doctor():
    r = triage("chest pain", {"symptoms": ["chest pain"], "severity": ["mild"]},
               "I have chest pain spreading to my left arm and I am sweating")
    assert r.urgency == "EMERGENCY"
    assert r.should_book_doctor is False
    assert r.red_flag_name == "cardiac_event"


def test_severe_is_urgent_within_24h():
    r = triage("headache", {"symptoms": ["headache"], "severity": ["severe"]}, "severe headache")
    assert r.urgency in ("URGENT_24H", "EMERGENCY")


def test_mild_is_self_care_and_not_booked():
    r = triage("sore throat", {"symptoms": ["sore throat"], "severity": ["mild"]}, "mild sore throat")
    assert r.urgency == "SELF_CARE"
    assert r.should_book_doctor is False
    assert "viral pharyngitis" in r.likely_causes


def test_no_severity_defaults_to_routine_with_causes_capped():
    r = triage("fever", {"symptoms": ["fever"]}, "fever since yesterday")
    assert r.urgency == "ROUTINE"
    assert 0 < len(r.likely_causes) <= 5
    assert r.should_book_doctor is True


def test_empty_parse_falls_back_to_chief_complaint():
    r = triage("Fever", {}, "")
    assert r.likely_causes
