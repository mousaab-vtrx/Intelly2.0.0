import { Activity, AlertTriangle, CalendarDays, FileText, ArrowRight } from "lucide-react";

function formatDate(value) {
  if (!value) return "Not generated yet";
  return new Date(value).toLocaleString();
}

export function OverviewPanel({
  telemetry,
  alerts,
  activeReport,
  dailyReport,
  onOpenSection,
}) {
  const highAlerts = alerts.filter((alert) => alert.level === "high").length;

  const quickLinks = [
    {
      id: "telemetry",
      title: "Live telemetry",
      description: "Monitor dose, lamp health, UVT, turbidity, and anomaly trends in real time.",
      meta: telemetry?.uv_dose_mj_cm2 ? `${telemetry.uv_dose_mj_cm2.toFixed(1)} mJ/cm² latest` : "Waiting for telemetry",
      icon: Activity,
    },
    {
      id: "alerts",
      title: "Alerts and events",
      description: "Review notable changes, priority alarms, and operational context without scanning the whole dashboard.",
      meta: `${alerts.length} recent alerts • ${highAlerts} high priority`,
      icon: AlertTriangle,
    },
    {
      id: "reports",
      title: "Active report",
      description: "Open the lightweight report workspace with overview, findings, and PDF preview separated into steps.",
      meta: formatDate(activeReport?.created_at),
      icon: FileText,
    },
    {
      id: "daily-report",
      title: "Daily report",
      description: "Review the full daily narrative and supporting PDF in a calmer, paged layout.",
      meta: formatDate(dailyReport?.created_at),
      icon: CalendarDays,
    },
  ];

  return (
    <section className="overview-panel">
      <div className="overview-hero">
        <div className="overview-copy">
          <span className="overview-kicker">Operations cockpit</span>
          <h2>Start from the signal, then drill into detail only when you need it.</h2>
          <p>
            The workspace is split into lighter views so operators can orient quickly, review
            reports in stages, and keep the PDF preview available without overwhelming the first screen.
          </p>
        </div>
        <div className="overview-highlight">
          <div className="overview-highlight-label">System posture</div>
          <strong>{highAlerts > 0 ? "Attention needed" : "Nominal tracking"}</strong>
          <span>
            {highAlerts > 0
              ? `${highAlerts} high-priority alert${highAlerts === 1 ? "" : "s"} need review`
              : "No critical alerts in the current window"}
          </span>
        </div>
      </div>

      <div className="overview-grid">
        {quickLinks.map(({ id, title, description, meta, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className="overview-card"
            onClick={() => onOpenSection(id)}
          >
            <div className="overview-card-top">
              <div className="overview-card-icon">
                <Icon size={18} />
              </div>
              <ArrowRight size={16} />
            </div>
            <h3>{title}</h3>
            <p>{description}</p>
            <span>{meta}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
