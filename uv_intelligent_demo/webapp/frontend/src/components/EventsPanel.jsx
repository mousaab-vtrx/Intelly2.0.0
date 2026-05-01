import { useMemo, useState } from "react";
import { AlertCircle, AlertTriangle, Bell, ChevronDown, Filter, Info, ShieldCheck } from "lucide-react";

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

function SeverityIcon({ level, size = 18 }) {
  switch (level) {
    case "high":   return <AlertCircle size={size} />;
    case "medium": return <AlertTriangle size={size} />;
    default:       return <Info size={size} />;
  }
}

function formatTimestamp(iso) {
  if (!iso) return "Unknown";
  const date = new Date(iso);
  const diffMins = Math.floor((Date.now() - date) / 60000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return date.toLocaleDateString();
}

function groupAlerts(alerts) {
  // Produce one group per category×level combo, keeping only the most recent alert in each bucket
  const map = new Map();
  for (const alert of alerts) {
    const key = `${alert.level}|${alert.category}`;
    const existing = map.get(key);
    if (!existing || new Date(alert.timestamp) > new Date(existing.latest.timestamp)) {
      map.set(key, {
        level: alert.level,
        category: alert.category,
        latest: alert,
        count: (existing?.count ?? 0) + 1,
      });
    } else {
      existing.count += 1;
    }
  }
  return [...map.values()].sort((a, b) => {
    const ld = (LEVEL_ORDER[a.level] ?? 99) - (LEVEL_ORDER[b.level] ?? 99);
    if (ld !== 0) return ld;
    return new Date(b.latest.timestamp) - new Date(a.latest.timestamp);
  });
}

export function EventsPanel({ alerts }) {
  const [selectedLevel, setSelectedLevel] = useState("all");
  const [expandedKey, setExpandedKey] = useState(null);

  const allAlerts = alerts || [];
  const counts = useMemo(() => ({
    all:    allAlerts.length,
    high:   allAlerts.filter(a => a.level === "high").length,
    medium: allAlerts.filter(a => a.level === "medium").length,
    low:    allAlerts.filter(a => a.level === "low").length,
  }), [allAlerts]);

  const filtered = useMemo(() =>
    selectedLevel === "all" ? allAlerts : allAlerts.filter(a => a.level === selectedLevel),
    [allAlerts, selectedLevel]
  );

  const groups = useMemo(() => groupAlerts(filtered), [filtered]);
  const topAlert = groups[0]?.latest ?? null;

  if (allAlerts.length === 0) {
    return (
      <section className="events-panel">
        <div className="events-header">
          <div>
            <h3><Bell size={20} /> Alerts &amp; Incidents</h3>
            <p className="events-subtitle">Prioritized incidents with operator guidance.</p>
          </div>
        </div>
        <div className="empty-state">
          <ShieldCheck size={40} style={{ color: "var(--color-success, #22c55e)" }} />
          <p>All systems nominal. No active incidents.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="events-panel">
      {/* ── Header ── */}
      <div className="events-header">
        <div>
          <h3><Bell size={20} /> Alerts &amp; Incidents</h3>
          <p className="events-subtitle">Prioritized incidents with operator guidance.</p>
        </div>
        <div className="events-filter-bar" aria-label="Alert severity filter">
          <Filter size={14} />
          {[
            { id: "all",    label: "All" },
            { id: "high",   label: "Critical" },
            { id: "medium", label: "Warning" },
            { id: "low",    label: "Info" },
          ].map(opt => (
            <button
              key={opt.id}
              type="button"
              className={`events-filter-chip ${selectedLevel === opt.id ? "active" : ""}`}
              onClick={() => setSelectedLevel(opt.id)}
            >
              {opt.label}
              <span>{counts[opt.id]}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="events-layout">
        {/* ── Hero Card (most critical) ── */}
        {topAlert && (
          <article className={`event-highlight event-${topAlert.level}`}>
            <div className="event-highlight-top">
              <div className={`event-severity-icon event-${topAlert.level}`}>
                <SeverityIcon level={topAlert.level} size={20} />
              </div>
              <div>
                <div className="event-highlight-label">{LEVEL_LABELS[topAlert.level] || "Event"}</div>
                <h4>{CATEGORY_LABELS[topAlert.category] || topAlert.category}</h4>
              </div>
            </div>
            <p className="event-highlight-message">{topAlert.message}</p>
            <div className="event-highlight-meta">
              <span>{formatTimestamp(topAlert.timestamp)}</span>
              <span>{topAlert.telemetry?.simulated ? "Simulation stream" : "Live stream"}</span>
            </div>
            {topAlert.recommended_action && (
              <div className="event-highlight-action">
                <strong>Recommended action</strong>
                <p>{topAlert.recommended_action}</p>
              </div>
            )}
          </article>
        )}

        {/* ── Grouped incident list ── */}
        <div className="events-column">
          <div className="events-list events-list-grouped">
            {groups.map(group => {
              const key = `${group.level}|${group.category}`;
              const isExpanded = expandedKey === key;
              const alert = group.latest;
              return (
                <article
                  key={key}
                  className={`event-row event-${group.level} ${isExpanded ? "expanded" : ""}`}
                >
                  <button
                    type="button"
                    className="event-row-button"
                    onClick={() => setExpandedKey(isExpanded ? null : key)}
                  >
                    <div className={`event-severity-icon event-${group.level}`}>
                      <SeverityIcon level={group.level} />
                    </div>

                    <div className="event-row-copy">
                      <div className="event-row-top">
                        <span className="event-category">
                          {CATEGORY_LABELS[group.category] || group.category}
                        </span>
                        <div className="event-row-badges">
                          <span className={`event-badge event-${group.level}`}>
                            {LEVEL_LABELS[group.level]}
                          </span>
                          {group.count > 1 && (
                            <span className="event-badge event-count">
                              ×{group.count}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="event-message">{alert.message}</div>
                      <div className="event-meta-line">
                        <span>{formatTimestamp(alert.timestamp)}</span>
                        {alert.telemetry?.uv_dose_mj_cm2 !== undefined && (
                          <span>UV {Number(alert.telemetry.uv_dose_mj_cm2).toFixed(1)} mJ/cm²</span>
                        )}
                      </div>
                    </div>

                    <ChevronDown
                      size={16}
                      className={`event-chevron ${isExpanded ? "rotated" : ""}`}
                    />
                  </button>

                  {isExpanded && (
                    <div className="event-details">
                      <div className="event-details-grid">
                        {[
                          { label: "UV Dose",    value: alert.telemetry?.uv_dose_mj_cm2,   unit: " mJ/cm²", decimals: 1 },
                          { label: "Lamp Power", value: alert.telemetry?.lamp_power_pct,   unit: "%",       decimals: 1 },
                          { label: "Lamp Health",value: alert.telemetry?.lamp_health_pct,  unit: "%",       decimals: 1 },
                          { label: "Turbidity",  value: alert.telemetry?.turbidity_ntu,    unit: " NTU",    decimals: 2 },
                        ].map(({ label, value, unit, decimals }) => (
                          <div key={label} className="detail-item">
                            <span className="detail-key">{label}</span>
                            <span className="detail-value">
                              {Number.isFinite(Number(value))
                                ? `${Number(value).toFixed(decimals)}${unit}`
                                : "—"}
                            </span>
                          </div>
                        ))}
                      </div>
                      {alert.recommended_action && (
                        <div className="event-detail-action">
                          <strong>Operator guidance</strong>
                          <p>{alert.recommended_action}</p>
                        </div>
                      )}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
