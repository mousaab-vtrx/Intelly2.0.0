# UV Reactor - Complete Redeployment & Data Flow Test Guide

## Overview

This guide covers redeploying the entire UV Reactor system and validating the complete data flow:

```
Simulation (CSV replay) 
    ↓
MQTT (Mosquitto)
    ↓
Node-Red (Flow processing)
    ↓
InfluxDB (Time-series storage)
    ↓
Backend (FastAPI)
    ↓
Frontend (React)
```

---

## Phase 1: Stop Existing Services

### Option A: Stop Everything
```bash
cd /home/shinra/uvReactor/uv_intelligent_demo/webapp

# Stop simulation and webapp
bash stop_simulation.sh

# Stop Docker containers
docker compose -f ../docker-compose.yml down

# Verify all services are stopped
docker ps -a
```

### Option B: Selective Restart (Keep Data)
If you want to preserve InfluxDB data and PostgreSQL state:

```bash
cd /home/shinra/uvReactor/uv_intelligent_demo

# Restart only Node-Red
docker compose restart nodered

# Restart only backend (if in Docker)
docker compose restart backend
```

---

## Phase 2: Redeploy Node-Red

### Check Node-Red Configuration
```bash
# View Node-Red flow file
cat deploy/nodered/flows.json | jq . | head -100

# Check credentials
cat deploy/nodered/flows_cred.json

# Verify package.json dependencies
cat deploy/nodered/package.json
```

### Deploy Node-Red
```bash
cd /home/shinra/uvReactor/uv_intelligent_demo

# Option 1: Fresh redeploy with docker-compose
docker compose -f docker-compose.yml pull nodered
docker compose -f docker-compose.yml up -d nodered

# Option 2: Remove and recreate container
docker rm -f uv_nodered
docker compose -f docker-compose.yml up -d nodered

# Monitor logs during startup
docker logs -f uv_nodered
```

### Wait for Node-Red to be Ready
```bash
# Check if Node-Red is healthy
curl -I http://localhost:1880

# Monitor until ready
watch -n 2 'curl -s http://localhost:1880 | head -20'
```

---

## Phase 3: Start All Services

### Start Complete Stack
```bash
cd /home/shinra/uvReactor/uv_intelligent_demo/webapp

# This starts:
# - Flask backend
# - InfluxDB
# - Node-Red
# - Mosquitto
# - PostgreSQL
# - Redis
bash start_simulation.sh
```

### Monitor Service Health
```bash
# Watch Docker status
watch -n 1 'docker ps --format "table {{.Names}}\t{{.Status}}"'

# Check all services
docker compose -f ../docker-compose.yml ps

# Expected services:
# - uv_postgres    (PostgreSQL)
# - uv_redis       (Redis)
# - uv_mosquitto   (MQTT Broker)
# - uv_influxdb    (Time-series DB)
# - uv_nodered     (Flow processor)
# - Flask backend  (HTTP API)
```

### View Service Logs
```bash
# Node-Red logs
docker logs -f uv_nodered

# InfluxDB logs
docker logs -f uv_influxdb

# Mosquitto logs
docker logs -f uv_mosquitto

# Backend logs (if Docker)
docker logs -f uv_backend

# Combined logs
docker compose -f ../docker-compose.yml logs -f
```

---

## Phase 4: Validate Data Flow

### Quick Test (Bash)
```bash
cd /home/shinra/uvReactor/uv_intelligent_demo/webapp

# Run comprehensive bash test
bash test_data_flow.sh

# Expected output:
# ✓ InfluxDB is healthy
# ✓ Mosquitto is accepting connections
# ✓ Node-Red is healthy
# ✓ Flask Backend is healthy
# ✓ InfluxDB bucket is accessible
# ✓ Node-Red has X flow(s) deployed
# ✓ Backend has telemetry data
```

### Detailed Python Test (With MQTT Capture)
```bash
cd /home/shinra/uvReactor/uv_intelligent_demo/webapp

# Install dependencies (if not already installed)
pip install paho-mqtt requests aiohttp

# Run detailed test (listens for 30 seconds)
python3 test_data_flow.py

# This validates:
# - Backend health
# - InfluxDB bucket exists
# - MQTT messages flowing
# - Backend state endpoint
# - AI tools (anomaly detection, forecasting)
# - Active alerts
```

---

## Phase 5: Manual Verification

### 1. Check Node-Red Flows
```bash
# Open Node-Red UI
curl http://localhost:1880

# Flow should be: Read CSV → Parse CSV → Delay → MQTT Publish → InfluxDB Write

# Check flow status
curl -s http://localhost:1880/api/flows | jq .
```

### 2. Check MQTT Messages
```bash
# Subscribe to telemetry topic
mqtt_sub -h localhost -p 1883 -t "uv/telemetry" -v

# Should see messages like:
# uv/telemetry {"timestamp":"2024-04-28T...","flow_m3h":1.2,"uvt":85,"lamp_power_pct":75,...}

# Control messages
mqtt_sub -h localhost -p 1883 -t "uv/control/#" -v
```

### 3. Check InfluxDB Data
```bash
# Query recent data (CLI)
influx query 'from(bucket:"uv_demo") |> range(start: -1h) |> limit(n: 10)' \
  --org uv_org \
  --token uv_admin_token

# Web UI
open http://localhost:8086
# Login: uv_admin / uv_admin_password
# Organization: uv_org
# Bucket: uv_demo
```

### 4. Check Backend State
```bash
# Get current state
curl http://localhost:8000/api/state | jq .

# Sample response:
# {
#   "telemetry": {...},
#   "status": "operational",
#   "last_update": "2024-04-28T...",
#   ...
# }

# Get AI analysis
curl http://localhost:8000/api/ai/tools/analysis?limit=5 | jq .

# Get alerts
curl http://localhost:8000/api/alerts | jq .
```

### 5. Check Frontend
```bash
# Open in browser
open http://localhost:3000

# Check browser console for errors
# Verify copilot panel loads responses correctly
# Test a copilot question
```

---

## Phase 6: Troubleshooting

### Node-Red Not Starting
```bash
# Check logs
docker logs uv_nodered

# Common issues:
# - Port 1880 already in use
# - Flow file syntax errors
# - Missing Node-Red modules

# Force restart
docker rm -f uv_nodered
docker compose -f ../docker-compose.yml up -d nodered
```

### No Data in InfluxDB
```bash
# Check MQTT messages are being published
docker exec uv_mosquitto mosquitto_sub -t "uv/telemetry" -v

# Check Node-Red flow execution
docker logs uv_nodered | grep -i "inject\|csv\|mqtt\|influx"

# Verify InfluxDB bucket
docker exec uv_influxdb influx bucket list --org uv_org --token uv_admin_token
```

### Backend Not Receiving Data
```bash
# Check backend is running
curl -I http://localhost:8000/api/health

# Check backend logs
docker logs -f uv_backend

# Verify Flask app is initialized
curl http://localhost:8000/api/state | jq . | head -20

# Check PostgreSQL connection
docker exec uv_postgres psql -U uvreactor -d uvreactor -c "SELECT version();"
```

### MQTT Connection Issues
```bash
# Test MQTT broker
docker exec uv_mosquitto mosquitto -t

# Check Mosquitto configuration
docker exec uv_mosquitto cat /mosquitto/config/mosquitto.conf

# Verify listener is active
docker exec uv_mosquitto ss -tlnp | grep 1883
```

---

## Phase 7: Performance Monitoring

### Real-time Metrics
```bash
# Watch CPU/Memory usage
docker stats --no-stream

# Specific service
docker stats uv_nodered uv_influxdb

# Disk space
du -sh /var/lib/docker/volumes/*/data
```

### Database Monitoring
```bash
# InfluxDB cardinality
influx bucket list --org uv_org --token uv_admin_token

# Database sizes
docker exec uv_postgres psql -U uvreactor -d uvreactor -c "\db+"

# Redis memory
docker exec uv_redis redis-cli INFO memory
```

### Network Monitoring
```bash
# MQTT message rate
docker exec uv_mosquitto mosquitto_sub -t "uv/telemetry" -v | wc -l

# HTTP request rate (30s)
watch -n 1 'tail -30 /var/log/docker/*.log | grep "GET\|POST" | wc -l'
```

---

## Phase 8: Post-Deployment Checklist

- [ ] All Docker containers running (`docker ps` shows all services)
- [ ] Node-Red flows deployed (`test_data_flow.sh` passes)
- [ ] MQTT messages flowing (`mqtt_sub` shows telemetry)
- [ ] InfluxDB has recent data (< 1 min old)
- [ ] Backend API responding (`/api/health` returns 200)
- [ ] Backend can read telemetry (`/api/state` has data)
- [ ] AI tools working (`/api/ai/tools/analysis` returns results)
- [ ] Frontend loads without errors (browser console clear)
- [ ] Copilot panel displays answers correctly
- [ ] No active error alerts in system

---

## Emergency Operations

### Complete System Reset
```bash
# Stop everything
docker compose -f /home/shinra/uvReactor/uv_intelligent_demo/docker-compose.yml down -v

# Clean volumes (⚠️ REMOVES ALL DATA)
docker volume prune -f

# Restart fresh
cd /home/shinra/uvReactor/uv_intelligent_demo/webapp
bash start_simulation.sh
```

### Restart Single Service
```bash
# Node-Red
docker restart uv_nodered

# InfluxDB (may take 30s)
docker restart uv_influxdb

# Mosquitto
docker restart uv_mosquitto

# PostgreSQL
docker restart uv_postgres

# Check health after restart
sleep 10
bash test_data_flow.sh
```

### View All Logs Concurrently
```bash
docker compose -f /home/shinra/uvReactor/uv_intelligent_demo/docker-compose.yml logs -f --tail=100
```

---

## References

### Key Files
- Docker Compose: `/home/shinra/uvReactor/uv_intelligent_demo/docker-compose.yml`
- Node-Red flows: `/home/shinra/uvReactor/uv_intelligent_demo/deploy/nodered/flows.json`
- Backend app: `/home/shinra/uvReactor/uv_intelligent_demo/webapp/backend/app.py`
- Test scripts: `/home/shinra/uvReactor/uv_intelligent_demo/webapp/test_data_flow.sh` and `.py`

### Services & Ports
| Service | Port | URL |
|---------|------|-----|
| Node-Red | 1880 | http://localhost:1880 |
| InfluxDB | 8086 | http://localhost:8086 |
| MQTT | 1883 | mqtt://localhost:1883 |
| Backend | 8000 | http://localhost:8000 |
| Frontend | 3000 | http://localhost:3000 |
| PostgreSQL | 5432 | postgres://localhost:5432 |
| Redis | 6379 | redis://localhost:6379 |

### Useful Commands
```bash
# Check if port is in use
lsof -i :1880

# Kill process on port
kill -9 $(lsof -t -i :1880)

# Docker compose status
docker compose -f ../docker-compose.yml status

# View docker network
docker network ls

# Inspect network
docker network inspect uv_intelligent_demo_default
```

---

## Support

If issues persist:

1. Check logs: `docker logs <service-name>`
2. Run test suite: `bash test_data_flow.sh`
3. Verify connectivity: `curl -I http://localhost:<port>`
4. Check Docker: `docker ps -a && docker logs`
5. Reset if needed: `docker compose down -v && docker compose up -d`
