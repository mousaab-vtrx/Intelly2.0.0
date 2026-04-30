import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Sidebar } from "./components/Sidebar";
import { StatusHeader } from "./components/StatusHeader";
import { MetricsPanel } from "./components/MetricsPanel";
import { EventsPanel } from "./components/EventsPanel";
import { CopilotPanel } from "./components/CopilotPanel";
import { Calendar } from "./components/Calendar";
import { PlanningPanel } from "./components/PlanningPanel";
import { ReportPanel } from "./components/ReportPanel";
import { API_BASE_URL } from "./api/client";
import {
  reportKeys,
  useActiveReport,
  useAiToolAnalysis,
  useDailyTodayReport,
  useGenerateReportMutation,
  useReportSelectionActionMutation,
} from "./hooks/useReports";
import { useEventPublish } from "./hooks/useEventBus";

const API_PORT = 8000;
const DEFAULT_COPILOT_WIDTH = 392;
const MIN_COPILOT_WIDTH = 320;
const MAX_COPILOT_WIDTH = 560;

function clampCopilotWidth(width) {
  if (typeof window === "undefined") {
    return Math.max(MIN_COPILOT_WIDTH, Math.min(MAX_COPILOT_WIDTH, width));
  }

  const viewportWidth = window.innerWidth;
  const maxWidth =
    viewportWidth < 960
      ? Math.max(280, viewportWidth - 24)
      : viewportWidth < 1240
        ? Math.min(520, Math.max(320, viewportWidth - 52))
        : Math.min(MAX_COPILOT_WIDTH, Math.max(MIN_COPILOT_WIDTH, viewportWidth - 320));

  return Math.max(Math.min(width, maxWidth), Math.min(MIN_COPILOT_WIDTH, maxWidth));
}

function telemetryKey(entry) {
  return entry?.recorded_at || entry?.timestamp || entry?.source_timestamp || null;
}

function alertKey(alert, index = 0) {
  return [
    alert?.id,
    alert?.category,
    alert?.level,
    alert?.timestamp,
    alert?.message,
    alert?.recommended_action,
    index,
  ]
    .filter(Boolean)
    .join("|");
}

function dedupeAlerts(alerts) {
  const seen = new Set();
  return alerts.filter((alert, index) => {
    const key = alertKey(alert, index);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export default function App() {
  const [telemetry, setTelemetry] = useState({});
  const [telemetryHistory, setTelemetryHistory] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [selectedPlanningDate, setSelectedPlanningDate] = useState(new Date());
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(true);
  const [copilotWidth, setCopilotWidth] = useState(() => clampCopilotWidth(DEFAULT_COPILOT_WIDTH));
  const [activeSection, setActiveSection] = useState("telemetry");

  const publish = useEventPublish();
  const queryClient = useQueryClient();
  const activeReportQuery = useActiveReport();
  const dailyReportQuery = useDailyTodayReport();
  const aiToolAnalysisQuery = useAiToolAnalysis();
  const generateReportMutation = useGenerateReportMutation();
  const reportSelectionActionMutation = useReportSelectionActionMutation();

  // Fetch initial data
  useEffect(() => {
    async function fetchInitialData() {
      try {
        const stateRes = await fetch(`${API_BASE_URL}/api/state`);

        if (stateRes.ok) {
          const data = await stateRes.json();
          setTelemetry(data.latest || {});
          setAlerts(data.alerts || []);
          if (Array.isArray(data.history) && data.history.length > 0) {
            setTelemetryHistory(data.history);
          } else if (data.latest) {
            setTelemetryHistory([data.latest]);
          }
        }
      } catch (err) {
        publish("notification:show", {
          severity: "warning",
          title: "Connection Issue",
          message: `Unable to load system state. ${err.message}`,
          duration: 3000,
        });
      }
    }

    fetchInitialData();
  }, [publish]);

  useEffect(() => {
    function syncCopilotWidth() {
      setCopilotWidth((prev) => clampCopilotWidth(prev));
    }

    syncCopilotWidth();
    window.addEventListener("resize", syncCopilotWidth);
    return () => window.removeEventListener("resize", syncCopilotWidth);
  }, []);

  async function handleGenerateReport(reportType, regenerate = false) {
    try {
      const report = await generateReportMutation.mutateAsync({ reportType, regenerate });
      publish("notification:show", {
        severity: "success",
        title: reportType === "daily_full_report" ? "Daily report ready" : "Active report updated",
        message: report.title,
        duration: 3000,
      });
    } catch (err) {
      publish("notification:show", {
        severity: "error",
        title: "Report generation failed",
        message: err.message,
        duration: 4000,
      });
    }
  }

  async function handleAssistSelection({ reportId, action, selectedText }) {
    try {
      const result = await reportSelectionActionMutation.mutateAsync({ reportId, action, selectedText });
      publish("notification:show", {
        severity: "success",
        title: `${result.action_label} ready`,
        message: "AI response generated from report context.",
        duration: 2500,
      });
    } catch (err) {
      publish("notification:show", {
        severity: "error",
        title: "AI action failed",
        message: err.message,
        duration: 3500,
      });
    }
  }

  function assistPropsFor(report) {
    const isCurrentReport = reportSelectionActionMutation.variables?.reportId === report?.id;
    return {
      onAssistSelection: handleAssistSelection,
      isAssisting: reportSelectionActionMutation.isPending && isCurrentReport,
      assistResult: isCurrentReport ? reportSelectionActionMutation.data : null,
      assistError: isCurrentReport ? (reportSelectionActionMutation.error?.message || "") : "",
    };
  }

  // WebSocket for realtime updates
  useEffect(() => {
    const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${wsProtocol}://${window.location.hostname}:${API_PORT}/ws/realtime`;

    let reconnectTimeout;

    function connectWebSocket() {
      try {
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          publish("notification:show", {
            severity: "success",
            title: "Connected to realtime stream",
            duration: 2000,
          });
        };

        ws.onmessage = (event) => {
          try {
            const packet = JSON.parse(event.data);

            if (packet.latest) {
              setTelemetry(packet.latest);
              setTelemetryHistory((prev) => {
                const next = [...prev, packet.latest];
                const seen = new Set();
                const deduped = next.filter((item) => {
                  const key = telemetryKey(item);
                  if (!key) return true;
                  if (seen.has(key)) return false;
                  seen.add(key);
                  return true;
                });
                return deduped.slice(-360);
              });
            }

            if (packet.alerts?.length > 0) {
              setAlerts((prev) => dedupeAlerts([...packet.alerts, ...prev]).slice(0, 50));
              packet.alerts.forEach((alert) => {
                publish("event:alert", alert);
              });

              if (packet.alerts.some((a) => a.level === "high")) {
                setCopilotOpen(true);
              }
            }

            if (packet.type === "report_update") {
              queryClient.invalidateQueries({ queryKey: reportKeys.active });
              queryClient.invalidateQueries({ queryKey: reportKeys.dailyToday });
              publish("notification:show", {
                severity: "info",
                title: packet.report_type === "daily_full_report" ? "Daily report refreshed" : "Active report refreshed",
                message: packet.report?.title || "A new report is available.",
                duration: 3000,
              });
            }

            if (["task_executed", "task_scheduled", "task_override"].includes(packet.type)) {
              publish("scheduled_task:update", packet);
              const eventTitle = packet.type === "task_scheduled"
                ? "Task scheduled"
                : packet.type === "task_override"
                  ? "Task override received"
                  : "Task execution result";
              publish("notification:show", {
                severity: packet.type === "task_executed" ? "success" : "info",
                title: eventTitle,
                message: packet.message || packet.task?.text || "Orchestrator updated.",
                duration: 3000,
              });
            }
          } catch (err) {
            console.error("Failed to parse WebSocket message:", err);
          }
        };

        ws.onerror = (err) => {
          console.error("WebSocket error:", err);
        };

        ws.onclose = () => {
          reconnectTimeout = setTimeout(connectWebSocket, 3000);
        };

        return ws;
      } catch (err) {
        console.error("Failed to create WebSocket:", err);
        reconnectTimeout = setTimeout(connectWebSocket, 3000);
      }
    }

    const ws = connectWebSocket();

    return () => {
      clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, [publish, queryClient]);

  function renderSection() {
    switch (activeSection) {
      case "telemetry":
        return (
          <section id="telemetry" className="section">
            <MetricsPanel
              telemetry={telemetry}
              telemetryHistory={telemetryHistory}
            />
          </section>
        );
      case "alerts":
        return (
          <section id="alerts" className="section">
            <EventsPanel alerts={alerts} />
          </section>
        );
      case "reports":
        return (
          <ReportPanel
            heading="Active Notification Report"
            description="Current incident response snapshot with immediate actions and concise findings."
            report={activeReportQuery.data}
            isLoading={activeReportQuery.isLoading}
            error={activeReportQuery.error}
            onGenerate={() => handleGenerateReport("notification_report", true)}
            isGenerating={generateReportMutation.isPending && generateReportMutation.variables?.reportType === "notification_report"}
            generateLabel="Regenerate Active Report"
            variant="active"
            {...assistPropsFor(activeReportQuery.data)}
          />
        );
      case "daily-report":
        return (
          <ReportPanel
            heading="Today's Daily Full Report"
            description="Broader shift-level context, continuity notes, and AI-supported trend interpretation."
            report={dailyReportQuery.data}
            isLoading={dailyReportQuery.isLoading}
            error={dailyReportQuery.error}
            onGenerate={() => handleGenerateReport("daily_full_report", true)}
            isGenerating={generateReportMutation.isPending && generateReportMutation.variables?.reportType === "daily_full_report"}
            generateLabel="Regenerate Today's Daily Report"
            variant="daily"
            toolAnalysis={aiToolAnalysisQuery.data}
            toolAnalysisLoading={aiToolAnalysisQuery.isLoading}
            {...assistPropsFor(dailyReportQuery.data)}
          />
        );
      case "planning":
        return (
          <div className="planning-layout">
            <div className="planning-left">
              <Calendar
                compact
                selectedDate={selectedPlanningDate}
                onSelectDate={setSelectedPlanningDate}
              />
            </div>
            <div className="planning-right">
              <PlanningPanel selectedDate={selectedPlanningDate} />
            </div>
          </div>
        );
      default:
        return (
          <section id="telemetry" className="section">
            <MetricsPanel
              telemetry={telemetry}
              telemetryHistory={telemetryHistory}
            />
          </section>
        );
    }
  }

  return (
    <div
      className={`app-layout ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${
        copilotOpen ? "" : "copilot-collapsed"
      }`}
      style={{ "--copilot-width": `${copilotWidth}px` }}
    >
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        activeSection={activeSection}
        onSelectSection={setActiveSection}
        copilotOpen={copilotOpen}
        onToggleCopilot={() => setCopilotOpen((prev) => !prev)}
      />

      <main className="app-main">
        <StatusHeader activeReport={activeReportQuery.data} dailyReport={dailyReportQuery.data} />

        <div className="content-sections">{renderSection()}</div>
      </main>

      <CopilotPanel
        collapsed={sidebarCollapsed}
        isOpen={copilotOpen}
        telemetry={telemetry}
        width={copilotWidth}
        onResize={(nextWidth) => setCopilotWidth(clampCopilotWidth(nextWidth))}
      />
    </div>
  );
}
