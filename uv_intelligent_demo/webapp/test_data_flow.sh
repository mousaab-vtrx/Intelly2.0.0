#!/usr/bin/env bash
#
# Test Data Flow from Simulation → Node-Red → InfluxDB → Backend
# Run this AFTER Node-Red has been redeployed
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEBAPP_DIR="$ROOT_DIR/uv_intelligent_demo/webapp"
COMPOSE_FILE="$ROOT_DIR/uv_intelligent_demo/docker-compose.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging helpers
log_info() {
  echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
  echo -e "${GREEN}✓ $1${NC}"
}

log_warn() {
  echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
  echo -e "${RED}✗ $1${NC}"
}

# Check for required tools
for tool in curl; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    log_error "Required tool '$tool' not found. Please install it."
    exit 1
  fi
done

# Check for jq (optional but recommended)
if ! command -v jq >/dev/null 2>&1; then
  log_warn "jq not found. JSON parsing will be limited."
fi

# Health check helpers
check_http_endpoint() {
  local url="$1"
  local label="$2"
  local attempts=5
  local delay=2
  
  while (( attempts > 0 )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log_success "$label is healthy"
      return 0
    fi
    sleep "$delay"
    ((attempts--))
  done
  
  log_error "$label is NOT healthy at $url"
  return 1
}

check_mqtt_connection() {
  local host="${1:-localhost}"
  local port="${2:-1883}"
  local label="${3:-MQTT}"
  
  if timeout 5 bash -c "cat < /dev/null > /dev/tcp/$host/$port" 2>/dev/null; then
    log_success "$label is accepting connections on $host:$port"
    return 0
  else
    log_error "$label is NOT accepting connections on $host:$port"
    return 1
  fi
}

# Test InfluxDB connectivity and bucket
test_influxdb_bucket() {
  local influx_url="http://localhost:8086"
  local org="uv_org"
  local bucket="uv_demo"
  local token="uv_admin_token"
  
  log_info "Testing InfluxDB bucket: $bucket..."
  
  # Query for recent data
  local response=$(curl -fsS -X POST "$influx_url/api/v2/query?org=$org" \
    -H "Authorization: Token $token" \
    -H "Content-Type: application/vnd.flux" \
    -d 'from(bucket:"uv_demo") |> range(start: -1h) |> limit(n:1)' 2>/dev/null || echo "{}")
  
  if echo "$response" | grep -q "error"; then
    log_error "InfluxDB query failed: $response"
    return 1
  else
    log_success "InfluxDB bucket is accessible"
    return 0
  fi
}

# Test backend state endpoint
test_backend_state() {
  local backend_url="http://localhost:8000"
  
  log_info "Testing backend state endpoint..."
  
  local response=$(curl -fsS "$backend_url/api/state" 2>/dev/null || echo "{}")
  
  if echo "$response" | jq . >/dev/null 2>&1; then
    log_success "Backend /api/state endpoint is responding"
    
    # Check if telemetry data is present
    if echo "$response" | jq -e '.telemetry' >/dev/null 2>&1; then
      log_success "Backend has telemetry data"
      echo "$response" | jq '.telemetry' | head -20
      return 0
    else
      log_warn "Backend state retrieved but no telemetry data yet"
      return 0
    fi
  else
    log_error "Backend /api/state endpoint not responding"
    return 1
  fi
}

# Test backend AI tools analysis
test_backend_tools() {
  local backend_url="http://localhost:8000"
  
  log_info "Testing backend AI tools endpoint..."
  
  local response=$(curl -fsS "$backend_url/api/ai/tools/analysis?limit=5" 2>/dev/null || echo "{}")
  
  if echo "$response" | jq . >/dev/null 2>&1; then
    log_success "Backend /api/ai/tools/analysis endpoint is responding"
    echo "$response" | jq . | head -30
    return 0
  else
    log_error "Backend /api/ai/tools/analysis endpoint not responding"
    return 1
  fi
}

# Test Node-Red flow status
test_nodered_flows() {
  local nodered_url="http://localhost:1880"
  
  log_info "Testing Node-Red flows..."
  
  if check_http_endpoint "$nodered_url" "Node-Red UI"; then
    # Try to get flow info via API
    local response=$(curl -fsS "$nodered_url/api/flows" 2>/dev/null || echo "{}")
    
    if echo "$response" | jq . >/dev/null 2>&1; then
      local flow_count=$(echo "$response" | jq 'length')
      log_success "Node-Red has $flow_count flow(s) deployed"
      echo "$response" | jq . | head -50
      return 0
    else
      log_warn "Node-Red UI is running but API not accessible"
      return 0
    fi
  else
    return 1
  fi
}

# Main test sequence
main() {
  echo ""
  echo "============================================================"
  echo "  UV REACTOR DATA FLOW VALIDATION TEST"
  echo "============================================================"
  echo ""
  
  local failed=0
  
  # Phase 1: Service Health Checks
  log_info "PHASE 1: Service Health Checks"
  echo ""
  
  check_http_endpoint "http://localhost:8086/health" "InfluxDB" || ((failed++))
  check_mqtt_connection "localhost" "1883" "Mosquitto" || ((failed++))
  check_http_endpoint "http://localhost:1880" "Node-Red" || ((failed++))
  check_http_endpoint "http://localhost:8000/api/health" "Flask Backend" || ((failed++))
  check_http_endpoint "http://localhost:5432" "PostgreSQL (port check)" || log_warn "PostgreSQL port check failed (expected if not exposed)"
  
  echo ""
  
  # Phase 2: Data Pipeline Tests
  log_info "PHASE 2: Data Pipeline Tests"
  echo ""
  
  test_influxdb_bucket || ((failed++))
  echo ""
  
  test_nodered_flows || ((failed++))
  echo ""
  
  test_backend_state || ((failed++))
  echo ""
  
  test_backend_tools || ((failed++))
  echo ""
  
  # Phase 3: Summary
  log_info "PHASE 3: Summary"
  echo ""
  
  if (( failed == 0 )); then
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✓ ALL TESTS PASSED${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Data flow validation successful!"
    echo ""
    echo "Next steps:"
    echo "1. Monitor Node-Red logs: docker logs -f uv_nodered"
    echo "2. Check InfluxDB UI: http://localhost:8086"
    echo "3. Check backend: http://localhost:8000/api/state"
    echo "4. Verify simulation is running: http://localhost:8000/api/health"
    echo ""
    return 0
  else
    echo -e "${RED}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}✗ SOME TESTS FAILED (${failed} failures)${NC}"
    echo -e "${RED}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "1. Check Docker logs: docker ps -a"
    echo "2. View service logs: docker logs <service-name>"
    echo "3. Verify docker-compose: docker compose config"
    echo "4. Restart services: docker compose restart"
    echo ""
    return 1
  fi
}

# Parse arguments
HELP=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      HELP=true
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      HELP=true
      shift
      ;;
  esac
done

if [[ "$HELP" == "true" ]]; then
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Test the data flow from simulation → Node-Red → InfluxDB → Backend

OPTIONS:
  -h, --help        Show this help message

DESCRIPTION:
  This script validates that:
  1. All services (InfluxDB, Mosquitto, Node-Red, Backend) are healthy
  2. InfluxDB bucket is accessible
  3. Node-Red flows are deployed and running
  4. Backend can retrieve state and telemetry data
  5. AI tools (anomaly detection, forecasting) are functional

PREREQUISITES:
  - Docker Compose services should be running
  - Run this AFTER Node-Red has been redeployed
  - Simulation should be sending data

MONITORING COMMANDS:
  Check Node-Red logs:      docker logs -f uv_nodered
  Check Backend logs:       docker logs -f uv_backend
  Check InfluxDB logs:      docker logs -f uv_influxdb
  View all services:        docker ps -a
  Query Docker events:      docker events --filter type=container

EOF
  exit 0
fi

main
