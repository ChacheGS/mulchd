FROM python:3.14-slim

# Pull uv from its official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install system deps needed by bun installer
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install bun + mulch CLI (needed for the ml CLI used by domains.py)
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:$PATH"
RUN bun add -g @os-eco/mulch-cli@0.10.7

WORKDIR /app

# Dependency layer — cached unless pyproject.toml or uv.lock changes
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project

# Source (includes migrations/)
COPY src/ ./src/

# Install the project itself
RUN uv sync --no-dev --frozen

COPY deploy/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
