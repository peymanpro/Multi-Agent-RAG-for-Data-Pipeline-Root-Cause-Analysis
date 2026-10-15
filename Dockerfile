FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RCA_RUNBOOKS_DIR=/app/data/runbooks

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY data/runbooks ./data/runbooks

RUN python -m pip install ".[api-redis]" \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent \
       --shell /usr/sbin/nologin app \
    && chown -R 10001:10001 /app

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "pipeline_rca.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
