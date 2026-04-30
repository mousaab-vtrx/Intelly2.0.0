import { useState } from "react";
import { AlertCircle, Loader } from "lucide-react";

export function DashboardPanel({ panels }) {
  const [loadedPanels, setLoadedPanels] = useState(new Set());
  const [failedPanels, setFailedPanels] = useState(new Set());

  function handlePanelLoad(idx) {
    setLoadedPanels((prev) => new Set([...prev, idx]));
  }

  function handlePanelError(idx) {
    setFailedPanels((prev) => new Set([...prev, idx]));
  }

  return (
    <section className="dashboard-panel">
      <h3>Operational Trend Graphs</h3>
      {panels.length === 0 ? (
        <div className="empty-state">
          <AlertCircle size={40} style={{ color: "#f57c00" }} />
          <p>No dashboard panels configured. Check your Grafana connection.</p>
        </div>
      ) : (
        <div className="dashboard-grid">
          {panels.map((panelUrl, idx) => (
            <div key={idx} className="dashboard-iframe-wrapper">
              {!loadedPanels.has(idx) && !failedPanels.has(idx) && (
                <div className="iframe-loading">
                  <Loader size={32} className="spinner" />
                  <small>Loading panel...</small>
                </div>
              )}
              {failedPanels.has(idx) && (
                <div className="iframe-error">
                  <AlertCircle size={32} style={{ color: "#d32f2f" }} />
                  <small>Failed to load panel</small>
                </div>
              )}
              <iframe
                title={`grafana-panel-${idx}`}
                src={panelUrl}
                frameBorder="0"
                loading="lazy"
                allowFullScreen
                onLoad={() => handlePanelLoad(idx)}
                onError={() => handlePanelError(idx)}
                className="dashboard-iframe"
                style={{ display: failedPanels.has(idx) ? "none" : "block" }}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
