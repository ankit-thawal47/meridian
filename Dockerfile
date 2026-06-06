FROM python:3.12-slim

# git is required for per-task worktrees (Property 2 isolation)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
