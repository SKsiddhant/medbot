FROM python:3.11-slim

# System deps for psycopg2 and healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python deps first for docker-layer caching.
# The default (hosted Hugging Face API) needs no torch; build with
#   --build-arg INSTALL_LOCAL_ML=true
# only if you run the NER model inside the container (USE_HF_INFERENCE_API=false).
ARG INSTALL_LOCAL_ML=false
COPY requirements.txt requirements-local-ml.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_LOCAL_ML" = "true" ]; then pip install --no-cache-dir -r requirements-local-ml.txt; fi

# App code, run as an unprivileged user
COPY . .
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

# Render and most hosts inject PORT at runtime; 8000 is the local default.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

# Keep this at ONE worker. DialogueManager stores conversation state in a per-process dict
# (services/dialogue_manager.py); Redis is not used for it yet, so extra workers would each
# hold a different copy and users would randomly lose their place mid-conversation.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY:-1}"]
