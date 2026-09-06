"""
MedBot — FastAPI entrypoint.

Routes:
  GET  /                       — healthcheck
  POST /webhook/sms            — Twilio SMS webhook (must return TwiML)
  POST /webhook/whatsapp       — Meta WhatsApp Cloud API webhook
  GET  /webhook/whatsapp       — Meta webhook verification handshake
  POST /api/chat               — REST endpoint used by the web prototype
  POST /api/reset              — reset a session (dev only)

Run:
  uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Form, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel

from config import settings
from database.session import init_db
from services.dialogue_manager import dialogue_manager
from services.sms_service import sms_service
from services.whatsapp_service import whatsapp_service
from services.voice_service import voice_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting MedBot ({settings.APP_ENV})")
    try:
        init_db()
    except Exception as e:
        logger.warning(f"DB init failed (ok for dev): {e}")
    yield
    logger.info("Shutting down MedBot")


app = FastAPI(title="MedBot", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the static web prototype at /ui
try:
    app.mount("/ui", StaticFiles(directory="frontend", html=True), name="ui")
except RuntimeError:
    pass                       # frontend/ absent in some deploys


# =====================================================================
# Health
# =====================================================================
@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "app": "MedBot",
        "status": "ok",
        "env": settings.APP_ENV,
        "channels": {
            "sms": sms_service.enabled,
            "whatsapp": whatsapp_service.enabled,
            "web": True,
        },
    }


# =====================================================================
# SMS webhook (Twilio)
# Twilio POSTs application/x-www-form-urlencoded and expects TwiML back.
# =====================================================================
@app.post("/webhook/sms")
async def sms_webhook(From: str = Form(...), Body: str = Form(...)) -> Response:
    logger.info(f"SMS in << {From}: {Body}")
    reply = await dialogue_manager.handle_message(
        user_id=From,
        text=Body,
        channel="sms",
    )
    twiml = sms_service.build_twiml_reply(
        body=reply.text,
        numbered_options=reply.numbered_options,
    )
    logger.info(f"SMS out >> {From}: {reply.text[:80]}")
    return Response(content=twiml, media_type="application/xml")


# =====================================================================
# WhatsApp webhook (Meta Cloud API)
# =====================================================================
@app.get("/webhook/whatsapp")
async def whatsapp_verify(request: Request) -> Response:
    """Meta calls this once with hub.mode/hub.verify_token/hub.challenge."""
    qs = request.query_params
    challenge = whatsapp_service.verify_webhook(
        mode=qs.get("hub.mode"),
        token=qs.get("hub.verify_token"),
        challenge=qs.get("hub.challenge"),
    )
    if challenge:
        return PlainTextResponse(content=challenge)
    return PlainTextResponse(content="Forbidden", status_code=403)


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request) -> JSONResponse:
    payload = await request.json()
    parsed = whatsapp_service.parse_incoming(payload)
    if parsed is None:
        return JSONResponse({"status": "ignored"})
    from_number, text = parsed
    if not text:
        return JSONResponse({"status": "ignored"})

    logger.info(f"WA in << {from_number}: {text}")
    reply = await dialogue_manager.handle_message(
        user_id=from_number,
        text=text,
        channel="whatsapp",
    )
    logger.info(f"WA out >> {from_number}: {reply.text[:80]}")

    if reply.quick_replies:
        await whatsapp_service.send_with_buttons(
            to_number=from_number,
            body=reply.text,
            buttons=reply.quick_replies,
        )
    else:
        await whatsapp_service.send_text(to_number=from_number, body=reply.text)
    return JSONResponse({"status": "ok"})


# =====================================================================
# Web API — used by the HTML prototype in /frontend
# =====================================================================
class ChatRequest(BaseModel):
    user_id: str
    text: str
    channel: str = "web"       # web | sms | whatsapp (for mock demo)


class ChatResponse(BaseModel):
    text: str
    quick_replies: list[str] = []
    numbered_options: list[str] = []
    end_of_flow: bool = False


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(req: ChatRequest) -> ChatResponse:
    reply = await dialogue_manager.handle_message(
        user_id=req.user_id,
        text=req.text,
        channel=req.channel,
    )
    return ChatResponse(
        text=reply.text,
        quick_replies=reply.quick_replies,
        numbered_options=reply.numbered_options,
        end_of_flow=reply.end_of_flow,
    )


@app.post("/api/reset")
async def api_reset(req: ChatRequest) -> dict[str, str]:
    dialogue_manager.reset(req.user_id)
    return {"status": "reset"}

from fastapi import UploadFile, File

@app.post("/api/voice", response_model=ChatResponse)
async def api_voice(
    user_id: str = Form(...),
    channel: str = Form("web"),
    audio: UploadFile = File(...)
) -> ChatResponse:
    audio_bytes = await audio.read()
    res = await voice_service.transcribe(audio_bytes)
    
    text = res.get("text", "")
    if "error" in res or not text:
        text = "Sorry, I couldn't hear that."
        
    reply = await dialogue_manager.handle_message(
        user_id=user_id,
        text=text,
        channel=channel,
    )
    return ChatResponse(
        text=f"(Voice transcription: {text})\n\n{reply.text}",
        quick_replies=reply.quick_replies,
        numbered_options=reply.numbered_options,
        end_of_flow=reply.end_of_flow,
    )

class LocationRequest(BaseModel):
    user_id: str
    lat: float
    lng: float
    channel: str = "web"

from services.location_service import location_service

@app.post("/api/location", response_model=ChatResponse)
async def api_location(req: LocationRequest) -> ChatResponse:
    loc = location_service.resolve_coords(req.lat, req.lng, source="gps")
    text = loc.city if loc.city else f"{req.lat},{req.lng}"
    reply = await dialogue_manager.handle_message(
        user_id=req.user_id,
        text=text,
        channel=req.channel,
    )
    return ChatResponse(
        text=reply.text,
        quick_replies=reply.quick_replies,
        numbered_options=reply.numbered_options,
        end_of_flow=reply.end_of_flow,
    )

@app.post("/api/image", response_model=ChatResponse)
async def api_image(
    user_id: str = Form(...),
    channel: str = Form("web"),
    image: UploadFile = File(...)
) -> ChatResponse:
    # In a real app, this would use a vision model to analyze the image
    # For now, we simulate by assuming it's a wound (as requested)
    text = "I have a wound here. [Attached image of a wound]"
    
    reply = await dialogue_manager.handle_message(
        user_id=user_id,
        text=text,
        channel=channel,
    )
    return ChatResponse(
        text=f"(Image analyzed: Wound detected)\n\n{reply.text}",
        quick_replies=reply.quick_replies,
        numbered_options=reply.numbered_options,
        end_of_flow=reply.end_of_flow,
    )
