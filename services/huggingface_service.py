"""
Hugging Face service.

Two modes:
  1. USE_HF_INFERENCE_API=true  →  call the hosted Inference API over HTTPS
                                    (no GPU, works on Render/Railway free tier).
  2. USE_HF_INFERENCE_API=false →  load the model locally with `transformers`
                                    (needs GPU or a fat CPU box).

Model:  d4data/biomedical-ner-all   — a fine-tuned DistilBERT that tags
        symptoms, diseases, drugs, body parts, severity, duration, etc.
"""
from __future__ import annotations

import re
from typing import Any

import httpx
from loguru import logger

from config import settings


HF_INFERENCE_URL = "https://api-inference.huggingface.co/models/{model}"

# entity_group labels we care about from biomedical-ner-all
SYMPTOM_LABELS = {"Sign_symptom", "Detailed_description", "Disease_disorder"}
BODY_PART_LABELS = {"Biological_structure"}
SEVERITY_LABELS = {"Severity"}
DURATION_LABELS = {"Duration", "Frequency"}


class HuggingFaceService:
    def __init__(self) -> None:
        self.token = settings.HF_API_TOKEN
        self.ner_model = settings.HF_NER_MODEL
        self.use_api = settings.USE_HF_INFERENCE_API
        self._local_pipe = None  # lazy-loaded transformers pipeline

        if not self.use_api:
            self._load_local_pipeline()

    # ------------------------------------------------------------------
    # Local pipeline (transformers)
    # ------------------------------------------------------------------
    def _load_local_pipeline(self) -> None:
        try:
            from transformers import pipeline  # heavy import — lazy
            logger.info(f"Loading local NER model: {self.ner_model}")
            self._local_pipe = pipeline(
                "ner",
                model=self.ner_model,
                aggregation_strategy="simple",
            )
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to load local model, falling back to API: {e}")
            self.use_api = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def extract_entities(self, text: str) -> list[dict[str, Any]]:
        """Run biomedical NER on the user message. Returns a list of
        {word, entity_group, score, start, end} dicts."""
        if not text or len(text.strip()) < 2:
            return []

        if self.use_api:
            return await self._call_inference_api(text)
        return self._call_local(text)

    async def _call_inference_api(self, text: str) -> list[dict[str, Any]]:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        url = HF_INFERENCE_URL.format(model=self.ner_model)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(url, headers=headers, json={"inputs": text})
                r.raise_for_status()
                data = r.json()
                # HF returns a warm-up dict on first call
                if isinstance(data, dict) and "error" in data:
                    logger.warning(f"HF API: {data.get('error')}")
                    return []
                return data
        except Exception as e:
            logger.error(f"HF inference API error: {e}")
            return []

    def _call_local(self, text: str) -> list[dict[str, Any]]:
        if self._local_pipe is None:
            return []
        return self._local_pipe(text)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Convenience wrappers used by DialogueManager / TriageEngine
    # ------------------------------------------------------------------
    async def parse_message(self, text: str) -> dict[str, list[str]]:
        """Return a structured view: symptoms, body_parts, severity, duration."""
        ents = await self.extract_entities(text)
        result = {
            "symptoms": [],
            "body_parts": [],
            "severity": [],
            "duration": [],
            "raw": ents,
        }
        for e in ents:
            group = e.get("entity_group") or e.get("entity", "")
            word = e.get("word", "").strip().lower()
            if not word:
                continue
            if group in SYMPTOM_LABELS:
                result["symptoms"].append(word)
            elif group in BODY_PART_LABELS:
                result["body_parts"].append(word)
            elif group in SEVERITY_LABELS:
                result["severity"].append(word)
            elif group in DURATION_LABELS:
                result["duration"].append(word)

        # de-dupe, keep order
        for k in ("symptoms", "body_parts", "severity", "duration"):
            seen: set[str] = set()
            result[k] = [x for x in result[k] if not (x in seen or seen.add(x))]

        # crude fallback: if NER found nothing, try keyword match
        if not result["symptoms"]:
            result["symptoms"] = self._keyword_fallback(text)

        return result

    _KEYWORDS = [
        "fever", "headache", "cough", "chest pain", "shortness of breath",
        "vomiting", "nausea", "diarrhea", "rash", "dizziness", "fatigue",
        "sore throat", "runny nose", "back pain", "abdominal pain",
        "chills", "body ache", "loss of smell", "loss of taste",
    ]

    def _keyword_fallback(self, text: str) -> list[str]:
        t = text.lower()
        return [k for k in self._KEYWORDS if re.search(rf"\b{re.escape(k)}\b", t)]


# module-level singleton
hf_service = HuggingFaceService()
