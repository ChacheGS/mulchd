FROM python:3.12-slim

# Install Bun (required for ml CLI)
RUN apt-get update && apt-get install -y curl unzip && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:$PATH"

# Install mulch CLI globally
RUN bun install -g @os-eco/mulch-cli

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY server/ ./server/

CMD ["mulchd"]
