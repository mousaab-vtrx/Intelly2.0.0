import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  AlertTriangle,
  BrainCircuit,
  ClipboardList,
  ExternalLink,
  Eye,
  FileStack,
  FileText,
  ListChecks,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import { API_BASE_URL } from "../api/client";
import { PdfViewer } from "./PdfViewer";

const SIGNAL_LABELS = {
  uv_dose_mj_cm2: "UV Dose",
  lamp_power_pct: "Lamp Power",
  turbidity_ntu: "Turbidity",
  lamp_health_pct: "Lamp Health",
  uvt: "UVT",
};

function reportStats(report) {
  const sections = report?.structured_content?.sections || [];
  const continuity = report?.structured_content?.continuity_notes || [];
  const bullets = sections.reduce((sum, section) => sum + (section.bullets || []).length, 0);

  return [
    { label: "Sections", value: sections.length },
    { label: "Findings", value: bullets },
    { label: "Continuity Notes", value: continuity.length },
  ];
}

export function ReportPanel({
  heading,
  description,
  report,
  isLoading,
  error,
  onGenerate,
  isGenerating,
  generateLabel,
  variant = "default",
  toolAnalysis = null,
  toolAnalysisLoading = false,
  onAssistSelection,
  isAssisting = false,
  assistResult = null,
  assistError = "",
}) {
  const [activeView, setActiveView] = useState("overview");
  const [selectedPreviewText, setSelectedPreviewText] = useState("");

  useEffect(() => {
    setActiveView("overview");
  }, [report?.id]);

  const stats = useMemo(() => reportStats(report), [report]);
  const reportUrl = report ? `${API_BASE_URL}${report.pdf_url}` : "";
  const isDaily = variant === "daily";
  const isCritical = report?.title?.includes("Critical Failure");
  const views = [
    { id: "overview", label: "Overview", icon: FileStack },
    { id: "sections", label: "Findings", icon: ListChecks },
    ...(isDaily ? [{ id: "preview", label: "Preview", icon: Eye }] : []),
  ];
  const overviewHighlights = useMemo(() => {
    const sections = report?.structured_content?.sections || [];
    const icons = isDaily
      ? [ShieldCheck, AlertTriangle, ClipboardList]
      : [AlertTriangle, ClipboardList, ShieldCheck];
    return sections.slice(0, 3).map((section, index) => ({
      heading: section.heading,
      copy: section.bullets?.[0] || "No summary point available for this section yet.",
      Icon: icons[index] || ClipboardList,
    }));
  }, [isDaily, report]);
  const analysisHighlights = useMemo(() => {
    const pyod = toolAnalysis?.pyod || {};
    const prophet = toolAnalysis?.prophet || {};

    return [
      {
        key: "pyod",
        heading: "Anomaly posture",
        copy:
          pyod.summary ||
          (toolAnalysisLoading
            ? "Loading anomaly analysis from current telemetry history."
            : "Anomaly posture will populate when enough telemetry samples are available."),
        Icon: BrainCircuit,
        meta: [
          `Samples ${pyod.sample_size ?? pyod.available_samples ?? 0}`,
          `Score ${Number.isFinite(pyod.decision_score) ? pyod.decision_score.toFixed(3) : "--"}`,
        ],
        bullets: (pyod.leading_signals || []).slice(0, 3).map((signal) => {
          const label = SIGNAL_LABELS[signal.metric] || signal.metric;
          const z = typeof signal.z_score === "number" ? `${signal.z_score > 0 ? "+" : ""}${signal.z_score.toFixed(2)}z` : "--";
          return `${label}: ${z}`;
        }),
      },
      {
        key: "prophet",
        heading: "Forecast outlook",
        copy:
          prophet.summary ||
          (toolAnalysisLoading
            ? "Loading forecast guidance from recent UVT history."
            : "Forecast guidance will populate when enough UVT samples are available."),
        Icon: TrendingUp,
        meta: [
          `Direction ${prophet.direction || "--"}`,
          `Final UVT ${Number.isFinite(prophet.final_forecast_uvt) ? `${prophet.final_forecast_uvt.toFixed(2)}%T` : "--"}`,
        ],
        bullets: [
          typeof prophet.threshold_risk_below_70 === "boolean"
            ? `Risk below 70%T: ${prophet.threshold_risk_below_70 ? "elevated" : "clear"}`
            : "Risk below 70%T: pending",
          `Samples: ${prophet.sample_size ?? prophet.available_samples ?? 0}`,
        ],
      },
    ];
  }, [toolAnalysis, toolAnalysisLoading]);

  useEffect(() => {
    setSelectedPreviewText("");
  }, [report?.id, activeView]);

  return (
    <section className={`report-panel ${isDaily ? "daily-report-experience" : ""}`}>
      <div className="report-panel-header report-hero">
        <div className="report-hero-copy">
          <div className="report-panel-title">
            <FileText size={18} />
            <h2>{heading}</h2>
          </div>
          {description ? <p>{description}</p> : null}
        </div>
        <button
          type="button"
          className="report-action-button"
          onClick={onGenerate}
          disabled={isGenerating}
        >
          <RefreshCw size={16} className={isGenerating ? "spinning" : ""} />
          <span>{isGenerating ? "Working..." : generateLabel}</span>
        </button>
      </div>

      {isLoading ? <div className="report-state">Loading report...</div> : null}
      {error ? <div className="report-state error">{error.message}</div> : null}
      {!isLoading && !error && !report ? (
        <div className="report-state">
          No report is available yet. Generate one to populate this view.
        </div>
      ) : null}

      {report ? (
        <div className="report-workspace">
          <aside className="report-sidebar">
            <div className={`report-summary-card ${isCritical ? "critical-card" : ""}`}>
              <h3 className={`report-document-title ${isCritical ? "critical-title" : ""}`}>{report.title}</h3>
              <p className="report-summary">{report.structured_content?.executive_summary}</p>

              <div className="report-stat-grid">
                {stats.map((stat) => (
                  <div key={stat.label} className="report-stat-card">
                    <strong>{stat.value}</strong>
                    <span>{stat.label}</span>
                  </div>
                ))}
              </div>

              <div className="report-links">
                <a
                  href={reportUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="report-link-button"
                >
                  <ExternalLink size={16} />
                  <span>Open PDF</span>
                </a>
              </div>
            </div>

            <div className="report-view-nav">
              {views.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  type="button"
                  className={`report-view-tab ${activeView === id ? "active" : ""}`}
                  onClick={() => setActiveView(id)}
                >
                  <Icon size={16} />
                  <span>{label}</span>
                </button>
              ))}
            </div>
          </aside>

          <div className="report-stage">
            {activeView === "overview" ? (
              <div className="report-stage-card">
                <div className="report-stage-header">
                  <div>
                    <h3>Executive overview</h3>
                  </div>
                </div>

                {isDaily ? (
                  <div className="daily-overview-grid">
                    {overviewHighlights.map(({ heading, copy, Icon }) => (
                      <article key={heading} className="daily-signal-card">
                        <div className="daily-signal-icon">
                          <Icon size={22} />
                        </div>
                        <div className="daily-signal-copy">
                          <h4>{heading}</h4>
                          <p>{copy}</p>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="report-overview-grid report-overview-grid-active">
                    {overviewHighlights.map(({ heading, copy, Icon }) => (
                      <article key={heading} className="report-card-compact report-card-compact-active">
                        <div className="report-card-compact-top">
                          <span className="report-card-icon">
                            <Icon size={18} />
                          </span>
                          <span className="report-heading">{heading}</span>
                        </div>
                        <p>{copy}</p>
                      </article>
                    ))}
                  </div>
                )}

                {isDaily ? (
                  <div className="daily-overview-grid report-analysis-grid">
                    {analysisHighlights.map(({ key, heading, copy, Icon, meta, bullets }) => (
                      <article key={key} className="daily-signal-card report-analysis-card">
                        <div className="daily-signal-icon">
                          <Icon size={22} />
                        </div>
                        <div className="daily-signal-copy report-analysis-copy">
                          <h4>{heading}</h4>
                          <p>{copy}</p>
                          <div className="report-analysis-meta">
                            {meta.map((item) => (
                              <span key={item} className="analysis-pill">
                                {item}
                              </span>
                            ))}
                          </div>
                          <ul className="report-analysis-points">
                            {bullets.map((bullet) => (
                              <li key={bullet}>{bullet}</li>
                            ))}
                          </ul>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="report-window report-window-active">
                    <div className="report-window-header">
                      <h4>Immediate operator focus</h4>
                    </div>
                    <ul className="report-note-list">
                      {(report.structured_content?.continuity_notes || []).slice(0, 4).map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className={`report-window ${isDaily ? "daily-notes-window" : "report-window-secondary"}`}>
                  <div className="report-window-header">
                    <h4>{isDaily ? "Continuity notes" : "Operational notes"}</h4>
                  </div>
                  <ul className="report-note-list">
                    {(report.structured_content?.continuity_notes || []).map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : null}

            {activeView === "sections" ? (
              <div className="report-stage-card">
                <div className="report-stage-header">
                  <div>
                    <h3>Detailed findings</h3>
                  </div>
                </div>

                <div className="report-section-stack">
                  {(report.structured_content?.sections || []).map((section) => (
                    <section key={section.heading} className="report-section-card">
                      <h4>{section.heading}</h4>
                      <ul>
                        {(section.bullets || []).map((bullet) => (
                          <li key={bullet}>{bullet}</li>
                        ))}
                      </ul>
                    </section>
                  ))}
                </div>
              </div>
            ) : null}

            {activeView === "preview" && isDaily ? (
              <div className="report-stage-card">
                <div className="report-stage-header">
                  <div>
                    <h3>PDF preview</h3>
                    <p>Select text in the preview, then run Review or Explain.</p>
                  </div>
                </div>
                <div className="pdf-selection-assistant">
                  <div className="pdf-selection-summary">
                    <span className="report-type-pill">Selection-aware AI</span>
                    <p>
                      {selectedPreviewText
                        ? selectedPreviewText
                        : "Highlight any text in the PDF preview to enable Review or Explain."}
                    </p>
                  </div>
                  <div className="pdf-selection-actions">
                    {["Review", "Explain"].map((action) => (
                      <button
                        key={action}
                        type="button"
                        className="report-action-button"
                        disabled={!selectedPreviewText || isAssisting}
                        onClick={() =>
                          onAssistSelection?.({
                            reportId: report.id,
                            action: action.toLowerCase(),
                            selectedText: selectedPreviewText,
                          })
                        }
                      >
                        {action}
                      </button>
                    ))}
                  </div>
                  {assistError ? <div className="report-state error">{assistError}</div> : null}
                  {assistResult ? (
                    <div className="report-window ai-action-window">
                      <div className="report-window-header">
                        <h4>{assistResult.action_label}</h4>
                      </div>
                      <div className="ai-action-meta">
                        <span>{assistResult.context_count} context item(s)</span>
                        <span>{assistResult.model}</span>
                      </div>
                      <div className="ai-action-response">
                        <ReactMarkdown>{assistResult.answer}</ReactMarkdown>
                      </div>
                    </div>
                  ) : null}
                </div>
                <div className="report-pdf-card">
                  <PdfViewer
                    fileUrl={reportUrl}
                    title={report.title}
                    onSelectionChange={setSelectedPreviewText}
                  />
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
