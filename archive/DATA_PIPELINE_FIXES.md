# UV Reactor Data Pipeline Issues & Fixes

## Summary of Issues Found

### 1. **PostgreSQL Database Schema Error** ❌ → ✅ FIXED
**Issue:** The `telemetry_history` table was not created in PostgreSQL due to IMMUTABLE function casting errors in index definitions.

**Root Cause:** 
```sql
-- This fails in PostgreSQL:
CREATE INDEX idx_telemetry_history_recorded_at 
ON telemetry_history(((recorded_at)::timestamptz) DESC)  
-- Error: functions in index expression must be marked IMMUTABLE
```

**Solution:** Changed all three indexes to use simple column casting instead of function casts:
```sql
-- This works:
CREATE INDEX idx_telemetry_history_recorded_at 
ON telemetry_history(recorded_at DESC)
```

**Files Modified:**
- `webapp/backend/db.py` - Fixed 3 index definitions

### 2. **Data Streaming Issues** ✅ VERIFIED & WORKING
**Status:** Node-Red IS successfully streaming to InfluxDB

**Confirmed Flow:**
```
Node-Red CSV Reader 
    ↓
Function: Build MQTT + Line Protocol
    ↓
    ├→ MQTT: uv/telemetry (→ Backend listens here)
    ├→ HTTP: InfluxDB write (✅ Confirmed working)
    └→ MQTT: uv/control/advisory
```

**What's working:**
- Node-Red reads CSV data
- Transforms to InfluxDB Line Protocol with nanosecond timestamps
- Publishes to MQTT topic `uv/telemetry`
- Writes directly to InfluxDB via HTTP POST

**Verification:**
```bash
# InfluxDB query confirms data is streaming
docker exec uv_influxdb influx query 'from(bucket:"uv_demo") |> range(start: -1h)'
# Result: 100s of UVT measurements with timestamps
```

### 3. **Unrealistic CSV Data** ❌ → ✅ FIXED
**Issue:** Original CSV had:
- Only 48 data points (one day of data)
- Stable metrics (lamp health ~48-57%, minimal degradation)
- No realistic fault progression to test alerts

**Solution:** Generated 5-day dataset with realistic degradation:

**New Dataset: `simulated_telemetry_16x.csv`**
- **1,440 records** (12 samples/hour × 24 hours × 5 days)
- **Day 1**: Normal operation (lamp health ~98%)
- **Days 2-2.5**: Gradual degradation (lamp health: 95% → 75%)
- **Days 3-5**: Critical phase (lamp health: 75% → 30%)
- Progressive indicators:
  - Lamp health decreases linearly
  - Turbidity increases (0.5 NTU → 3.2 NTU)
  - UV intensity drops with lamp degradation
  - Anomaly scores increase (0 → 1.0)
  - Lamp power increases to compensate
  - CUSUM events triggered during critical phase

## Data Flow Architecture

```
┌─────────────────────────────────────────────┐
│         Docker Compose Services             │
├─────────────────────────────────────────────┤
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │  Node-Red (Port 1880)                │  │
│  │  - Reads CSV: simulated_telemetry_16x│  │
│  │  - Injects at 9300ms intervals       │  │
│  └────┬─────────────────────────────────┘  │
│       │                                     │
│       ├─ HTTP POST → InfluxDB              │
│       │  (Line Protocol, nanosec)          │
│       │                                     │
│       └─ MQTT PUBLISH                      │
│          uv/telemetry (JSON)               │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │  InfluxDB (Port 8086)                │  │
│  │  Bucket: uv_demo                     │  │
│  │  Org: uv_org                         │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │  PostgreSQL (Port 5432)              │  │
│  │  telemetry_history table ✅ FIXED    │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │  Mosquitto (Port 1883)               │  │
│  │  uv/telemetry topic                  │  │
│  └──────────────────────────────────────┘  │
│                                             │
└─────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────┐
│     Backend (webapp/backend/app.py)         │
│  - Subscribes to MQTT uv/telemetry         │
│  - Stores in PostgreSQL telemetry_history  │
│  - Detects anomalies                       │
│  - Broadcasts alerts via WebSocket         │
└─────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────┐
│     Frontend (Vue.js)                       │
│  - Displays real-time metrics              │
│  - Shows alerts (dose, health, quality)    │
│  - Monitors degradation                    │
└─────────────────────────────────────────────┘
```

## Alert Detection During Degradation

The enhanced CSV will trigger these alerts as data flows through:

### Phase 1: Normal (Day 1)
- ✅ Lamp health: 98% (healthy)
- ✅ Anomaly score: 0.01 (negligible)
- ✅ Turbidity: 0.5 NTU (clear)
- **Alerts**: None or minor

### Phase 2: Degrading (Days 2-2.5)
- ⚠️ Lamp health: 95% → 75% (declining)
- ⚠️ Anomaly score: 0.05 → 0.25 (increasing)
- ⚠️ Turbidity: 0.8 → 2.3 NTU (rising)
- **Alerts**: "Monitor lamp health", "Slight degradation detected"

### Phase 3: Critical (Days 3-5)
- 🔴 Lamp health: 75% → 30% (critically low)
- 🔴 Anomaly score: 0.25 → 1.0 (critical)
- 🔴 Turbidity: 2.3 → 3.2 NTU (too high)
- 🔴 Lamp power: 70% → 92% (maxed out)
- **Alerts**: 
  - "CRITICAL: Lamp health degraded. Plan maintenance."
  - "CRITICAL: High turbidity. Check pre-filters."
  - UV dose risk alerts

## How to Test

### 1. Create PostgreSQL Tables
```bash
# The backend will auto-create tables on startup
# But to manually create:
sudo docker exec uv_postgres psql -U uvreactor -d uvreactor << 'SQL'
CREATE TABLE IF NOT EXISTS telemetry_history (
    id BIGSERIAL PRIMARY KEY,
    recorded_at TEXT NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_telemetry_history_recorded_at
ON telemetry_history(recorded_at DESC);
SQL
```

### 2. Start Services
```bash
cd uv_intelligent_demo
docker compose up -d
```

### 3. Verify Data Flow
```bash
# Check Node-Red is running
docker logs -f uv_nodered

# Monitor MQTT messages
docker exec uv_mosquitto mosquitto_sub -t "uv/telemetry" -u test -P test

# Query InfluxDB
docker exec uv_influxdb influx query 'from(bucket:"uv_demo") 
  |> range(start: -1h) 
  |> filter(fn: (r) => r._measurement == "uv_reactor")'

# Query PostgreSQL
docker exec uv_postgres psql -U uvreactor -d uvreactor \
  -c "SELECT COUNT(*) FROM telemetry_history; SELECT * FROM telemetry_history LIMIT 5;"
```

### 4. Monitor in Webapp
- Navigate to http://localhost:5173
- Open Copilot panel to ask about status
- Watch metrics change as degradation progresses
- Observe alerts appear as thresholds are crossed

## Testing Alert Scenarios

The degradation CSV will allow you to verify:

✅ **Lamp Health Alerts** (at 70%, 50% thresholds)
✅ **Turbidity Alerts** (at 2.5 NTU, 3.0 NTU thresholds)
✅ **Dose Risk Alerts** (when UV dose drops below target)
✅ **Anomaly Detection** (when anomaly_score spikes)
✅ **CUSUM Events** (process change detection)
✅ **Gradual Degradation** (multi-day trend analysis)

## Files Changed

| File | Changes |
|------|---------|
| `webapp/backend/db.py` | Fixed 3 PostgreSQL index definitions |
| `external-resources/datasets/simulated_telemetry_16x.csv` | Generated 1,440 realistic records with degradation |
| `external-resources/datasets/simulated_telemetry_degradation.csv` | Same as above |
| `generate_realistic_telemetry.py` | NEW: Python script to generate datasets |

## Next Steps

1. ✅ Run `docker compose up -d` to start services
2. ✅ Backend will auto-create PostgreSQL tables
3. ✅ Node-Red will begin streaming degradation data
4. ✅ Monitor frontend for alert progression
5. ✅ Test Copilot's ability to detect and report anomalies

---
**Generated:** 2026-04-28
**Dataset Duration:** 5 days of simulated operation
**Sample Rate:** 1 sample every 5 minutes
**Total Records:** 1,440
