FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 --create-home --home-dir /home/app app \
    && mkdir -p /data/projects \
    && chown -R app:app /app /data /home/app

RUN apt-get update \
    && apt-get install --no-install-recommends --yes git \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/README.md ./
COPY backend/src ./src
RUN pip install --no-cache-dir ".[test]"

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/tests ./tests
COPY presets ./presets
COPY schemas ./schemas

RUN chown -R app:app /app

USER 10001:10001
EXPOSE 8000

CMD ["uvicorn", "novel_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
