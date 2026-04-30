# UV Reactor Ops Center

This `README.md` is the current source of truth for the repo. It consolidates the project-owned Markdown that was previously split across architecture notes, verification docs, quickstarts, redesign summaries, and cleanup notes.

Some older `.md` files in this repository were written at different stages of the project and are no longer fully aligned with the code. They are still useful as historical context, but this document reflects the current implementation as it exists in the repo today.

## What This Project Is

This repository contains a UV reactor monitoring and operator-assistance stack with four main parts:

1. A simulated process and telemetry generator in `uv_intelligent_demo/`
2. A telemetry/data path built around MQTT, InfluxDB, and PostgreSQL
3. A FastAPI backend for realtime state, alerts, reports, and copilot APIs
4. A React operations UI for telemetry, alerts, planning, and AI-assisted reporting

At a high level, the system is designed so the AI layer advises operators without replacing PLC or SCADA safety responsibilities.

## Current Architecture

```text
Sensors / PLC / Gateway
  -> MQTT broker (Mosquitto)
  -> InfluxDB (optional historian/testing path)
  -> FastAPI backend
     -> PostgreSQL (reports, telemetry history, scheduled tasks)
     -> Redis (report/cache support)
     -> WebSocket realtime stream
     -> AI copilot + analysis tools
  -> React frontend

Optional test tooling:
  -> Node-RED replay/transform flows for demo and testing only
```

The repo also includes a digital twin so the stack can be demonstrated without physical hardware.

## No-Hardware Mode

This project now has a coherent no-hardware path:

- the backend can start even if MQTT is not immediately available because it connects asynchronously and retries
- the standard webapp launcher brings up `postgres`, `redis`, and `mosquitto`
- the core application can run without Node-RED
- Node-RED exists only as optional replay tooling when you want simulated live telemetry

If you do want live simulated telemetry rather than an idle dashboard, use the optional Node-RED replay flow. It now:

- reads from a real dataset path in the repo
- stamps outgoing telemetry with live timestamps
- marks messages as simulated
- restarts automatically after each full replay pass

## What Is Actually Current

These are the important corrections to older docs:

- The active backend is FastAPI, not Flask.
- The active realtime WebSocket endpoint is `/ws/realtime`.
- The active tool-analysis endpoints are `GET /api/ai/tools/analysis` and `POST /api/ai/tools/analysis`.
- The current webapp launcher is [`uv_intelligent_demo/webapp/start_webapp.sh`](/home/shinra/uvReactor/uv_intelligent_demo/webapp/start_webapp.sh), and it starts `postgres`, `redis`, and `mosquitto`. It does not bring up `influxdb` or `nodered`.
- Grafana is still conceptually supported by the frontend/backend, but it is not currently defined in [`uv_intelligent_demo/docker-compose.yml`](/home/shinra/uvReactor/uv_intelligent_demo/docker-compose.yml). Treat Grafana as optional/external unless you add it back.
- The current Docker Compose stack includes `postgres`, `redis`, `mosquitto`, `influxdb`, and `nodered`, but `nodered` is test/demo infrastructure rather than a core runtime dependency.
- The current app code imports the top-level scripts in `uv_intelligent_demo/` such as [`copilot.py`](/home/shinra/uvReactor/uv_intelligent_demo/copilot.py) and [`digital_twin.py`](/home/shinra/uvReactor/uv_intelligent_demo/digital_twin.py). The mirrored `uv_intelligent_demo/backend/core/` layout appears to be an older structure and should not be treated as the primary entrypoint.
- PostgreSQL is the default runtime database. SQLite support remains mainly for migration and legacy compatibility.

## Repo Layout

```text
uvReactor/
├── README.md
├── uv_intelligent_demo/
│   ├── copilot.py
│   ├── digital_twin.py
│   ├── data_pipeline.py
│   ├── hardware_control_bridge.py
│   ├── rag_setup.py
│   ├── setup_compound_ai.py
│   ├── docker-compose.yml
│   ├── config/rules.yaml
│   ├── deploy/
│   │   ├── mosquitto/
│   │   └── nodered/
│   ├── external-resources/
│   └── webapp/
│       ├── backend/
│       ├── frontend/
│       ├── start_webapp.sh
│       ├── stop_webapp.sh
│       └── status_webapp.sh
└── langchain-chromadb-guidebook/
```

## Core Capabilities

### 1. Reason

[`uv_intelligent_demo/copilot.py`](/home/shinra/uvReactor/uv_intelligent_demo/copilot.py) provides the operator copilot:

- ChromaDB-backed retrieval
- Two-pass context retrieval
- Structured response generation
- Mistral API when `MISTRAL_API_KEY` is available
- Ollama fallback with local `mistral`

The copilot is advisory. It answers questions and explains likely causes, risks, and actions; it is not the deterministic control loop.

### 2. Predict

The predictive/tooling layer is split across:

- [`uv_intelligent_demo/digital_twin.py`](/home/shinra/uvReactor/uv_intelligent_demo/digital_twin.py)
- [`uv_intelligent_demo/webapp/backend/ai_tools.py`](/home/shinra/uvReactor/uv_intelligent_demo/webapp/backend/ai_tools.py)

It includes:

- PyOD Isolation Forest for anomaly detection
- Prophet for short-horizon UVT forecasting
- Kalman filtering and CUSUM-style drift signaling in the simulator
- Rule-based advisory logic from [`uv_intelligent_demo/config/rules.yaml`](/home/shinra/uvReactor/uv_intelligent_demo/config/rules.yaml)

### 3. Advise

[`uv_intelligent_demo/hardware_control_bridge.py`](/home/shinra/uvReactor/uv_intelligent_demo/hardware_control_bridge.py) is the control bridge for operator-approved advisories and optional command execution with guardrails.

The safety model described throughout the older architecture docs is still the intended one:

- advisory mode first
- hardware writes off by default
- bounded lamp power
- minimum dose checks
- operator approval before command mode

### 4. Report

The reporting pipeline lives in [`uv_intelligent_demo/webapp/backend/reporting/`](/home/shinra/uvReactor/uv_intelligent_demo/webapp/backend/reporting):

- report generation service
- retrieval of historical context
- PDF/LaTeX artifact generation
- persistence and active-report replacement
- support for daily and notification-style reports

## Data Flow

The current intended telemetry flow is:

```text
Digital twin or PLC/gateway
  -> MQTT topic such as uv/telemetry
  -> FastAPI MQTT consumer
     -> in-memory latest state
     -> PostgreSQL telemetry_history
     -> alert detection
     -> websocket broadcast to frontend
     -> downstream AI/report context
```

There is also an optional testing path:

```text
MQTT
  -> Node-RED
  -> InfluxDB
  -> replay, inspection, and external dashboard experiments
```

The important clarification is that Node-RED is not a required project component. It is included as a convenient replay/transformation tool for demos and testing, while the main application can consume MQTT directly without it.

## Sensor Integration

This system is designed so that physical sensors, simulated sensors, and replayed telemetry all converge on the same agent-facing schema.

### 1. Sensor Source

In a real deployment, field devices would usually be read by a PLC, SCADA layer, or gateway rather than by the agent directly. Typical source signals include:

- flow rate
- turbidity
- UV transmittance
- lamp power
- UV intensity
- computed UV dose
- lamp health or degradation indicators

Without hardware access, this repo substitutes one of two software sources:

- the digital twin in [`uv_intelligent_demo/digital_twin.py`](/home/shinra/uvReactor/uv_intelligent_demo/digital_twin.py)
- the optional Node-RED replay flow in [`uv_intelligent_demo/deploy/nodered/flows.json`](/home/shinra/uvReactor/uv_intelligent_demo/deploy/nodered/flows.json)

### 2. Provisioning to the Application

The core application expects telemetry to arrive as JSON over MQTT on `uv/telemetry`.

The effective schema is:

```json
{
  "timestamp": "2026-04-28T12:00:00Z",
  "flow_m3h": 120.5,
  "turbidity_ntu": 0.85,
  "uvt": 78.2,
  "lamp_power_pct": 75.0,
  "uv_intensity": 45.3,
  "uv_dose_mj_cm2": 42.1,
  "lamp_health_pct": 92.0,
  "anomaly_score": 0.15,
  "cusum_event": false
}
```

If the upstream data comes from another schema, [`uv_intelligent_demo/data_pipeline.py`](/home/shinra/uvReactor/uv_intelligent_demo/data_pipeline.py) can normalize CSV imports into the project’s canonical columns.

### 3. MQTT Ingestion

The FastAPI backend subscribes to `uv/telemetry` in [`uv_intelligent_demo/webapp/backend/app.py`](/home/shinra/uvReactor/uv_intelligent_demo/webapp/backend/app.py).

When a message arrives:

1. the payload is parsed from JSON
2. the latest telemetry snapshot is stored in memory as current state
3. the payload is persisted to PostgreSQL `telemetry_history`
4. alert rules are evaluated against the new snapshot
5. any resulting alerts are broadcast over WebSocket to the frontend

This is the main provisioning path from sensor data to the rest of the system.

### 4. Processing Before the Agent Uses It

Once telemetry is ingested, several parts of the stack consume it:

- the frontend reads the latest state and alert stream for realtime visualization
- the AI tool layer reads recent telemetry windows for anomaly detection and forecasting
- the reporting layer reads telemetry, alerts, and tool outputs to generate operator-facing reports
- the copilot combines current telemetry context with retrieved knowledge-base content

So the agent does not reason over raw electrical signals. It reasons over already structured telemetry frames and persisted history.

### 5. Optional Test Replay Path

When you run the optional Node-RED simulation, the replay flow:

1. reads a CSV dataset from `uv_intelligent_demo/external-resources/datasets/simulated_telemetry_16x.csv`
2. emits one row per second
3. converts each row into the MQTT telemetry schema
4. adds live timestamps and simulation metadata
5. publishes the result to `uv/telemetry`
6. optionally writes the same stream to InfluxDB for dashboard experiments

That means the backend sees replayed telemetry the same way it would see live hardware-provided telemetry.

### 6. Agent Processing Path

From the agent’s perspective, the flow is:

```text
Sensor or simulator
  -> MQTT telemetry frame
  -> FastAPI ingestion
  -> PostgreSQL telemetry history + in-memory latest state
  -> alert detection + AI tool analysis
  -> copilot/reporting context
  -> operator-facing recommendations
```

This is why the system remains usable without hardware: the agent is coupled to the normalized telemetry contract, not to the physical acquisition method.

## Services and Ports

### Docker Compose Services

Defined in [`uv_intelligent_demo/docker-compose.yml`](/home/shinra/uvReactor/uv_intelligent_demo/docker-compose.yml):

- `postgres` on `5432`
- `redis` on `6379`
- `mosquitto` on `1883`
- `influxdb` on `8086`
- `nodered` on `1880` for test/demo flows only

### Webapp Processes

Started separately:

- FastAPI backend on `8000`
- Vite frontend on `5173`
- Optional simulation launcher: [`uv_intelligent_demo/webapp/start_simulation.sh`](/home/shinra/uvReactor/uv_intelligent_demo/webapp/start_simulation.sh)

### Optional/External

- Grafana on `3000` if you run your own instance
- Ollama for local LLM fallback

## FastAPI Surface

The main API is implemented in [`uv_intelligent_demo/webapp/backend/app.py`](/home/shinra/uvReactor/uv_intelligent_demo/webapp/backend/app.py).

Key routes currently present:

- `GET /api/health`
- `GET /api/state`
- `GET /api/alerts`
- `GET /api/events`
- `GET /api/ai/tools/analysis`
- `POST /api/ai/tools/analysis`
- `GET /api/grafana`
- `POST /api/chat`
- `POST /api/reports/generate`
- `GET /api/reports/active`
- `GET /api/reports/daily/today`
- `POST /api/reports/regenerate`
- `POST /api/reports/selection-action`
- `GET /api/reports/{report_id}/pdf`
- `POST /api/schedule-task`
- `GET /api/scheduled-tasks`
- `POST /api/task/{task_id}/override`
- `WS /ws/realtime`

## Frontend

The React app lives in [`uv_intelligent_demo/webapp/frontend/`](/home/shinra/uvReactor/uv_intelligent_demo/webapp/frontend/).

The current UI includes:

- telemetry views
- alerts/events
- report panels
- planning/calendar views
- copilot interactions
- realtime updates over WebSocket

One notable correction from older redesign docs: the frontend is broader now than the original "7-component dashboard" description. The redesign notes are still directionally useful, but they no longer fully describe the present UI surface.

## Database and Persistence

The database abstraction is in [`uv_intelligent_demo/webapp/backend/db.py`](/home/shinra/uvReactor/uv_intelligent_demo/webapp/backend/db.py).

Current runtime expectation:

- PostgreSQL is the default app database
- Redis is used by the reporting/cache layer
- ChromaDB persists local vector data in `uv_intelligent_demo/chroma_db/`
- SQLite remains in the repo mainly for migration/legacy support

Important persisted data includes:

- telemetry history
- scheduled tasks
- reports and report metadata
- vector knowledge index

## Safety and Control Positioning

Across the older architecture documents, the most consistent and still-useful principle is this:

- PLC/SCADA safety should remain separate from AI reasoning
- AI should operate as an advisory and analysis layer
- operator approval should gate any action that could affect hardware

That is the right mental model for this repo. Some older docs overstate implementation certainty with phrases like "fully verified" or "production-ready." The codebase contains substantial working pieces, but those labels should be read as project intent or point-in-time assessment rather than a blanket guarantee that every deployment concern is solved.

## Quick Start

### 1. Python environment

```bash
source venv/bin/activate
```

### 2. Bring up infrastructure

If you want the full local service stack:

```bash
docker compose -f uv_intelligent_demo/docker-compose.yml up -d
```

If you only want the webapp dependencies handled by the launcher:

```bash
./uv_intelligent_demo/webapp/start_webapp.sh
```

Remember that `start_webapp.sh` ensures `postgres`, `redis`, and `mosquitto` are started. If you need InfluxDB or the optional Node-RED test flows, start them separately with Compose.

If you want the no-hardware replay stack in one command:

```bash
./uv_intelligent_demo/webapp/start_simulation.sh
```

To stop it:

```bash
./uv_intelligent_demo/webapp/stop_simulation.sh
```

To verify the no-hardware path end-to-end:

```bash
./uv_intelligent_demo/webapp/smoke_test_simulation.sh
```

Useful options:

- `--no-start` to test against an already running stack
- `--stop-after` to shut the simulation stack down when the test finishes
- `--timeout 180` to allow a longer wait for telemetry to appear

### 3. Start the web app manually

Backend:

```bash
source venv/bin/activate
uvicorn uv_intelligent_demo.webapp.backend.app:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd uv_intelligent_demo/webapp/frontend
npm install
npm run dev
```

### 4. Build the local knowledge base

```bash
python uv_intelligent_demo/rag_setup.py
```

### 5. Generate demo telemetry

```bash
python uv_intelligent_demo/digital_twin.py
```

That writes:

- `uv_intelligent_demo/simulated_telemetry.csv`
- `uv_intelligent_demo/uvt_forecast.csv`

### 6. Use the copilot

```bash
python uv_intelligent_demo/copilot.py
```

## Environment Notes

Common variables used by the current code:

```env
MISTRAL_API_KEY=
MQTT_HOST=localhost
MQTT_PORT=1883
DATABASE_URL=postgresql://uvreactor:uvreactor@localhost:5432/uvreactor
REDIS_URL=redis://localhost:6379/0
GRAFANA_BASE_URL=http://localhost:3000
REPORT_DAILY_HOUR=6
REPORT_DAILY_MINUTE=0
REPORT_TIMEZONE=UTC
ENABLE_HARDWARE_WRITES=false
HW_MIN_POWER_PCT=55
HW_MAX_POWER_PCT=95
HW_MIN_DOSE_MJ_CM2=40
```

## Recommended Reading Order

If you still want the older docs for detail, read them in this order:

1. This `README.md`
2. [`AGENT_ARCHITECTURE_ALIGNMENT.md`](/home/shinra/uvReactor/AGENT_ARCHITECTURE_ALIGNMENT.md)
3. [`SENSOR_DATA_STREAMING_ARCHITECTURE.md`](/home/shinra/uvReactor/SENSOR_DATA_STREAMING_ARCHITECTURE.md)
4. [`AGENT_RESPECTS_PLC_SCADA_PRINCIPLES.md`](/home/shinra/uvReactor/AGENT_RESPECTS_PLC_SCADA_PRINCIPLES.md)
5. [`AGENT_IMPLEMENTATION_VERIFIED.md`](/home/shinra/uvReactor/AGENT_IMPLEMENTATION_VERIFIED.md)
6. [`uv_intelligent_demo/webapp/ARCHITECTURE.md`](/home/shinra/uvReactor/uv_intelligent_demo/webapp/ARCHITECTURE.md)

Use the rest as historical notes unless you first confirm they still match the code.

## Legacy Notes and Misconceptions Cleared Up

- "Grafana was removed" and "Grafana is part of the default stack" are both present in older docs. The accurate statement today is: Grafana-related integration still exists in app/UI assumptions, but the current Compose file does not run Grafana.
- "Node-RED is optional" and "all data must pass through Node-RED" both appear in older docs. The accurate statement today is: Node-RED is only used for testing/demo replay flows, and the core application does not depend on it.
- "The project structure is `backend/core` plus `api`" is outdated. The active runnable web backend is under `uv_intelligent_demo/webapp/backend/`, while top-level scripts under `uv_intelligent_demo/` are still actively used.
- "The backend is production-ready" is too broad on its own. A better statement is: the repo contains a functional prototype-to-demo stack with substantial architecture for alerts, reporting, AI assistance, and persistence, but production readiness still depends on deployment hardening, validation, and operational controls.
- "All docs are equally current" is not true. This file should be treated as the authoritative entrypoint.

## Included Source Docs

This consolidated README was assembled from the project-owned Markdown in:

- `AGENT_ARCHITECTURE_ALIGNMENT.md`
- `AGENT_IMPLEMENTATION_VERIFIED.md`
- `AGENT_RESPECTS_PLC_SCADA_PRINCIPLES.md`
- `SENSOR_DATA_STREAMING_ARCHITECTURE.md`
- `SENSOR_DATA_FLOW_QUICK_REF.md`
- `README_VERIFICATION.md`
- `README_REDESIGN.md`
- `REDESIGN_SUMMARY.md`
- `CLEANUP_AND_DOCUMENTATION_INDEX.md`
- `CLEANUP_SUMMARY.md`
- `VERIFICATION_CHECKLIST.md`
- `uv_intelligent_demo/README.md`
- `uv_intelligent_demo/webapp/README.md`
- `uv_intelligent_demo/webapp/ARCHITECTURE.md`
- `uv_intelligent_demo/webapp/QUICKSTART.md`
- `uv_intelligent_demo/compound_ai_models_and_tools.md`

When any of those disagree with this file, prefer this file and then verify against the code.
