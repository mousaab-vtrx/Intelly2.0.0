from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import paho.mqtt.client as mqtt
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in os.sys.path:
    os.sys.path.append(str(ROOT))

load_dotenv(find_dotenv(filename=".env", usecwd=True), override=False)

from copilot import answer_question, _build_llm  # noqa: E402
try:  # noqa: E402
    from ai_tools import run_all_tools  # noqa: E402
except ModuleNotFoundError:  # noqa: E402
    from uv_intelligent_demo.webapp.backend.ai_tools import run_all_tools
try:  # noqa: E402
    from reporting.service import ReportService, ReportServiceConfig
except ModuleNotFoundError:  # noqa: E402
    from uv_intelligent_demo.webapp.backend.reporting.service import ReportService, ReportServiceConfig
try:  # noqa: E402
    from db import get_database
except ModuleNotFoundError:  # noqa: E402
    from uv_intelligent_demo.webapp.backend.db import get_database


@dataclass
class AlertEvent:
    """Structured alert event with severity levels"""
    id: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    level: Literal["high", "medium", "low"] = "medium"
    category: str = "system"  # dose, anomaly, health, quality, etc.
    message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    telemetry: dict[str, Any] = field(default_factory=dict)
    recommended_action: str = ""


@dataclass
class EventMetadata:
    """Metadata for event-driven architecture"""
    event_type: str
    source: str
    severity: Literal["critical", "warning", "info"] = "info"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    """Structured chat response with formatted content"""
    answer: str
    formatted: bool = True
    sources: list[str] = []


class ReportGenerateRequest(BaseModel):
    report_type: Literal["notification_report", "daily_full_report"] = "notification_report"
    reason: str | None = None


class ReportRegenerateRequest(BaseModel):
    report_type: Literal["notification_report", "daily_full_report"] = "notification_report"


class ReportSelectionActionRequest(BaseModel):
    report_id: str
    action: Literal["review", "explain"]
    selected_text: str


class ToolAnalysisRequest(BaseModel):
    limit: int = 120


class ConnectionHub:
    def __init__(self) -> None:
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for ws in self.connections:
            try:
                await ws.send_json(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)


app = FastAPI(
    title="UV Ops Center API",
    description="Event-driven API for UV reactor operations",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

hub = ConnectionHub()
LATEST: dict[str, Any] = {}
ALERTS: list[AlertEvent] = []
EVENT_LOG: list[dict[str, Any]] = []
SCHEDULED_TASKS: list[dict[str, Any]] = []
LOOP: asyncio.AbstractEventLoop | None = None
SCHEDULER_TASK: asyncio.Task | None = None
DAILY_REPORT_SCHEDULER: AsyncIOScheduler | None = None
DEFAULT_DATABASE_URL = "postgresql://uvreactor:uvreactor@localhost:5432/uvreactor"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
os.environ.setdefault("DATABASE_URL", DATABASE_URL)
DB = get_database()
REPORTS_DIR = Path(__file__).resolve().parent / "report_artifacts"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REPORT_DAILY_HOUR = int(os.getenv("REPORT_DAILY_HOUR", "6"))
REPORT_DAILY_MINUTE = int(os.getenv("REPORT_DAILY_MINUTE", "0"))
REPORT_TIMEZONE = os.getenv("REPORT_TIMEZONE", "UTC")


def _report_context() -> dict[str, Any]:
    try:
        tool_analysis = current_tool_analysis(limit=120)
    except Exception:
        tool_analysis = {}
    return {
        "telemetry": LATEST,
        "alerts": [asdict(alert) for alert in ALERTS],
        "scheduled_tasks": SCHEDULED_TASKS,
        "tool_analysis": tool_analysis,
    }


report_service = ReportService(
    ReportServiceConfig(
        base_dir=ROOT,
        artifacts_dir=REPORTS_DIR,
        redis_url=REDIS_URL,
        database_url=DATABASE_URL,
    ),
    context_provider=_report_context,
)


def now_iso() -> str:
    """Get current timestamp in ISO format"""
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_float(value: Any, precision: int = 1, default: str = "N/A") -> str:
    try:
        return f"{float(value):.{precision}f}"
    except (TypeError, ValueError):
        return default


def _alert_signature(alert: AlertEvent) -> str:
    return f"{alert.category}:{alert.level}"


def _merge_alerts(existing: list[AlertEvent], incoming: list[AlertEvent], cooldown_seconds: int = 900) -> list[AlertEvent]:
    merged = list(existing)
    for alert in incoming:
        signature = _alert_signature(alert)
        alert_time = _parse_iso_timestamp(alert.timestamp) or datetime.now(timezone.utc)
        replacement_index: int | None = None

        for index in range(len(merged) - 1, -1, -1):
            candidate = merged[index]
            if _alert_signature(candidate) != signature:
                continue
            candidate_time = _parse_iso_timestamp(candidate.timestamp)
            if not candidate_time:
                continue
            if (alert_time - candidate_time).total_seconds() <= cooldown_seconds:
                replacement_index = index
            break

        if replacement_index is not None:
            merged[replacement_index] = alert
        else:
            merged.append(alert)

    merged.sort(key=lambda item: item.timestamp)
    return merged[-20:]


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, memoryview):
        return value.tobytes().decode("utf-8")
    return value


def _row_value(row: Any, key: str, index: int) -> Any:
    if hasattr(row, "keys"):
        return _normalize_scalar(row[key])
    return _normalize_scalar(row[index])


def _task_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": _row_value(row, "id", 0),
        "text": _row_value(row, "text", 1),
        "status": _row_value(row, "status", 2),
        "completed": bool(_row_value(row, "completed", 3)),
        "createdAt": _row_value(row, "created_at", 4),
        "scheduledFor": _row_value(row, "scheduled_for", 5),
        "executedAt": _row_value(row, "executed_at", 6),
        "ai_evaluation": (
            json.loads(ai_eval)
            if isinstance((ai_eval := _row_value(row, "ai_evaluation", 7)), str)
            else ai_eval
        ),
    }


def init_db() -> None:
    DB.init_tables()


def load_scheduled_tasks() -> list[dict[str, Any]]:
    with DB.connect() as conn:
        rows = conn.fetchall(
            """
            SELECT id, text, status, completed, created_at, scheduled_for, executed_at, ai_evaluation
            FROM scheduled_tasks
            ORDER BY scheduled_for ASC
            """
        )
    return [_task_row_to_dict(row) for row in rows]


def persist_telemetry_snapshot(payload: dict[str, Any]) -> None:
    recorded_at = str(payload.get("ts") or payload.get("timestamp") or now_iso())
    row_payload = dict(payload)
    row_payload.setdefault("recorded_at", recorded_at)
    with DB.connect() as conn:
        conn.execute(
            """
            INSERT INTO telemetry_history (recorded_at, payload)
            VALUES (%s, %s)
            """,
            (
                recorded_at,
                json.dumps(row_payload),
            ),
        )
        conn.commit()


def load_recent_telemetry(limit: int = 120) -> list[dict[str, Any]]:
    with DB.connect() as conn:
        rows = conn.fetchall(
            """
            SELECT recorded_at, payload
            FROM telemetry_history
            ORDER BY recorded_at DESC
            LIMIT %s
            """,
            (limit,),
        )
    results: list[dict[str, Any]] = []
    for row in reversed(rows):
        recorded_at = _row_value(row, "recorded_at", 0)
        payload = _row_value(row, "payload", 1)
        if isinstance(payload, str):
            payload = json.loads(payload)
        payload = dict(payload or {})
        payload.setdefault("recorded_at", recorded_at)
        payload.setdefault("timestamp", recorded_at)
        results.append(payload)
    return results


def current_tool_analysis(limit: int = 120) -> dict[str, Any]:
    return run_all_tools(load_recent_telemetry(limit=limit))


def upsert_scheduled_task(task: dict[str, Any]) -> None:
    with DB.connect() as conn:
        ai_eval_json = json.dumps(task.get("ai_evaluation")) if task.get("ai_evaluation") else None
        conn.execute("BEGIN")
        conn.execute(
            """
            INSERT INTO scheduled_tasks (
                id, text, status, completed, created_at, scheduled_for, executed_at, ai_evaluation
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(id) DO UPDATE SET
                text=excluded.text,
                status=excluded.status,
                completed=excluded.completed,
                created_at=excluded.created_at,
                scheduled_for=excluded.scheduled_for,
                executed_at=excluded.executed_at,
                ai_evaluation=excluded.ai_evaluation
            """,
            (
                str(task.get("id")),
                task.get("text", ""),
                task.get("status", "scheduled"),
                bool(task.get("completed")),
                task.get("createdAt", now_iso()),
                task.get("scheduledFor", next_midnight_utc_iso()),
                task.get("executedAt"),
                ai_eval_json,
            ),
        )
        conn.commit()


def next_midnight_utc_iso() -> str:
    """Return the next midnight timestamp in UTC ISO format."""
    now = datetime.now(timezone.utc)
    next_day = now.date() + timedelta(days=1)
    next_midnight = datetime.combine(next_day, datetime.min.time(), tzinfo=timezone.utc)
    return next_midnight.isoformat()


async def ai_evaluate_task_execution(task: dict[str, Any]) -> dict[str, Any]:
    """
    AI Agent evaluates whether a scheduled task should be executed.
    Returns decision with reasoning and health assessment.
    """
    try:
        # Build contextual prompt for AI agent
        health_context = f"""
Current System Health:
- UV Dose: {_format_float(LATEST.get('uv_dose_mj_cm2'), 1)} mJ/cm²
- Lamp Power: {_format_float(LATEST.get('lamp_power_pct'), 1)}%
- Lamp Health: {_format_float(LATEST.get('lamp_health_pct'), 1)}%
- Turbidity: {_format_float(LATEST.get('turbidity_ntu'), 2)} NTU
- Anomaly Score: {_format_float(LATEST.get('anomaly_score'), 3)}
- Active Critical Alerts: {len([a for a in ALERTS if a.level == 'high'])}
"""
        
        critical_alerts = [a.message for a in ALERTS[-5:] if a.level == "high"]
        alert_context = f"Recent Critical Events:\n" + "\n".join(f"- {a}" for a in critical_alerts) if critical_alerts else "No critical alerts"
        
        evaluation_prompt = f"""You are a UV reactor AI operator assistant. Evaluate if the following scheduled task should be executed NOW.

Task to Execute: "{task.get('text', '')}"
Scheduled for: {task.get('scheduledFor', 'Unknown')}

{health_context}

{alert_context}

Respond with ONLY valid JSON (no markdown, no extra text):
{{
  "should_execute": true/false,
  "confidence": 0.0-1.0,
  "reason": "brief reason",
  "health_status": "healthy/degraded/critical",
  "recommendation": "action description"
}}"""

        llm = _build_llm()
        response_text = llm.invoke(evaluation_prompt).content
        
        # Parse AI response
        import json
        # Extract JSON from response (handle markdown code blocks)
        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        
        decision = json.loads(response_text.strip())
        return {
            "ai_decision": decision.get("should_execute", True),
            "confidence": decision.get("confidence", 0.5),
            "reason": decision.get("reason", ""),
            "health_status": decision.get("health_status", "unknown"),
            "recommendation": decision.get("recommendation", ""),
            "evaluated_at": now_iso()
        }
    except Exception as err:
        print(f"[AI_EVAL] Error evaluating task: {err}")
        # Fallback: allow execution if no critical alerts
        return {
            "ai_decision": len([a for a in ALERTS if a.level == "high"]) == 0,
            "confidence": 0.5,
            "reason": f"AI evaluation failed due to formatting error, using fallback decision: {str(err)[:100]}",
            "health_status": "unknown",
            "recommendation": "Manual review recommended",
            "evaluated_at": now_iso()
        }


async def scheduled_task_runner() -> None:
    """
    Execute pending tasks when their scheduled time has passed.
    AI agent evaluates task execution based on current system health.
    """
    while True:
        try:
            now = datetime.now(timezone.utc)
            for task in SCHEDULED_TASKS:
                if task.get("completed"):
                    continue

                scheduled_for_raw = task.get("scheduledFor")
                if not scheduled_for_raw:
                    continue

                scheduled_for = _parse_iso_timestamp(scheduled_for_raw)
                if scheduled_for is None:
                    continue
                if scheduled_for.tzinfo is None:
                    scheduled_for = scheduled_for.replace(tzinfo=timezone.utc)

                if now >= scheduled_for:
                    # AI Agent evaluates if task should execute
                    ai_evaluation = await ai_evaluate_task_execution(task)
                    
                    task["completed"] = True
                    task["status"] = "executed" if ai_evaluation["ai_decision"] else "deferred"
                    task["executedAt"] = now.isoformat()
                    task["ai_evaluation"] = ai_evaluation
                    
                    upsert_scheduled_task(task)

                    broadcast_payload = {
                        "type": "task_executed",
                        "task": task,
                        "ai_evaluation": ai_evaluation,
                        "timestamp": now_iso(),
                    }
                    
                    if ai_evaluation["ai_decision"]:
                        # Check if task requires analysis/guidance
                        task_text = task.get('text', '').lower()
                        analysis_keywords = ['examine', 'analyze', 'provide', 'guide', 'check', 'review', 'assess', 'evaluate']
                        if any(keyword in task_text for keyword in analysis_keywords):
                            try:
                                # Execute analysis using AI copilot
                                analysis_result = await answer_question(task.get('text', ''))
                                task["analysis_result"] = analysis_result
                                broadcast_payload["analysis_result"] = analysis_result
                            except Exception as analysis_err:
                                print(f"[SCHEDULER] Analysis error: {analysis_err}")
                                task["analysis_error"] = str(analysis_err)
                        
                        broadcast_payload["message"] = f"✅ Task executed: {task.get('text', 'Unknown')}"
                    else:
                        broadcast_payload["message"] = f"⏸️ Task deferred: {ai_evaluation['reason']}"
                    
                    await hub.broadcast(broadcast_payload)
        except Exception as err:
            print(f"[SCHEDULER] Error: {err}")

        await asyncio.sleep(30)


def detect_notable_changes(telemetry: dict[str, Any]) -> list[AlertEvent]:
    """Detect anomalies and generate alerts based on telemetry"""
    alerts: list[AlertEvent] = []
    dose = _safe_float(telemetry.get("uv_dose_mj_cm2", 0.0))
    anomaly = _safe_float(telemetry.get("anomaly_score", 0.0))
    lamp_health = _safe_float(telemetry.get("lamp_health_pct", 100.0))
    turbidity = _safe_float(telemetry.get("turbidity_ntu", 0.0))
    lamp_power = _safe_float(telemetry.get("lamp_power_pct", 100.0))

    # UV Dose - Critical threshold
    if dose < 40:
        alerts.append(
            AlertEvent(
                level="high",
                category="dose",
                message=f"CRITICAL: UV dose below target ({dose:.1f} mJ/cm²). System not meeting disinfection requirements.",
                timestamp=now_iso(),
                telemetry=telemetry,
                recommended_action="Check lamp power, verify water clarity, review flow rate."
            )
        )
    elif dose < 60:
        alerts.append(
            AlertEvent(
                level="medium",
                category="dose",
                message=f"UV dose suboptimal ({dose:.1f} mJ/cm²). Performance below target.",
                timestamp=now_iso(),
                telemetry=telemetry,
                recommended_action="Monitor trend. May indicate early lamp degradation."
            )
        )

    # Anomaly Score - ML-based detection
    if anomaly < -0.5:
        alerts.append(
            AlertEvent(
                level="high",
                category="anomaly",
                message=f"CRITICAL: Major anomaly detected ({anomaly:.3f}). Behavior significantly deviates from normal patterns.",
                timestamp=now_iso(),
                telemetry=telemetry,
                recommended_action="Perform immediate system diagnostics. Check sensors and hardware."
            )
        )
    elif anomaly < 0:
        alerts.append(
            AlertEvent(
                level="medium",
                category="anomaly",
                message=f"Anomaly score: {anomaly:.3f}. Minor deviation detected.",
                timestamp=now_iso(),
                telemetry=telemetry,
                recommended_action="Monitor for pattern changes."
            )
        )

    # Lamp Health - Maintenance indicator
    if lamp_health < 50:
        alerts.append(
            AlertEvent(
                level="high",
                category="health",
                message=f"CRITICAL: Lamp health critically low ({lamp_health:.1f}%). Immediate replacement needed.",
                timestamp=now_iso(),
                telemetry=telemetry,
                recommended_action="Schedule urgent lamp replacement."
            )
        )
    elif lamp_health < 70:
        alerts.append(
            AlertEvent(
                level="medium",
                category="health",
                message=f"Lamp health degraded ({lamp_health:.1f}%). Plan maintenance window.",
                timestamp=now_iso(),
                telemetry=telemetry,
                recommended_action="Schedule lamp replacement within next maintenance window."
            )
        )

    # Turbidity - Water quality
    if turbidity > 3.0:
        alerts.append(
            AlertEvent(
                level="high",
                category="quality",
                message=f"CRITICAL: High turbidity ({turbidity:.2f} NTU). Water too cloudy for effective disinfection.",
                timestamp=now_iso(),
                telemetry=telemetry,
                recommended_action="Check pre-filters, verify clarification process working."
            )
        )
    elif turbidity > 2.5:
        alerts.append(
            AlertEvent(
                level="medium",
                category="quality",
                message=f"Elevated turbidity ({turbidity:.2f} NTU). Water clarity declining.",
                timestamp=now_iso(),
                telemetry=telemetry,
                recommended_action="Monitor trend. May need filter maintenance."
            )
        )

    # Lamp Power - Operation status
    if lamp_power < 50:
        alerts.append(
            AlertEvent(
                level="medium",
                category="operation",
                message=f"Lamp operating at reduced power ({lamp_power:.1f}%). Output compromised.",
                timestamp=now_iso(),
                telemetry=telemetry,
                recommended_action="Verify electrical supply, check ballast condition."
            )
        )

    return alerts


def mqtt_on_connect(client, _userdata, _flags, reason_code, _properties=None):
    if reason_code == 0:
        client.subscribe("uv/telemetry")
        print("[MQTT] Connected and subscribed to uv/telemetry")


def mqtt_on_message(_client, _userdata, msg):
    global LATEST, ALERTS
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError:
        return
    
    LATEST = payload
    try:
        persist_telemetry_snapshot(payload)
    except Exception as err:
        print(f"[TELEMETRY_STORE] Error persisting telemetry: {err}")
    new_alerts = detect_notable_changes(payload)
    
    if new_alerts:
        ALERTS = _merge_alerts(ALERTS, new_alerts)
        
    if LOOP:
        packet = {
            "type": "telemetry_update",
            "latest": payload,
            "alerts": [asdict(a) for a in new_alerts],
            "timestamp": now_iso(),
        }
        asyncio.run_coroutine_threadsafe(hub.broadcast(packet), LOOP)


def start_mqtt_consumer() -> None:
    host = os.getenv("MQTT_HOST", "localhost")
    port = int(os.getenv("MQTT_PORT", "1883"))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = mqtt_on_connect
    client.on_message = mqtt_on_message
    client.reconnect_delay_set(min_delay=2, max_delay=30)
    client.connect_async(host, port, 60)
    client.loop_start()
    print(f"[MQTT] Starting async consumer for {host}:{port}")


def serialize_report(record: dict[str, Any]) -> dict[str, Any]:
    pdf_url = f"/reports/{record['id']}/pdf"
    return {
        "id": record["id"],
        "title": record["title"],
        "report_type": record["report_type"],
        "is_active": record["is_active"],
        "created_at": record["created_at"],
        "report_date": record.get("report_date"),
        "structured_content": record["structured_content"],
        "metadata": record["metadata"],
        "pdf_url": pdf_url,
    }


async def generate_and_broadcast_report(report_type: Literal["notification_report", "daily_full_report"], reason: str | None = None) -> dict[str, Any]:
    report = await report_service.generate_report(report_type, reason=reason)
    payload = {
        "type": "report_update",
        "report_type": report_type,
        "report": serialize_report(report),
        "timestamp": now_iso(),
    }
    if LOOP:
        await hub.broadcast(payload)
    return report


@app.on_event("startup")
async def startup_event() -> None:
    global LOOP, SCHEDULER_TASK, DAILY_REPORT_SCHEDULER
    LOOP = asyncio.get_running_loop()
    init_db()
    report_service.startup()
    SCHEDULED_TASKS.clear()
    SCHEDULED_TASKS.extend(load_scheduled_tasks())
    start_mqtt_consumer()
    SCHEDULER_TASK = asyncio.create_task(scheduled_task_runner())
    DAILY_REPORT_SCHEDULER = AsyncIOScheduler(timezone=REPORT_TIMEZONE)
    DAILY_REPORT_SCHEDULER.add_job(
        generate_and_broadcast_report,
        CronTrigger(hour=REPORT_DAILY_HOUR, minute=REPORT_DAILY_MINUTE, timezone=REPORT_TIMEZONE),
        kwargs={"report_type": "daily_full_report", "reason": "daily scheduled generation"},
        id="daily-full-report",
        replace_existing=True,
    )
    DAILY_REPORT_SCHEDULER.start()
    await report_service.ensure_active_notification_report()
    print("[API] UV Ops Center API started")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global SCHEDULER_TASK, DAILY_REPORT_SCHEDULER
    if SCHEDULER_TASK:
        SCHEDULER_TASK.cancel()
        try:
            await SCHEDULER_TASK
        except asyncio.CancelledError:
            pass
        SCHEDULER_TASK = None
    if DAILY_REPORT_SCHEDULER:
        DAILY_REPORT_SCHEDULER.shutdown(wait=False)
        DAILY_REPORT_SCHEDULER = None
    report_service.shutdown()


@app.get("/api/health")
def health() -> dict[str, str]:
    """Health check endpoint"""
    return {"status": "ok", "timestamp": now_iso()}


@app.get("/api/state")
def state() -> dict[str, Any]:
    """Get current system state"""
    history = load_recent_telemetry(limit=180)
    return {
        "latest": LATEST,
        "history": history,
        "alerts": [asdict(a) for a in ALERTS[-20:]],  # Last 20 alerts
        "timestamp": now_iso()
    }


@app.get("/api/alerts")
def get_alerts(limit: int = 20) -> dict[str, Any]:
    """Get alerts with filters"""
    return {
        "alerts": [asdict(a) for a in ALERTS[-limit:]],
        "total": len(ALERTS),
        "timestamp": now_iso()
    }


@app.get("/api/events")
def get_events(event_type: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Get event log"""
    events = EVENT_LOG[-limit:]
    if event_type:
        events = [e for e in events if e.get("type") == event_type]
    
    return {
        "events": events,
        "total": len(EVENT_LOG),
        "timestamp": now_iso()
    }


@app.get("/api/ai/tools/analysis")
def get_ai_tool_analysis(limit: int = 120) -> dict[str, Any]:
    rows = load_recent_telemetry(limit=limit)
    analysis = run_all_tools(rows)
    return {
        "analysis": analysis,
        "samples_used": len(rows),
        "timestamp": now_iso(),
    }


@app.post("/api/ai/tools/analysis")
def post_ai_tool_analysis(payload: ToolAnalysisRequest) -> dict[str, Any]:
    rows = load_recent_telemetry(limit=payload.limit)
    analysis = run_all_tools(rows)
    return {
        "analysis": analysis,
        "samples_used": len(rows),
        "timestamp": now_iso(),
    }


@app.get("/api/grafana")
def grafana_panels() -> dict[str, Any]:
    """Get Grafana dashboard panel URLs"""
    base = os.getenv("GRAFANA_BASE_URL", "http://localhost:3000")
    dashboard_uid = "uv-reactor-ai-provisioned"
    qs = "orgId=1&from=now-24h&to=now&theme=dark"
    return {
        "baseUrl": base,
        "panels": [
            f"{base}/d-solo/{dashboard_uid}/uv-reactor-ai-demo-provisioned?{qs}&panelId=1",
            f"{base}/d-solo/{dashboard_uid}/uv-reactor-ai-demo-provisioned?{qs}&panelId=2",
            f"{base}/d-solo/{dashboard_uid}/uv-reactor-ai-demo-provisioned?{qs}&panelId=3",
            f"{base}/d-solo/{dashboard_uid}/uv-reactor-ai-demo-provisioned?{qs}&panelId=4",
        ],
        "dashboardUrl": f"{base}/d/{dashboard_uid}/uv-reactor-ai-demo-provisioned?{qs}",
        "timestamp": now_iso()
    }


@app.post("/api/chat")
async def chat(payload: ChatRequest) -> ChatResponse:
    """AI-powered chat endpoint using vector DB and LangChain"""
    question = payload.question.strip()
    if not question:
        return ChatResponse(
            answer="Ask a question about UV reactor behavior, dose trends, maintenance recommendations, or troubleshooting.",
            formatted=True
        )
    
    # Build context from current telemetry and recent alerts
    context_lines = []
    
    if LATEST:
        context_lines.append(
            f"Current System State:\n"
            f"- UV Dose: {_format_float(LATEST.get('uv_dose_mj_cm2'), 1)} mJ/cm²\n"
            f"- Lamp Power: {_format_float(LATEST.get('lamp_power_pct'), 1)}%\n"
            f"- UVT: {_format_float(LATEST.get('uvt'), 1)}%\n"
            f"- Turbidity: {_format_float(LATEST.get('turbidity_ntu'), 2)} NTU\n"
            f"- Lamp Health: {_format_float(LATEST.get('lamp_health_pct'), 1)}%"
        )
    
    if ALERTS:
        recent_alerts = [a for a in ALERTS[-5:] if a.level == "high"]
        if recent_alerts:
            context_lines.append(
                f"Recent Critical Alerts:\n" +
                "\n".join(f"- {a.message}" for a in recent_alerts)
            )

    try:
        tool_analysis = current_tool_analysis(limit=120)
        context_lines.append(
            "AI Tool Outputs:\n"
            f"- PyOD: {tool_analysis['pyod'].get('summary', 'Unavailable')}\n"
            f"- Prophet: {tool_analysis['prophet'].get('summary', 'Unavailable')}\n"
            f"- PyOD signals: {json.dumps(tool_analysis['pyod'].get('leading_signals', []))}\n"
            f"- Prophet risk below 70%T: {tool_analysis['prophet'].get('threshold_risk_below_70', 'unknown')}"
        )
    except Exception as err:
        context_lines.append(f"AI Tool Outputs:\n- Analysis tools unavailable: {err}")
    
    context = "\n\n".join(context_lines)
    
    try:
        # Get response from LLM with vector DB context
        response, source_labels = answer_question(
            ROOT,
            f"{question}\n\nCurrent Context:\n{context}"
        )
        
        # Format response as markdown
        formatted_answer = _format_copilot_response(response)
        
        return ChatResponse(
            answer=formatted_answer,
            formatted=True,
            sources=list(dict.fromkeys([*(source_labels or ["Vector DB", "Telemetry", "Alert History"]), "PyOD Tool", "Prophet Tool"]))
        )
    except Exception as err:
        return ChatResponse(
            answer=f"### Error\n{str(err)}\n\n"
                  f"### Troubleshooting\n"
                  f"- Verify LLM backend (Ollama or Mistral API)\n"
                  f"- Check ChromaDB vector database connection\n"
                  f"- Review system logs",
            formatted=True
        )


def _strip_emojis(text: str) -> str:
    """Remove all emoji and special Unicode characters, keeping only ASCII and common Unicode."""
    import unicodedata
    
    result = []
    for char in text:
        # Keep standard ASCII and common Unicode (Latin, Greek, basic punctuation)
        category = unicodedata.category(char)
        if category.startswith('L') or category.startswith('N') or category in ('Pc', 'Pd', 'Po', 'Zs'):
            # Keep letters, numbers, underscores, hyphens, punctuation, spaces
            if not any(ord(c) > 127 for c in char):  # ASCII
                result.append(char)
            elif category.startswith('L'):  # Letters (including accented)
                result.append(char)
        elif char in ' \t\n':  # Keep whitespace
            result.append(char)
    
    return ''.join(result)


def _format_copilot_response(raw_response: str) -> str:
    """Format copilot output as consistent, professional markdown without emojis."""
    # First pass: strip emoji characters
    raw_response = _strip_emojis(raw_response)
    
    header_prefixes = {
        "summary",
        "analysis",
        "cause",
        "causes",
        "risk",
        "risks",
        "recommendation",
        "recommendations",
        "action",
        "actions",
        "evidence",
        "why it matters",
        "error",
        "troubleshooting",
    }
    bullet_prefixes = ("-", "*")
    status_prefix_patterns = {
        "recommendation:": "Recommendation",
        "warning:": "Warning",
        "error:": "Error",
        "info:": "Info",
    }

    def _normalize_section_header(line: str) -> str | None:
        normalized = line.strip().lstrip("#").strip()
        normalized_lower = normalized.lower().rstrip(":")
        return f"### {normalized.rstrip(':')}" if any(
            normalized_lower.startswith(prefix) for prefix in header_prefixes
        ) else None

    def _normalize_bullet(line: str) -> str | None:
        stripped = line.strip()
        for prefix in bullet_prefixes:
            if stripped.startswith(prefix):
                return f"- {stripped[len(prefix):].strip()}"
        return None

    def _normalize_status_line(line: str) -> str | None:
        stripped = line.strip().lower()
        for pattern, label in status_prefix_patterns.items():
            if stripped.startswith(pattern):
                original_line = line.strip()
                remainder = original_line[len(pattern):].lstrip(" :-").strip()
                return f"**{label}:** {remainder}" if remainder else f"**{label}**"
        return None

    lines = raw_response.split("\n")
    formatted_lines: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        formatted_header = _normalize_section_header(line)
        if formatted_header:
            formatted_lines.append(formatted_header)
            continue

        formatted_bullet = _normalize_bullet(line)
        if formatted_bullet:
            formatted_lines.append(formatted_bullet)
            continue

        formatted_status = _normalize_status_line(line)
        if formatted_status:
            formatted_lines.append(formatted_status)
            continue

        formatted_lines.append(line)

    result = "\n".join(formatted_lines)

    if "###" not in result:
        result = f"### Analysis\n{result}"

    return result


def _model_label(llm: Any) -> str:
    return (
        getattr(llm, "model_name", None)
        or getattr(llm, "model", None)
        or getattr(llm, "model_id", None)
        or llm.__class__.__name__
    )


def _matching_report_sections(report: dict[str, Any], selected_text: str) -> list[dict[str, Any]]:
    selected_terms = {term for term in selected_text.lower().split() if len(term) > 3}
    sections = report.get("structured_content", {}).get("sections", [])
    if not selected_terms:
        return sections[:2]

    matches: list[dict[str, Any]] = []
    for section in sections:
        haystack = " ".join([section.get("heading", ""), *(section.get("bullets", []) or [])]).lower()
        if any(term in haystack for term in selected_terms):
            matches.append(section)
    return matches[:3] or sections[:2]


@app.post("/reports/generate")
@app.post("/api/reports/generate")
async def generate_report(payload: ReportGenerateRequest) -> dict[str, Any]:
    report = await generate_and_broadcast_report(payload.report_type, reason=payload.reason or "operator requested generation")
    return {
        "status": "ok",
        "report": serialize_report(report),
        "timestamp": now_iso(),
    }


@app.get("/reports/active")
@app.get("/api/reports/active")
def get_active_report() -> dict[str, Any]:
    report = report_service.get_active_report()
    if not report:
        return {"report": None, "timestamp": now_iso()}
    return {"report": serialize_report(report), "timestamp": now_iso()}


@app.get("/reports/daily/today")
@app.get("/api/reports/daily/today")
def get_daily_today_report() -> dict[str, Any]:
    report = report_service.get_daily_today_report()
    if not report:
        return {"report": None, "timestamp": now_iso()}
    return {"report": serialize_report(report), "timestamp": now_iso()}


@app.post("/reports/regenerate")
@app.post("/api/reports/regenerate")
async def regenerate_report(payload: ReportRegenerateRequest) -> dict[str, Any]:
    report = await generate_and_broadcast_report(payload.report_type, reason="operator forced regeneration")
    return {
        "status": "ok",
        "report": serialize_report(report),
        "timestamp": now_iso(),
    }


SELECTION_ACTION_CONFIG: dict[str, dict[str, str]] = {
    "review": {
        "label": "Review",
        "guidance": "Assess the selected excerpt, highlight operational implications, and identify follow-up checks.",
        "directives": """
- Evaluate the selection like an operator-facing reviewer, not a generic assistant.
- Surface risk, ambiguity, and missing verification steps before offering reassurance.
- Tie every point back to reactor operations, maintenance posture, compliance, or decision impact.
- Prefer concrete checks, thresholds, dependencies, and likely consequences over paraphrase.
""".strip(),
    },
    "explain": {
        "label": "Explain",
        "guidance": "Explain the selected excerpt in plain language, including why it matters in this report.",
        "directives": """
- Translate technical wording into direct operator language without losing the original meaning.
- Clarify terminology, implicit assumptions, and cause-and-effect relationships in the excerpt.
- Emphasize why the passage appears in this report and what the operator should understand from it.
- Keep the explanation accessible, but preserve any material warning or operational nuance.
""".strip(),
    },
}


@app.post("/api/reports/selection-action")
async def run_report_selection_action(payload: ReportSelectionActionRequest) -> dict[str, Any]:
    selected_text = payload.selected_text.strip()
    if not selected_text:
        raise HTTPException(status_code=400, detail="Selection text is required")

    report = report_service.get_report(payload.report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    knowledge_chunks = report_service.retriever.retrieve_knowledge(
        f"{payload.action} {selected_text} uv reactor operational context"
    )
    prior_report_chunks = report_service.retriever.retrieve_prior_reports(
        f"{payload.action} {selected_text} historical reactor reporting context"
    )
    matching_sections = _matching_report_sections(report, selected_text)
    action_config = SELECTION_ACTION_CONFIG[payload.action]

    llm = _build_llm()
    prompt = f"""
You are assisting an operator reading a UV reactor report.
Use the report excerpt plus retrieved database context to answer the requested action.
Do not ask follow-up questions.
Do not invent facts beyond the supplied context.

Requested action: {action_config["label"].upper()}
Action guidance: {action_config["guidance"]}
Hidden response directives:
{action_config["directives"]}

Selected report text:
{selected_text}

Matching report sections:
{json.dumps(matching_sections, indent=2)}

Retrieved knowledge base context:
{json.dumps(knowledge_chunks, indent=2)}

Retrieved prior report context:
{json.dumps(prior_report_chunks, indent=2)}

Return concise markdown with:
### {action_config["label"]}
- 2 to 4 bullet points
### Why It Matters
- 1 to 3 bullet points
### Evidence Used
- 1 to 3 bullet points
"""

    try:
        raw_answer = llm.invoke(prompt).content
        answer = _format_copilot_response(raw_answer)
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Unable to generate AI action response: {err}") from err

    return {
        "action": payload.action,
        "action_label": action_config["label"],
        "answer": answer,
        "selected_text": selected_text,
        "context_count": len(knowledge_chunks) + len(prior_report_chunks),
        "sources": [f"Knowledge {idx + 1}" for idx, _ in enumerate(knowledge_chunks[:3])]
        + [f"History {idx + 1}" for idx, _ in enumerate(prior_report_chunks[:2])],
        "model": _model_label(llm),
        "timestamp": now_iso(),
    }


@app.get("/reports/{report_id}/pdf")
@app.get("/api/reports/{report_id}/pdf")
def get_report_pdf(report_id: str) -> Response:
    cached_pdf = report_service.cache.get_pdf(report_id)
    if cached_pdf:
        return Response(content=cached_pdf.content, media_type=cached_pdf.content_type)

    report = report_service.get_report(report_id)
    if not report or not report.get("pdf_path"):
        raise HTTPException(status_code=404, detail="PDF not found for report")

    pdf_path = Path(report["pdf_path"])
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Stored PDF file is missing")
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"{report_id}.pdf")


@app.post("/api/schedule-task")
async def schedule_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Schedule a task to run at midnight (00:00)"""
    scheduled_for = payload.get("scheduledFor") or next_midnight_utc_iso()
    task = {
        "id": payload.get("id"),
        "text": payload.get("text"),
        "status": "scheduled",
        "completed": False,
        "createdAt": payload.get("createdAt", now_iso()),
        "scheduledFor": scheduled_for,
        "executedAt": None,
    }
    
    SCHEDULED_TASKS.append(task)
    upsert_scheduled_task(task)
    
    if LOOP:
        await hub.broadcast({
            "type": "task_scheduled",
            "task": task,
            "timestamp": now_iso(),
        })
    
    return {
        "status": "scheduled",
        "task": task,
        "message": f"Task '{task['text']}' scheduled for midnight execution",
        "timestamp": now_iso()
    }


@app.get("/api/scheduled-tasks")
def get_scheduled_tasks() -> dict[str, Any]:
    """Get all scheduled tasks"""
    persisted_tasks = load_scheduled_tasks()
    SCHEDULED_TASKS.clear()
    SCHEDULED_TASKS.extend(persisted_tasks)
    return {
        "tasks": persisted_tasks,
        "total": len(persisted_tasks),
        "timestamp": now_iso()
    }


@app.post("/api/task/{task_id}/override")
async def override_task_execution(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Override AI agent task decision - allow operator to force execute or cancel deferred tasks
    """
    task_to_update = None
    for task in SCHEDULED_TASKS:
        if str(task.get("id")) == str(task_id):
            task_to_update = task
            break
    
    if not task_to_update:
        return {"error": "Task not found", "timestamp": now_iso()}
    
    override_action = payload.get("action")  # "execute" or "cancel"
    override_reason = payload.get("reason", "Manual operator override")
    
    if override_action == "execute":
        task_to_update["completed"] = True
        task_to_update["status"] = "executed"
        task_to_update["executedAt"] = now_iso()
        if not task_to_update.get("ai_evaluation"):
            task_to_update["ai_evaluation"] = {}
        task_to_update["ai_evaluation"]["operator_override"] = True
        task_to_update["ai_evaluation"]["override_reason"] = override_reason
    elif override_action == "cancel":
        task_to_update["completed"] = True
        task_to_update["status"] = "cancelled"
        if not task_to_update.get("ai_evaluation"):
            task_to_update["ai_evaluation"] = {}
        task_to_update["ai_evaluation"]["operator_override"] = True
        task_to_update["ai_evaluation"]["override_reason"] = override_reason
    
    upsert_scheduled_task(task_to_update)
    
    if LOOP:
        await hub.broadcast({
            "type": "task_override",
            "task": task_to_update,
            "action": override_action,
            "reason": override_reason,
            "timestamp": now_iso(),
        })
    
    return {
        "status": "updated",
        "task": task_to_update,
        "message": f"Task {override_action}d with operator override",
        "timestamp": now_iso()
    }


@app.put("/api/task/{task_id}")
def update_scheduled_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Update a scheduled task"""
    task_to_update = None
    for task in SCHEDULED_TASKS:
        if str(task.get("id")) == str(task_id):
            task_to_update = task
            break
    
    if not task_to_update:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Update fields
    if "text" in payload:
        task_to_update["text"] = payload["text"]
    if "scheduledFor" in payload:
        task_to_update["scheduledFor"] = payload["scheduledFor"]
    
    upsert_scheduled_task(task_to_update)
    
    return {
        "status": "updated",
        "task": task_to_update,
        "timestamp": now_iso()
    }


@app.delete("/api/task/{task_id}")
def delete_scheduled_task(task_id: str) -> dict[str, Any]:
    """Delete a scheduled task"""
    task_to_delete = None
    for i, task in enumerate(SCHEDULED_TASKS):
        if str(task.get("id")) == str(task_id):
            task_to_delete = task
            del SCHEDULED_TASKS[i]
            break
    
    if not task_to_delete:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Remove from database
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
            conn.commit()
    except Exception as err:
        print(f"[DB] Error deleting task: {err}")
        # Re-add to memory if DB delete failed
        SCHEDULED_TASKS.append(task_to_delete)
        raise HTTPException(status_code=500, detail="Database error")
    
    return {
        "status": "deleted",
        "task_id": task_id,
        "timestamp": now_iso()
    }


@app.websocket("/ws/realtime")
async def ws_realtime(ws: WebSocket) -> None:
    """WebSocket endpoint for realtime telemetry and alerts"""
    await hub.connect(ws)
    try:
        # Send initial state
        await ws.send_json({
            "type": "connection_established",
            "latest": LATEST,
            "alerts": [asdict(a) for a in ALERTS[-10:]],
            "active_report": serialize_report(active_report) if (active_report := report_service.get_active_report()) else None,
            "daily_report": serialize_report(daily_report) if (daily_report := report_service.get_daily_today_report()) else None,
            "timestamp": now_iso(),
        })
        
        # Keep connection alive and receive heartbeats
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)
    except Exception as err:
        print(f"[WS] Error: {err}")
        hub.disconnect(ws)


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )