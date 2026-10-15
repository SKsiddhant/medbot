import sqlite3
import time
import uuid

import pytest

import config
from database.models import Conversation, User
from database.session import get_db
from services import auth


def _name():
    return "u" + uuid.uuid4().hex[:8]


def _signup(client, name=None, password="correct horse"):
    name = name or _name()
    r = client.post("/api/signup", json={"username": name, "password": password})
    return name, r


def _raw_password(name):
    from config import settings
    path = settings.DATABASE_URL.replace("sqlite:///", "")
    return sqlite3.connect(path).execute("select password from users where username=?", (name,)).fetchone()[0]


def test_signup_stores_a_hash_not_the_password(client):
    name, r = _signup(client, password="correct horse")
    assert r.status_code == 200 and r.json()["token"]
    stored = _raw_password(name)
    assert stored != "correct horse" and stored.startswith("scrypt$")


def test_signup_validation_and_duplicates(client):
    assert _signup(client, password="short")[1].status_code == 400
    assert _signup(client, name="ab")[1].status_code == 400
    name, _ = _signup(client)
    assert _signup(client, name=name)[1].status_code == 400


def test_login(client):
    name, _ = _signup(client, password="correct horse")
    ok = client.post("/api/login", json={"username": name, "password": "correct horse"})
    assert ok.status_code == 200 and ok.json()["token"]
    assert client.post("/api/login", json={"username": name, "password": "wrong password"}).status_code == 401
    assert client.post("/api/login", json={"username": "nobody-here", "password": "whatever1"}).status_code == 401


def test_legacy_plaintext_password_is_upgraded_on_first_login(client):
    name = _name()
    with get_db() as db:
        db.add(User(username=name, password="oldplaintext"))
    assert client.post("/api/login", json={"username": name, "password": "nope-nope"}).status_code == 401
    assert client.post("/api/login", json={"username": name, "password": "oldplaintext"}).status_code == 200
    assert _raw_password(name).startswith("scrypt$")
    assert client.post("/api/login", json={"username": name, "password": "oldplaintext"}).status_code == 200


def test_history_requires_the_owners_token(client):
    alice, r = _signup(client)
    bob, rb = _signup(client)
    with get_db() as db:
        db.add(Conversation(user_id=alice, channel="web", role="user", text="private symptom"))
    h = lambda t: {"Authorization": f"Bearer {t}"}

    assert client.get(f"/api/history/{alice}").status_code == 401                               # no credentials
    assert client.get(f"/api/history/{alice}", headers=h("garbage")).status_code == 401
    assert client.get(f"/api/history/{alice}", headers=h(rb.json()["token"])).status_code == 401  # someone else's token
    own = client.get(f"/api/history/{alice}", headers=h(r.json()["token"]))
    assert own.status_code == 200 and own.json()["history"][0]["text"] == "private symptom"


def test_token_tampering_and_expiry():
    tok = auth.make_token("alice")
    assert auth.verify_token(tok) == "alice"
    payload, sig = tok.split(".")
    assert auth.verify_token(payload + "." + "0" * len(sig)) is None
    assert auth.verify_token(None) is None and auth.verify_token("nodot") is None
    real = time.time
    try:
        time.time = lambda: real() + auth.TOKEN_TTL_SECONDS + 5
        assert auth.verify_token(tok) is None
    finally:
        time.time = real


def test_production_refuses_to_sign_without_secret_key(monkeypatch):
    monkeypatch.setattr(config.settings, "SECRET_KEY", "")
    monkeypatch.setattr(config.settings, "APP_ENV", "production")
    with pytest.raises(RuntimeError):
        auth.make_token("alice")
    with pytest.raises(RuntimeError):
        auth.ensure_configured()  # what the app calls on startup


def test_render_style_postgres_url_is_normalised():
    assert config.Settings(DATABASE_URL="postgres://u:p@h/db").DATABASE_URL == "postgresql://u:p@h/db"
    assert config.Settings(DATABASE_URL="sqlite:///x.db").DATABASE_URL == "sqlite:///x.db"


def test_image_endpoint_does_not_claim_to_have_analysed_the_image(client):
    r = client.post("/api/image", data={"user_id": _name()}, files={"image": ("x.png", b"not really an image", "image/png")})
    assert r.status_code == 200
    assert "not analysed" in r.json()["text"] and "Wound detected" not in r.json()["text"]
