# Quick Start: Redeploy & Test

## TL;DR - Get Running in 3 Steps

### Step 1: Redeploy Everything
```bash
cd /home/shinra/uvReactor/uv_intelligent_demo/webapp

# Stop all services
bash stop_simulation.sh
docker compose -f ../docker-compose.yml down

# Start everything fresh
bash start_simulation.sh

# Wait 30-60 seconds for services to boot
```

### Step 2: Redeploy Node-Red (Your Part)
```bash
# After starting docker-compose above, redeploy your Node-Red flows:
docker rm -f uv_nodered
docker compose -f ../docker-compose.yml up -d nodered

# Wait for it to be ready
sleep 30
```

### Step 3: Run Test Suite
```bash
# Quick health check (2 minutes)
bash test_data_flow.sh

# Detailed test with MQTT capture (40 seconds)
python3 test_data_flow.py
```

If both tests pass ✓, your data flow is working!

---

## What Gets Tested

✓ Backend API health  
✓ InfluxDB bucket connectivity  
✓ Mosquitto MQTT broker  
✓ Node-Red flows deployed  
✓ MQTT messages flowing  
✓ Telemetry reaching InfluxDB  
✓ Backend reading telemetry  
✓ AI tools (anomaly detection, forecasting)  
✓ Alert generation  

---

## Monitor During Testing

In separate terminal windows:

```bash
# Watch all containers
watch -n 1 'docker ps --format "table {{.Names}}\t{{.Status}}"'

# Node-Red logs
docker logs -f uv_nodered

# InfluxDB logs  
docker logs -f uv_influxdb

# All combined
docker compose -f ../docker-compose.yml logs -f
```

---

## If Tests Fail

1. **Check Node-Red is running:**
   ```bash
   curl http://localhost:1880
   docker logs uv_nodered | tail -30
   ```

2. **Check MQTT is operational:**
   ```bash
   docker logs uv_mosquitto | tail -30
   ```

3. **Check InfluxDB is ready:**
   ```bash
   curl http://localhost:8086/health
   docker logs uv_influxdb | tail -30
   ```

4. **Check backend:**
   ```bash
   curl http://localhost:8000/api/health | jq .
   docker logs uv_backend
   ```

5. **Full reset if needed:**
   ```bash
   docker compose -f ../docker-compose.yml down -v
   bash start_simulation.sh
   sleep 60
   bash test_data_flow.sh
   ```

---

## Test Output Examples

### Successful test_data_flow.sh
```
✓ InfluxDB is healthy
✓ Mosquitto is accepting connections on localhost:1883
✓ Node-Red is healthy
✓ Flask Backend is healthy
✓ InfluxDB bucket is accessible
✓ Node-Red has 1 flow(s) deployed
✓ Backend /api/state endpoint is responding
✓ Backend has telemetry data
✓ ALL TESTS PASSED
```

### Successful test_data_flow.py
```
✓ Backend health check passed
✓ InfluxDB bucket 'uv_demo' exists
ℹ  Listening for MQTT messages for 30 seconds...
✓ Captured 45 telemetry messages
✓ Captured 12 control messages
✓ Backend state retrieved
✓ AI tools analysis retrieved (5 items)
✓ Alerts retrieved (0 total)
```

---

## Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| Port 1880 in use | Old Node-Red still running | `docker rm -f uv_nodered` |
| InfluxDB timeout | Container still starting | Wait 30s, check `docker logs uv_influxdb` |
| No MQTT messages | Simulation not running | Check `docker ps`, ensure `nodered` container is up |
| Backend 500 error | Missing dependencies | Check logs: `docker logs uv_backend` |
| Frontend not loading | React dev server not running | Check port 3000: `curl http://localhost:3000` |

---

## Full Docs

For comprehensive documentation, see:
- `DEPLOYMENT_AND_TEST_GUIDE.md` - Complete step-by-step guide
- `test_data_flow.sh` - Bash health check script
- `test_data_flow.py` - Python detailed test with MQTT capture

---

**Status:** Ready to deploy! 🚀
