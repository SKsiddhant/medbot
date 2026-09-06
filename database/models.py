"""
SQLAlchemy models.

Two tables for now:
  * Conversation — one row per user turn (audit trail, required for
    medical compliance).
  * Booking      — persisted appointment.

Migrations: use Alembic. For MVP, `Base.metadata.create_all()` in
database/session.py will bootstrap a SQLite / Postgres schema.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), index=True, nullable=False)
    channel = Column(String(16), nullable=False)          # sms | whatsapp | web
    role = Column(String(16), nullable=False)             # user | bot
    text = Column(Text, nullable=False)
    state = Column(String(32), nullable=True)
    entities_json = Column(Text, nullable=True)           # jsonified NER output
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(String(32), unique=True, index=True, nullable=False)
    user_id = Column(String(64), index=True, nullable=False)
    doctor_id = Column(String(32), nullable=False)
    doctor_name = Column(String(128), nullable=False)
    specialty = Column(String(64), nullable=False)
    clinic = Column(String(256), nullable=False)
    slot = Column(String(64), nullable=False)
    fee_inr = Column(Integer, nullable=False)
    status = Column(String(32), default="PENDING_CONFIRMATION")
    created_at = Column(DateTime, default=datetime.utcnow)


class TriageLog(Base):
    __tablename__ = "triage_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), index=True, nullable=False)
    chief_complaint = Column(String(128), nullable=False)
    symptoms_json = Column(Text, nullable=False)
    urgency = Column(String(32), nullable=False)
    specialty = Column(String(64), nullable=False)
    red_flag = Column(String(64), nullable=True)
    likely_causes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
