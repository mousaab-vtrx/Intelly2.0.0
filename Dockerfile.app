# ─── Stage 1: Node.js frontend dependencies ───────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build/uv_intelligent_demo/webapp/frontend

COPY uv_intelligent_demo/webapp/frontend/package*.json ./
RUN npm ci && npm cache clean --force

# ─── Stage 2: Production image ─────────────────────────────────────────────────
FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20.x
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the full project
COPY . .

# Restore pre-built frontend node_modules
COPY --from=frontend-builder /build/uv_intelligent_demo/webapp/frontend/node_modules \
     ./uv_intelligent_demo/webapp/frontend/node_modules

# Install all Python backend dependencies
RUN pip install --no-cache-dir \
    uvicorn[standard] \
    fastapi \
    pydantic \
    pydantic-settings \
    python-dotenv \
    paho-mqtt \
    apscheduler \
    psycopg2-binary \
    redis \
    langchain \
    langchain-core \
    langchain-community \
    langchain-mistralai \
    langchain-text-splitters \
    langchain-chroma \
    chromadb \
    sentence-transformers \
    pypdf \
    pyod \
    prophet \
    pandas \
    numpy \
    scikit-learn \
    scipy \
    statsmodels \
    filterpy \
    matplotlib

WORKDIR /app

EXPOSE 8000 5173

CMD ["sh", "-c", "echo 'Container ready'"]
