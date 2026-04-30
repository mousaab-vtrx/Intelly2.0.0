import {
  Activity,
  AlertTriangle,
  Calendar,
  Bot,
  Briefcase,
  Menu,
  FileText,
  X,
} from "lucide-react";

export function Sidebar({
  collapsed,
  onToggle,
  activeSection,
  onSelectSection,
  copilotOpen,
  onToggleCopilot,
}) {
  const navItems = [
    { id: "telemetry", label: "Overview", icon: Activity },
    { id: "alerts", label: "Alerts & Incidents", icon: AlertTriangle },
    { id: "reports", label: "Reports", icon: FileText },
    { id: "daily-report", label: "Daily Report", icon: Calendar },
    { id: "planning", label: "Orchestrator", icon: Briefcase },
    { id: "copilot-toggle", label: copilotOpen ? "Hide Copilot" : "Show Copilot", icon: Bot },
  ];

  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="sidebar-header">
        <button className="sidebar-toggle" onClick={onToggle} aria-label="Toggle sidebar">
          {collapsed ? <Menu size={18} /> : <X size={18} />}
        </button>
      </div>

      {!collapsed && (
        <div className="sidebar-brand">
          <h1>intelly</h1>
          <p>Reactor data simplified</p>
        </div>
      )}

      <nav className="sidebar-nav">
        {navItems.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => (id === "copilot-toggle" ? onToggleCopilot() : onSelectSection(id))}
            className={`nav-item ${
              id === "copilot-toggle"
                ? copilotOpen
                  ? "active"
                  : ""
                : activeSection === id
                  ? "active"
                  : ""
            }`}
            title={label}
            aria-label={label}
          >
            <Icon size={20} className="nav-icon" />
            {!collapsed && <span>{label}</span>}
          </button>
        ))}
      </nav>


    </aside>
  );
}
