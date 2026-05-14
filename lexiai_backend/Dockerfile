# Build from monorepo root (LexiAI/) so paths below resolve:
#   docker build -f lexiai_backend/Dockerfile .
# Railway: leave "Root Directory" empty (repo root) and set Dockerfile path to
# lexiai_backend/Dockerfile. If Root Directory is set to lexiai_backend/, this
# file cannot see ../requirements.txt — use repo root as build context instead.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl bash \
    && rm -rf /var/lib/apt/lists/*

# Dependency lockfile lives at repository root (sibling to lexiai_backend/).
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Only the Django service — avoids baking frontend, extra assets, or unrelated tools into the image.
COPY lexiai_backend/ /app/lexiai_backend/

WORKDIR /app/lexiai_backend

EXPOSE 8000

CMD ["bash", "start.sh"]
