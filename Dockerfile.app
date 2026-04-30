FROM node:20-alpine AS frontend-builder

WORKDIR /build/uv_intelligent_demo/webapp/frontend

COPY uv_intelligent_demo/webapp/frontend/package*.json ./

RUN npm ci --only=production && npm cache clean --force

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy entire project
COPY . .

# Copy pre-built frontend dependencies
COPY --from=frontend-builder /build/uv_intelligent_demo/webapp/frontend/node_modules ./uv_intelligent_demo/webapp/frontend/node_modules

# Install Python dependencies for backend
WORKDIR /app/uv_intelligent_demo/webapp/backend
RUN pip install --no-cache-dir -q uvicorn fastapi pydantic python-dotenv paho-mqtt apscheduler || \
    pip install --no-cache-dir uvicorn fastapi pydantic python-dotenv paho-mqtt apscheduler

WORKDIR /app

EXPOSE 8000 5173

CMD ["sh", "-c", "cd /app && bash"]
