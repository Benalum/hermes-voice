# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.11.28 AS uv
FROM python:3.12-slim-bookworm

ENV HOME=/home/hermes \
    PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 hermes \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/hermes hermes

COPY --from=uv /uv /uvx /usr/local/bin/
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY hermes_voice ./hermes_voice

RUN uv sync --locked --no-dev --no-editable \
    && mkdir -p /home/hermes/.hermes-voice \
    && chown -R hermes:hermes /home/hermes

USER hermes
EXPOSE 8990

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8990/healthz', timeout=3).read()"]

CMD ["uvicorn", "hermes_voice.server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8990"]
