"""
Doctor service.

Responsibilities:
  * Load the doctor directory (knowledge/doctors.json for MVP,
    Practo / Lybrate API once you have partnership).
  * Filter by specialty + city, sort by distance if we have coordinates.
  * Book an appointment (mock for MVP; returns a booking id + slot).

Swap `_load_doctors` and `book` to hit Practo when you have API keys.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any

from haversine import haversine

DOCTORS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "knowledge",
    "doctors.json",
)


class DoctorService:
    def __init__(self) -> None:
        self._doctors: list[dict[str, Any]] = self._load_doctors()
        self._bookings: dict[str, dict[str, Any]] = {}   # in-memory MVP

    def _load_doctors(self) -> list[dict[str, Any]]:
        with open(DOCTORS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def find_nearby(
        self,
        specialty: str,
        city: str = "",
        user_lat: float | None = None,
        user_lng: float | None = None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Return up to `limit` doctors matching the specialty.

        City-based match first (fastest for text-based conversation).
        If lat/lng supplied, sort by haversine distance.
        """
        # Specialty match (exact or contains)
        spec_l = specialty.lower()
        candidates = [
            dict(d) for d in self._doctors
            if spec_l in d["specialty"].lower()
            or d["specialty"].lower() in spec_l
        ]

        # City filter (case-insensitive, permissive)
        if city:
            city_l = city.lower()
            in_city = [d for d in candidates if d["city"].lower() == city_l]
            if in_city:
                candidates = in_city
            # else: fall back to all cities

        # If we don't have specialty match, widen to General Physician
        if not candidates:
            candidates = [
                dict(d) for d in self._doctors
                if d["specialty"] == "General Physician"
                and (not city or d["city"].lower() == city.lower())
            ]

        # Distance sort if coordinates given
        if user_lat is not None and user_lng is not None:
            for d in candidates:
                d["distance_km"] = round(
                    haversine((user_lat, user_lng), (d["lat"], d["lng"])), 1
                )
            candidates.sort(key=lambda d: d["distance_km"])
        else:
            # Sort by rating desc
            candidates.sort(key=lambda d: d.get("rating", 0), reverse=True)

        return candidates[:limit]

    # ------------------------------------------------------------------
    # Booking (mock)
    # ------------------------------------------------------------------
    def book(self, doctor_id: str, user_id: str) -> dict[str, Any]:
        doc = next((d for d in self._doctors if d["id"] == doctor_id), None)
        if not doc:
            raise ValueError(f"No such doctor: {doctor_id}")
        booking_id = f"MB-{uuid.uuid4().hex[:8].upper()}"
        booking = {
            "booking_id": booking_id,
            "doctor_id": doctor_id,
            "doctor_name": doc["name"],
            "user_id": user_id,
            "slot": doc["next_slot"],
            "clinic": doc["clinic"],
            "phone": doc["phone"],
            "fee_inr": doc["fee_inr"],
            "created_at": datetime.utcnow().isoformat(),
            "status": "PENDING_CONFIRMATION",
        }
        self._bookings[booking_id] = booking
        return booking

    def get_booking(self, booking_id: str) -> dict[str, Any] | None:
        return self._bookings.get(booking_id)


doctor_service = DoctorService()
