FROM python:3.10.18-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/

ENV PYTHONWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
      curl \
      libpq-dev \
      g++ && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV UV_CACHE_DIR=/root/.cache/uv
ENV UV_PROJECT_ENVIRONMENT=/root/.venv

WORKDIR /usr/src/app

COPY pyproject.toml uv.lock ./

# Note: This installs all dependencies, including dev dependencies
# We'll want to add --no-dev when we productionize this
RUN uv sync --frozen

ENV PATH="/root/.venv/bin:$PATH"

CMD sh -c "uv run python manage.py wait_for_db && uv run python manage.py runserver 0.0.0.0:8000"
