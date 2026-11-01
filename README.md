# MedBot

Medical triage chatbot for **SMS + WhatsApp + Web**, powered by Hugging Face biomedical NER and a deterministic red-flag rules engine. Built to be deployable, not just a demo.

> ⚠️ **Not a diagnostic tool.** MedBot is a triage assistant that suggests urgency and a specialty. In an emergency, call **112**.

---

## What's in the box

```
medbot/
├── main.py                       FastAPI app + all webhooks
├── config.py                     env-var settings
├── requirements.txt
├── Dockerfile / docker-compose.yml / render.yaml
├── .env.example
│
├── services/
│   ├── huggingface_service.py    NER via HF Inference API (or local)
│   ├── triage_engine.py          urgency + specialty decision
│   ├── dialogue_manager.py       state machine (the "brain")
│   ├── doctor_service.py         match doctors + book appointment
│   ├── sms_service.py            Twilio SMS (inbound TwiML + outbound)
│   └── whatsapp_service.py       Meta WhatsApp Cloud API
│
├── knowledge/
│   ├── red_flags.py              hard rules — chest pain + arm → ER
│   ├── cross_questions.py        SOCRATES-style follow-ups
│   └── doctors.json              mock doctor directory (swap for Practo)
│
├── database/
│   ├── models.py                 SQLAlchemy: Conversation / Booking / TriageLog
│   └── session.py                engine + Redis
│
└── frontend/
    └── index.html                dual-phone WhatsApp + SMS demo UI
```

---

## Architecture

```
User
  ↓
[ SMS via Twilio ]  ─┐
[ WhatsApp Cloud API ] ─┼──> FastAPI ──> DialogueManager (state machine)
[ Web /api/chat  ]   ─┘                      ├── HF NER → symptoms
                                             ├── Red-flag rules → EMERGENCY?
                                             ├── Cross-questions → follow-up
                                             ├── Triage engine → specialty
                                             └── Doctor service → booking
                                                  ↓
                                        Postgres (audit trail, accounts)
                                        dialogue state: in-process memory (Redis planned)
```

**Design choice:** The dialogue is a state machine, not free-form LLM. Medical bots must be auditable and can't afford drift on red flags. The LLM (NER) does entity extraction; deterministic Python does the reasoning.

---

## Quick start (local, 5 minutes)

```bash
# 1. Clone and install
git clone <your-repo>
cd medbot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Only if you set USE_HF_INFERENCE_API=false (runs the model in-process, ~2 GB):
# pip install -r requirements-local-ml.txt

# 2. Configure
cp .env.example .env
# minimum: set HF_API_TOKEN (free at huggingface.co/settings/tokens)
# leave USE_HF_INFERENCE_API=true (no GPU needed)
# SECRET_KEY is optional locally, required when APP_ENV=production

# 3. Run
uvicorn main:app --reload

# 4. Open the web prototype
open http://localhost:8000/ui
```

Run the tests with `pip install -r requirements-dev.txt && pytest`.

**That's it — the web UI works fully without Twilio or Meta credentials.** Both phones (WhatsApp look, SMS look) hit the same backend brain.

---

## Deploy to production

### Option A: Render.com (recommended, 10 minutes)

```bash
# Push repo to GitHub, then in Render dashboard:
#   New + → Blueprint → point at your repo
# Render reads render.yaml and provisions:
#   - Web service (Docker), with SECRET_KEY generated for you
#   - Postgres (free tier)
# Fill the other secrets in the dashboard when prompted.
```

Your API is now live at `https://medbot-api.onrender.com`.

### Option B: Docker Compose (any VPS)

```bash
docker compose up -d --build
```

Run a single worker (the default): conversation state is held in process memory, so more
workers would each keep a different copy. Set `CORS_ORIGINS` to your site's origin in production.

---

## Wire up the SMS channel (Twilio)

SMS is the priority channel because **it doesn't need Meta approval** and works on any phone.

1. Sign up at [twilio.com](https://twilio.com) — free trial gives you $15 credit.
2. Buy an SMS-enabled phone number (or use the trial number).
3. In Twilio Console → Phone Numbers → your number → **Messaging Configuration**:
   * A MESSAGE COMES IN → Webhook → `https://your-domain.com/webhook/sms`
   * HTTP POST
4. Add to `.env`:
   ```
   TWILIO_ACCOUNT_SID=ACxxxx
   TWILIO_AUTH_TOKEN=xxxx
   TWILIO_SMS_FROM=+1xxxxxxxxxx
   ```
5. Text your Twilio number "hi" — you should get MedBot's greeting.

**India note:** For Indian A2P SMS you'll need DLT template registration (2-4 weeks via your telecom operator). For MVP + international, Twilio works out of the box.

---

## Wire up the WhatsApp channel (Meta Cloud API)

WhatsApp gets deeper engagement but requires Meta approval — plan **1-4 weeks**, longer for health.

1. Create a Meta Business account → add a WhatsApp Business Account.
2. Get a permanent access token + phone_number_id from the WhatsApp Manager.
3. Configure webhook:
   * Callback URL: `https://your-domain.com/webhook/whatsapp`
   * Verify token: whatever you set in `META_VERIFY_TOKEN`
   * Subscribe to `messages` event
4. Add to `.env`:
   ```
   META_WHATSAPP_TOKEN=EAAxxxx
   META_PHONE_NUMBER_ID=xxxx
   META_VERIFY_TOKEN=your_random_string
   ```
5. Test with the sandbox first — Meta approval for production takes time.

---

## The AI layer

**NER model:** [`d4data/biomedical-ner-all`](https://huggingface.co/d4data/biomedical-ner-all) — a fine-tuned DistilBERT that extracts symptoms, diseases, drugs, body parts, severity, and duration. We use it via the free HF Inference API (`USE_HF_INFERENCE_API=true`), so no GPU is required.

**Why not just prompt GPT-4?** Two reasons:
1. Cost — NER is a solved task, and free HF inference wins.
2. Regulation — a fine-tuned biomedical model has a paper trail; a general LLM giving medical advice is a compliance nightmare.

**Want to fine-tune your own dialogue model?** Point `HF_DIALOGUE_MODEL` at your model on the Hub and set `USE_HF_INFERENCE_API=false` (needs a GPU box). Good starting datasets: MedDialog, HealthCareMagic, MedQuAD.

---

## Compliance quick-check for India

- **DPDP Act 2023**: log consent, store data in India, allow deletion. The `TriageLog` and `Conversation` tables give you the audit trail.
- **Clinical Establishments Act**: MedBot is triage, not diagnosis — every response includes the disclaimer.
- **Telemedicine Practice Guidelines 2020**: the actual doctor consultation happens with a licensed doctor booked through the app; MedBot only routes.

You still need a **DPO** for data protection and a **medical advisor** before public launch.

---

## Demo script (5 min, for judges/investors)

1. Open web prototype at `/ui`. On **WhatsApp** channel, click "Chest pain" demo — show the red-flag engine firing → emergency reply.
2. Reset. Switch to **SMS** channel. Click "Fever + neck stiff" — show meningitis red flag.
3. Reset again. Try a real conversation: "cough and fever for 3 days" → answer cross-questions → get triage + doctor booking.
4. Point at the **Live inspector** panel — entities, state, red flags. This is the auditability story.
5. Show `services/dialogue_manager.py` — no LLM prompt engineering in the decision path; every branch is code you can defend.

---

## Roadmap (post-MVP)

- Persist dialogue state in Redis (needed before running more than one worker)
- Verify Twilio and Meta webhook signatures on `/webhook/sms` and `/webhook/whatsapp`
- Fine-tune `mistralai/Mistral-7B-Instruct-v0.3` on MedDialog for more natural cross-questioning
- Replace mock doctor JSON with Practo / Lybrate partner API
- Add video consultation link generation (Jitsi/Daily.co)
- Multilingual (Hindi first) via `ai4bharat/indic-bert`
- HL7 FHIR export of consultation for handoff to the doctor
- Doctor-side dashboard (Next.js) to review incoming triages

---

## License

MIT. Use it, ship it, don't sue anyone. Don't ship it without a licensed doctor in the loop.
