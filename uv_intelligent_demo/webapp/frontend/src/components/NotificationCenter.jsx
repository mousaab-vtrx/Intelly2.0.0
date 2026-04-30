import { CalendarDays, FileText, RefreshCw } from "lucide-react";

function formatTimestamp(value) {
  if (!value) return "Not generated yet";
  return new Date(value).toLocaleString();
}

function CompactReportCard({ label, report, onOpen, onGenerate, isGenerating }) {
  return (
    <article className="report-card-compact">
      <div className="report-card-compact-top">
        <div className="report-card-label">
          <FileText size={15} />
          <strong>{label}</strong>
        </div>
        <button
          type="button"
          className="report-card-button"
          onClick={onGenerate}
          disabled={isGenerating}
        >
          <RefreshCw size={14} className={isGenerating ? "spinning" : ""} />
        </button>
      </div>

      <h4>{report?.title || "No report available"}</h4>
      <p>{report?.structured_content?.executive_summary || "Generate a report to populate this panel."}</p>
      <div className="report-card-footer">
        <span>
          <CalendarDays size={14} />
          {formatTimestamp(report?.created_at)}
        </span>
        <button type="button" className="report-inline-link" onClick={onOpen}>
          Open
        </button>
      </div>
    </article>
  );
}

export function NotificationCenter({
  activeReport,
  dailyReport,
  onOpenActive,
  onOpenDaily,
  onGenerateActive,
  onGenerateDaily,
  isGeneratingActive,
  isGeneratingDaily,
}) {
  return (
    <section className="report-window">
      <div className="report-window-header">
        <div className="report-heading">
          <FileText size={16} />
          <strong>Reports</strong>
        </div>
      </div>
      <div className="report-overview-grid">
        <CompactReportCard
          label="Active Notification"
          report={activeReport}
          onOpen={onOpenActive}
          onGenerate={onGenerateActive}
          isGenerating={isGeneratingActive}
        />
        <CompactReportCard
          label="Daily Full Report"
          report={dailyReport}
          onOpen={onOpenDaily}
          onGenerate={onGenerateDaily}
          isGenerating={isGeneratingDaily}
        />
      </div>
    </section>
  );
}
