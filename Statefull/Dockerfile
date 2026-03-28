# Simple, robust Dockerfile for FastAPI on AWS EC2
FROM python:3.13-slim

# Prevent Python from writing .pyc files & enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ---- System deps (PostgreSQL client libraries + build tools) ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ---- Copy and normalize requirements first (best for layer caching) ----
COPY requirements-simple.txt /app/requirements.txt
# Fix Windows CRLF if present
RUN sed -i 's/\r$//' /app/requirements.txt

COPY pyproject.toml /app/pyproject.toml

# Upgrade pip tooling, then install deps (prefer wheels)

RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir uv==0.4.21


# RUN uv pip install --system --no-cache --only-binary=:all: -r /app/requirements.txt

# RUN uv pip install --system --no-cache -r /app/requirements.txt
RUN uv pip install --system --no-cache -vvv -r /app/requirements.txt

# ---- Copy app code ----
COPY src/ /app/src/
COPY api_server.py /app/api_server.py
# DO NOT copy .env into the image (we’ll pass env at runtime)
# EXPOSE 8000 is documentation only, but good to keep
EXPOSE 8000

# ---- Run ----
# CMD ["uvicorn", "api_server:app", "--host", "127.0.0.1", "--port", "8000"]
# CMD ["fastapi", "run", "api_server:app", "--host", "127.0.0.1", "--port", "8000"]
# CMD ["fastapi", "run", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]



