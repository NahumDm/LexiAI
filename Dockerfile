# LexiAI backend image — build context MUST be the monorepo root (this folder).
#
# Local:
#   docker build -t lexiai-backend .
#
# Railway: use the default "Root Directory" (repo root). This file is named
# Dockerfile so it is auto-detected; railway.json also pins the Dockerfile builder.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl bash \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
# Large wheels (torch / NVIDIA CUDA); transient IncompleteRead is common — retry + longer timeout.
RUN pip install --upgrade pip \
    && pip install --retries 10 --timeout 300 -r /app/requirements.txt

COPY lexiai_backend/ /app/lexiai_backend/

WORKDIR /app/lexiai_backend

EXPOSE 8000

CMD ["bash", "start.sh"]
