import { useMemo, useState } from "react";
import { AlertCircle, AlertTriangle, Bell, Filter, Info } from "lucide-react";

const LEVEL_ORDER = { high: 0, medium: 1, low: 2 };
const LEVEL_LABELS = { high: "Critical", medium: "Warning", low: "Info" };
const CATEGORY_LABELS = {
  dose: "UV Dose",
  anomaly: "Anomaly",
  health: "Lamp Health",
  quality: "Water Quality",
  operation: "Operation",
  system: "System",
};

function severityIcon(level) {
  switch (level) {
    case "high":
      return <AlertCircle size={18} />;
    case "medium":
      return <AlertTriangle size={18} />;
    default:
      return <Info size={18} />;
  }
}

function formatTimestamp(iso) {
  if (!iso) return "Unknown";
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return date.toLocaleDateString();
}

function sortAlerts(alerts) {
  return [...alerts].sort((a, b) => {
    const levelDelta = (LEVEL_ORDER[a.level] ?? 99) - (LEVEL_ORDER[b.level] ?? 99);
    if (levelDelta !== 0) return levelDelta;
    return new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime();
  });
}

function alertKey(alert, index = 0) {
  return [
    alert.id,
    alert.category,
    alert.level,
    alert.timestamp,
    alert.message,
    alert.recommended_action,
    index,
  ]
    .filter(Boolean)
    .join("|");
}

function summarizeAlerts(alerts) {
  const grouped = alerts.reduce((acc, alert) => {
    const key = `${alert.level || "low"}|${alert.category || "system"}`;
    if (!acc[key]) {
      acc[key] = { level: alert.level || "low", category: alert.category || "system", count: 0 };
    }
    acc[key].count += 1;
    return acc;
  }, {});

  return Object.values(grouped).sort((a, b) => {
    const levelDelta = (LEVEL_ORDER[a.level] ?? 99) - (LEVEL_ORDER[b.level] ?? 99);
    if (levelDelta !== 0) return levelDelta;
    return b.count - a.count;
  });
}

export function EventsPanel({ alerts }) {
  const [selectedLevel, setSelectedLevel] = useState("all");
  const [expandedId, setExpandedId] = useState("");

  const orderedAlerts = useMemo(() => sortAlerts(alerts || []), [alerts]);
  const counts = useMemo(
    () => ({
      all: orderedAlerts.length,
      high: orderedAlerts.filter((alert) => alert.level === "high").length,
      medium: orderedAlerts.filter((alert) => alert.level === "medium").length,
      low: orderedAlerts.filter((alert) => alert.level === "low").length,
    }),
    [orderedAlerts]
  );

  const filteredAlerts = useMemo(() => {
    if (selectedLevel === "all") return orderedAlerts;
    return orderedAlerts.filter((alert) => alert.level === selectedLevel);
  }, [orderedAlerts, selectedLevel]);
  const alertSummary = useMemo(() => summarizeAlerts(filteredAlerts), [filteredAlerts]);

  const highlightAlert = filteredAlerts[0] || null;

  return (
    <section className="events-panel">
      <div className="events-header">
        <div>
          <h3>
            <Bell size={20} />
            Alerts & Incidents
          </h3>
          <p className="events-subtitle">
            Prioritized incidents with compact context and operator guidance.
          </p>
        </div>

        <div className="events-filter-bar" aria-label="Alert severity filter">
          <Filter size={14} />
          {[
            { id: "all", label: "All" },
            { id: "high", label: "Critical" },
            { id: "medium", label: "Warning" },
            { id: "low", label: "Info" },
          ].map((option) => (
            <button
              key={option.id}
              type="button"
              className={`events-filter-chip ${selectedLevel === option.id ? "active" : ""}`}
              onClick={() => setSelectedLevel(option.id)}
            >
              {option.label}
              <span>{counts[option.id]}</span>
            </button>
          ))}
        </div>
      </div>

      {orderedAlerts.length === 0 ? (
        <div className="empty-state">
          <Bell size={36} style={{ color: "#8ea0ba" }} />
          <p>No active incidents. Telemetry is currently within expected bands.</p>
        </div>
      ) : (
        <div className="events-layout">
          {highlightAlert ? (
            <article className={`event-highlight event-${highlightAlert.level}`}>
              <div className="event-highlight-top">
                <div className={`event-severity-icon event-${highlightAlert.level}`}>
                  {severityIcon(highlightAlert.level)}
                </div>
                <div>
                  <div className="event-highlight-label">
                    {LEVEL_LABELS[highlightAlert.level] || "Event"}
                  </div>
                  <h4>{CATEGORY_LABELS[highlightAlert.category] || highlightAlert.category}</h4>
                </div>
              </div>
              <p className="event-highlight-message">{highlightAlert.message}</p>
              <div className="event-highlight-meta">
                <span>{formatTimestamp(highlightAlert.timestamp)}</span>
                <span>{highlightAlert.telemetry?.simulated ? "Simulation stream" : "Live stream"}</span>
              </div>
              {highlightAlert.recommended_action ? (
                <div className="event-highlight-action">
                  <strong>Recommended action</strong>
                  <p>{highlightAlert.recommended_action}</p>
                </div>
              ) : null}
            </article>
          ) : null}

          <div className="events-column">
            {alertSummary.length > 0 ? (
              <div className="events-summary-strip">
                {alertSummary.slice(0, 4).map((item) => (
                  <div key={`${item.level}-${item.category}`} className={`events-summary-card event-${item.level}`}>
                    <span className="events-summary-count">{item.count}</span>
                    <span className="events-summary-label">
                      {CATEGORY_LABELS[item.category] || item.category}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
            <div className="events-list">
            {filteredAlerts.map((alert, index) => {
              const alertId = alertKey(alert, index);
              const isExpanded = expandedId === alertId;
              return (
                <article
                  key={alertId}
                  className={`event-row event-${alert.level} ${isExpanded ? "expanded" : ""}`}
                >
                  <button
                    type="button"
                    className="event-row-button"
                    onClick={() => setExpandedId(isExpanded ? "" : alertId)}
                  >
                    <div className={`event-severity-icon event-${alert.level}`}>
                      {severityIcon(alert.level)}
                    </div>
                    <div className="event-row-copy">
                      <div className="event-row-top">
                        <span className="event-category">
                          {CATEGORY_LABELS[alert.category] || alert.category}
                        </span>
                        <span className={`event-badge event-${alert.level}`}>
                          {LEVEL_LABELS[alert.level] || alert.level}
                        </span>
                      </div>
                      <div className="event-message">{alert.message}</div>
                      <div className="event-meta-line">
                        <span>{formatTimestamp(alert.timestamp)}</span>
                        {alert.telemetry?.uv_dose_mj_cm2 !== undefined ? (
                          <span>UV dose {Number(alert.telemetry.uv_dose_mj_cm2).toFixed(1)} mJ/cm²</span>
                        ) : null}
                      </div>
                    </div>
                  </button>

                  {isExpanded ? (
                    <div className="event-details">
                      <div className="event-details-grid">
                        <div className="detail-item">
                          <span className="detail-key">UV Dose</span>
                          <span className="detail-value">
                            {Number.isFinite(Number(alert.telemetry?.uv_dose_mj_cm2))
                              ? `${Number(alert.telemetry.uv_dose_mj_cm2).toFixed(1)} mJ/cm²`
                              : "--"}
                          </span>
                        </div>
                        <div className="detail-item">
                          <span className="detail-key">Lamp Power</span>
                          <span className="detail-value">
                            {Number.isFinite(Number(alert.telemetry?.lamp_power_pct))
                              ? `${Number(alert.telemetry.lamp_power_pct).toFixed(1)}%`
                              : "--"}
                          </span>
                        </div>
                        <div className="detail-item">
                          <span className="detail-key">Lamp Health</span>
                          <span className="detail-value">
                            {Number.isFinite(Number(alert.telemetry?.lamp_health_pct))
                              ? `${Number(alert.telemetry.lamp_health_pct).toFixed(1)}%`
                              : "--"}
                          </span>
                        </div>
                        <div className="detail-item">
                          <span className="detail-key">Turbidity</span>
                          <span className="detail-value">
                            {Number.isFinite(Number(alert.telemetry?.turbidity_ntu))
                              ? `${Number(alert.telemetry.turbidity_ntu).toFixed(2)} NTU`
                              : "--"}
                          </span>
                        </div>
                      </div>
                      {alert.recommended_action ? (
                        <div className="event-detail-action">
                          <strong>Operator guidance</strong>
                          <p>{alert.recommended_action}</p>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </article>
              );
            })}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
