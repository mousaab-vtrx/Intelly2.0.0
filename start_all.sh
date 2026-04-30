#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$ROOT_DIR/uv_intelligent_demo/docker-compose.yml"

echo "Starting UV Reactor Ops Center Full Stack..."

# Determine which docker compose to use
DOCKER_COMPOSE_CMD="docker compose"
if ! docker compose version >/dev/null 2>&1; then
  if docker-compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker-compose"
  else
    echo "Error: Docker Compose not found. Cannot start the system." >&2
    exit 1
  fi
fi

# Bring up the entire stack, building frontend and backend if necessary
if ! $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" up -d --build; then
  echo "Error: Failed to start docker containers." >&2
  exit 1
fi

echo "====================================================="
echo "✅ System successfully started in the background."
echo "====================================================="
echo ""
echo "It may take a minute for all services to become healthy."
echo "You can check their status using:"
echo "  $DOCKER_COMPOSE_CMD -f $COMPOSE_FILE ps"
echo ""
echo "Available Endpoints:"
echo "- 🌐 Frontend UI:   http://localhost:5173"
echo "- ⚙️  Backend API:  http://localhost:8000"
echo "- 🛠️  Node-RED:     http://localhost:1880"
echo "- 📊 InfluxDB:      http://localhost:8086"
echo ""
echo "To view logs, run:"
echo "  $DOCKER_COMPOSE_CMD -f $COMPOSE_FILE logs -f"
echo ""
echo "To stop the system, run:"
echo "  $DOCKER_COMPOSE_CMD -f $COMPOSE_FILE down"
echo "====================================================="
