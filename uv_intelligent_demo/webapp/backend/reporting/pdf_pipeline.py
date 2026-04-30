from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Template


def latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "≥": r"$\geq$",
        "≤": r"$\leq$",
        "²": r"$^2$",
        "°": r"$^\circ$",
        "μ": r"$\mu$",
        "Δ": r"$\Delta$",
        "×": r"$\times$",
        "–": "--",
        "—": "---",
    }
    return "".join(replacements.get(char, char) for char in text)


@dataclass
class PipelineArtifacts:
    latex: str
    pdf_path: Path
    tex_path: Path


class PlotAssetTool:
    def __init__(self) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        self.plt = plt

    @staticmethod
    def _safe_number(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _metric_specs(self, telemetry: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "label": "UV Dose",
                "value": self._safe_number(telemetry.get("uv_dose_mj_cm2")),
                "unit": "mJ/cm2",
                "target_min": 40.0,
                "target_max": 100.0,
            },
            {
                "label": "Lamp Power",
                "value": self._safe_number(telemetry.get("lamp_power_pct")),
                "unit": "%",
                "target_min": 60.0,
                "target_max": 100.0,
            },
            {
                "label": "UVT",
                "value": self._safe_number(telemetry.get("uvt")),
                "unit": "%T",
                "target_min": 0.0,
                "target_max": 100.0,
            },
            {
                "label": "Turbidity",
                "value": self._safe_number(telemetry.get("turbidity_ntu")),
                "unit": "NTU",
                "target_min": 0.0,
                "target_max": 2.5,
            },
        ]

    def _deviation_score(self, value: float, target_min: float, target_max: float) -> float:
        if target_min <= value <= target_max:
            return 0.0
        nearest = target_min if value < target_min else target_max
        scale = max(target_max - target_min, abs(target_max), 1.0)
        return min(abs(value - nearest) / scale * 100.0, 100.0)

    def _metrics_overview_plot(self, telemetry: dict[str, Any], outpath: Path) -> None:
        specs = self._metric_specs(telemetry)
        labels = [item["label"] for item in specs]
        positions = list(range(len(specs)))

        fig, ax = self.plt.subplots(figsize=(11.5, 4.8))
        fig.patch.set_facecolor("#fcfbff")
        ax.set_facecolor("#fcfbff")

        for idx, item in enumerate(specs):
            upper = max(item["target_max"] * 1.15, item["value"] * 1.15, 1.0)
            ax.hlines(
                idx,
                item["target_min"],
                item["target_max"],
                color="#efeaff",
                linewidth=12,
                alpha=1.0,
                zorder=1,
            )
            ax.scatter(
                item["value"],
                idx,
                s=180,
                color="#735cff",
                edgecolor="#ffffff",
                linewidth=1.6,
                zorder=3,
            )
            ax.text(
                min(item["value"] + upper * 0.015, upper * 0.96),
                idx + 0.16,
                f"{item['value']:.2f} {item['unit']}",
                fontsize=11,
                color="#221f4b",
                weight="bold",
            )

        x_upper = max(
            max(item["target_max"] * 1.2, item["value"] * 1.25, 1.0)
            for item in specs
        )
        ax.set_xlim(0, x_upper)
        ax.set_yticks(positions)
        ax.set_yticklabels(labels, fontsize=12, color="#221f4b", weight="bold")
        ax.invert_yaxis()
        ax.set_xlabel("Current value against target band", fontsize=12, color="#67618d")
        ax.set_title(
            "Operational metrics overview",
            fontsize=18,
            color="#221f4b",
            weight="bold",
            pad=16,
        )
        ax.grid(axis="x", color="#e7dfff", linewidth=0.8, alpha=0.9)
        ax.tick_params(axis="x", labelsize=11, colors="#67618d")
        for spine in ax.spines.values():
            spine.set_visible(False)
        fig.tight_layout()
        fig.savefig(outpath, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
        self.plt.close(fig)

    def _deviation_plot(self, telemetry: dict[str, Any], alerts: list[dict[str, Any]], outpath: Path) -> None:
        specs = self._metric_specs(telemetry)
        labels = [item["label"] for item in specs]
        values = [
            self._deviation_score(item["value"], item["target_min"], item["target_max"])
            for item in specs
        ]
        colors = ["#45d1bb" if value == 0 else "#ff5c7c" for value in values]
        high_alerts = sum(1 for alert in alerts if alert.get("level") == "high")
        medium_alerts = sum(1 for alert in alerts if alert.get("level") == "medium")

        fig, ax = self.plt.subplots(figsize=(11.5, 4.6))
        fig.patch.set_facecolor("#fcfbff")
        ax.set_facecolor("#fcfbff")
        bars = ax.bar(labels, values, color=colors, edgecolor="#25193f", linewidth=0.8)
        ax.set_ylim(0, max(100, max(values, default=0) + 15))
        ax.set_ylabel("Deviation from target (%)", fontsize=12, color="#67618d")
        ax.set_title(
            "Deviation profile and alert pressure",
            fontsize=18,
            color="#221f4b",
            weight="bold",
            pad=16,
        )
        ax.grid(axis="y", color="#e7dfff", linewidth=0.8, alpha=0.9)
        ax.tick_params(axis="x", labelrotation=0, labelsize=11, colors="#67618d")
        ax.tick_params(axis="y", labelsize=11, colors="#67618d")
        for spine in ax.spines.values():
            spine.set_visible(False)

        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + 2.5,
                f"{value:.1f}",
                ha="center",
                va="bottom",
                fontsize=11,
                color="#221f4b",
                weight="bold",
            )

        ax.text(
            0.99,
            0.95,
            f"High alerts: {high_alerts}   Medium alerts: {medium_alerts}",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=11,
            color="#67618d",
            bbox={
                "facecolor": "#ffffff",
                "edgecolor": "#e7dfff",
                "boxstyle": "round,pad=0.35",
            },
        )

        fig.tight_layout()
        fig.savefig(outpath, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
        self.plt.close(fig)

    def generate(self, telemetry: dict[str, Any], alerts: list[dict[str, Any]], outdir: Path) -> dict[str, Path]:
        metrics_path = outdir / "metrics-overview.png"
        deviation_path = outdir / "metrics-deviation.png"
        self._metrics_overview_plot(telemetry, metrics_path)
        self._deviation_plot(telemetry, alerts, deviation_path)
        return {
            "metrics_overview": metrics_path,
            "metrics_deviation": deviation_path,
        }


class LatexGenerationTool:
    TEMPLATE = Template(
        r"""
\documentclass[11pt]{article}
\usepackage[margin=0.72in]{geometry}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[scaled=0.98]{helvet}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{enumitem}
\usepackage{tabularx}
\usepackage{array}
\usepackage[table]{xcolor}
\usepackage{parskip}
\setlength{\parindent}{0pt}
\renewcommand{\familydefault}{\sfdefault}

\definecolor{ink}{HTML}{221F4B}
\definecolor{panel}{HTML}{FCFBFF}
\definecolor{panelsoft}{HTML}{F3EFFF}
\definecolor{line}{HTML}{E7DFFF}
\definecolor{accent}{HTML}{735CFF}
\definecolor{accentstrong}{HTML}{5E45F6}
\definecolor{mint}{HTML}{45D1BB}
\definecolor{textmuted}{HTML}{67618D}
\definecolor{danger}{HTML}{FF5C7C}

{% raw %}
\newcommand{\panelbox}[1]{
  \noindent
  \fcolorbox{line}{panel}{
    \parbox{\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}{#1}
  }
}
\newcommand{\sectionline}{
  \vspace{0.25em}
  {\color{line}\rule{\linewidth}{1pt}}
  \vspace{0.45em}
}
{% endraw %}

\begin{document}
\thispagestyle{empty}
\pagecolor{panel}

\noindent
\colorbox{ink}{
  \parbox{\dimexpr\linewidth-2\fboxsep\relax}{
    \vspace{10pt}
    {\color{white}\sffamily\bfseries\LARGE {{ title }}}\\[4pt]
    {\color{mint}\sffamily\large UV Ops Center guidance package}\\[4pt]
    {\color{white}\sffamily\small {{ report_type_label }} \hfill Generated {{ created_at }}}\\[2pt]
    {\color{white}\sffamily\small Trigger: {{ generation_reason }}}
    \vspace{10pt}
  }
}

\vspace{0.75em}
\panelbox{
  {\sffamily\bfseries\large\color{ink} Executive Summary}\\[6pt]
  {\color{mint}\rule{0.23\linewidth}{2.2pt}}\\[8pt]
  {\sffamily\color{textmuted} {{ summary }}}
}

\vspace{0.8em}
{\sffamily\bfseries\large\color{ink} Review Snapshot}
\sectionline

\renewcommand{\arraystretch}{1.3}
\begin{tabularx}{\linewidth}{|>{\raggedright\arraybackslash}X|>{\raggedright\arraybackslash}X|>{\raggedright\arraybackslash}X|}
\hline
\rowcolor{accentstrong}
\textcolor{white}{\textbf{Mode}} & \textcolor{white}{\textbf{Queued Tasks}} & \textcolor{white}{\textbf{Alert Focus}} \\
\hline
\cellcolor{panelsoft}\textcolor{ink}{\textbf{ {{ report_type_label }} }} &
\cellcolor{panelsoft}\textcolor{ink}{\textbf{ {{ queued_task_summary }} }} &
\cellcolor{panelsoft}\textcolor{ink}{\textbf{ {{ alert_focus }} }} \\
\hline
\end{tabularx}

\vspace{0.8em}
\panelbox{
  {\sffamily\bfseries\large\color{ink} Direct Guidance}\\[6pt]
  {\color{accent}\rule{0.2\linewidth}{2.2pt}}\\[8pt]
  {\sffamily\color{textmuted} The following operator-ready steps were compiled from the reviewed telemetry, alert history, retrieved evidence, and scheduled work context.}\\[8pt]
  \begin{enumerate}[leftmargin=1.45em, itemsep=0.55em, topsep=0.25em]
  {% for step in guidance_steps %}
  \item {\sffamily\color{textmuted} {{ step }}}
  {% endfor %}
  \end{enumerate}
}

{% if alert_briefs %}
\vspace{0.8em}
\panelbox{
  {\sffamily\bfseries\large\color{ink} Alert Watch}\\[6pt]
  \begin{itemize}[leftmargin=1.3em, itemsep=0.45em, topsep=0.25em]
  {% for alert in alert_briefs %}
  \item {\sffamily\color{textmuted} {{ alert }}}
  {% endfor %}
  \end{itemize}
}
{% endif %}

{% if task_briefs %}
\vspace{0.8em}
\panelbox{
  {\sffamily\bfseries\large\color{ink} Scheduled Task Context}\\[6pt]
  \begin{itemize}[leftmargin=1.3em, itemsep=0.45em, topsep=0.25em]
  {% for task in task_briefs %}
  \item {\sffamily\color{textmuted} {{ task }}}
  {% endfor %}
  \end{itemize}
}
{% endif %}

\vspace{0.8em}
{\sffamily\bfseries\large\color{ink} Live Snapshot}
\sectionline

\renewcommand{\arraystretch}{1.3}
\begin{tabularx}{\linewidth}{|>{\raggedright\arraybackslash}X|>{\raggedright\arraybackslash}X|>{\raggedright\arraybackslash}X|}
\hline
\rowcolor{accentstrong}
\textcolor{white}{\textbf{Metric}} & \textcolor{white}{\textbf{Current}} & \textcolor{white}{\textbf{Target}} \\
\hline
{% for metric in metrics %}
\cellcolor{panelsoft}\textcolor{textmuted}{\textbf{ {{ metric.label }} }} &
\cellcolor{panelsoft}\textcolor{ink}{\textbf{ {{ metric.value }} }} &
\cellcolor{panelsoft}\textcolor{textmuted}{ {{ metric.target }} } \\
\hline
{% endfor %}
\end{tabularx}

\vspace{0.8em}
\panelbox{
  {\sffamily\bfseries\large\color{ink} Plot 1: Current values against target bands}\\[4pt]
  {\color{accent}\rule{0.18\linewidth}{2.2pt}}\\[8pt]
  {\sffamily\color{textmuted} A compact view of how each live metric sits relative to the intended operating band.}\\[8pt]
  \includegraphics[width=\linewidth,height=0.29\textheight,keepaspectratio]{ {{ metrics_plot }} }
}

\vspace{0.8em}
\panelbox{
  {\sffamily\bfseries\large\color{ink} Plot 2: Deviation profile}\\[4pt]
  {\color{danger}\rule{0.18\linewidth}{2.2pt}}\\[8pt]
  {\sffamily\color{textmuted} Deviation pressure helps prioritize which variables need the most immediate operator attention.}\\[8pt]
  \includegraphics[width=\linewidth,height=0.29\textheight,keepaspectratio]{ {{ deviation_plot }} }
}

\clearpage

{% for section in sections %}
\panelbox{
  {\sffamily\bfseries\Large\color{ink} {{ section.heading }}}\\[6pt]
  {\color{accent}\rule{0.16\linewidth}{2pt}}\\[8pt]
  \begin{itemize}[leftmargin=1.3em, itemsep=0.45em, topsep=0.25em]
  {% for bullet in section.bullets %}
  \item {\sffamily\color{textmuted} {{ bullet }}}
  {% endfor %}
  \end{itemize}
}
\vspace{0.8em}
{% endfor %}

\panelbox{
  {\sffamily\bfseries\Large\color{ink} Continuity Notes}\\[6pt]
  {\color{mint}\rule{0.18\linewidth}{2pt}}\\[8pt]
  \begin{itemize}[leftmargin=1.3em, itemsep=0.45em, topsep=0.25em]
  {% for note in continuity_notes %}
  \item {\sffamily\color{textmuted} {{ note }}}
  {% endfor %}
  \end{itemize}
}

\vspace{0.8em}
\panelbox{
  {\sffamily\bfseries\Large\color{ink} Sources}\\[6pt]
  {\color{line}\rule{0.14\linewidth}{2pt}}\\[8pt]
  \begin{itemize}[leftmargin=1.3em, itemsep=0.45em, topsep=0.25em]
  {% for source in sources %}
  \item {\sffamily\color{textmuted} {{ source }}}
  {% endfor %}
  \end{itemize}
}

\end{document}
        """.strip()
    )

    @staticmethod
    def _format_metric_value(value: Any, unit: str, digits: int = 1) -> str:
        try:
            return f"{float(value):.{digits}f} {unit}".strip()
        except (TypeError, ValueError):
            return f"N/A {unit}".strip()

    def _build_metrics(self, metadata: dict[str, Any]) -> list[dict[str, str]]:
        telemetry = metadata.get("telemetry_snapshot", {}) or {}
        return [
            {
                "label": latex_escape("UV Dose"),
                "value": latex_escape(self._format_metric_value(telemetry.get("uv_dose_mj_cm2"), "mJ/cm2", 1)),
                "target": latex_escape("Target 40-100 mJ/cm2"),
            },
            {
                "label": latex_escape("Lamp Power"),
                "value": latex_escape(self._format_metric_value(telemetry.get("lamp_power_pct"), "%", 1)),
                "target": latex_escape("Target 60-100%"),
            },
            {
                "label": latex_escape("UVT"),
                "value": latex_escape(self._format_metric_value(telemetry.get("uvt"), "%T", 1)),
                "target": latex_escape("Target 0-100%T"),
            },
            {
                "label": latex_escape("Turbidity"),
                "value": latex_escape(self._format_metric_value(telemetry.get("turbidity_ntu"), "NTU", 2)),
                "target": latex_escape("Target 0-2.5 NTU"),
            },
        ]

    @staticmethod
    def _section_bullets(structured_content: dict[str, Any], *keywords: str) -> list[str]:
        for section in structured_content.get("sections", []):
            heading = str(section.get("heading", "")).lower()
            if any(keyword in heading for keyword in keywords):
                return [str(item) for item in section.get("bullets", []) if item]
        return []

    def _build_guidance_steps(
        self,
        structured_content: dict[str, Any],
        metadata: dict[str, Any],
    ) -> list[str]:
        steps = self._section_bullets(structured_content, "recommended", "action", "guidance")
        if not steps:
            steps = [
                "Review the latest operational status, risk summary, and continuity notes before issuing operator direction."
            ]

        alerts_snapshot = metadata.get("alerts_snapshot", []) or []
        if alerts_snapshot:
            highest_alert = alerts_snapshot[-1]
            recommended_action = highest_alert.get("recommended_action")
            if recommended_action:
                steps.append(f"Address the latest alert recommendation directly: {recommended_action}")

        scheduled_tasks_count = metadata.get("scheduled_tasks_count", 0)
        if scheduled_tasks_count:
            steps.append(
                f"Align the final operator direction with {scheduled_tasks_count} queued orchestration task(s) so field work matches the reviewed system state."
            )

        return [latex_escape(step) for step in steps[:6]]

    def _build_alert_briefs(self, metadata: dict[str, Any]) -> list[str]:
        briefs: list[str] = []
        for alert in (metadata.get("alerts_snapshot", []) or [])[-4:]:
            level = str(alert.get("level", "info")).upper()
            message = str(alert.get("message", "No alert message")).strip()
            action = str(alert.get("recommended_action", "")).strip()
            if action:
                briefs.append(latex_escape(f"{level}: {message} Recommended response: {action}"))
            else:
                briefs.append(latex_escape(f"{level}: {message}"))
        return briefs

    def _build_task_briefs(self, metadata: dict[str, Any]) -> list[str]:
        briefs: list[str] = []
        for task in metadata.get("scheduled_tasks_snapshot", []) or []:
            text = str(task.get("text", "Queued task")).strip()
            status = str(task.get("status", "scheduled")).replace("_", " ").strip()
            briefs.append(latex_escape(f"{text} (status: {status})"))
        return briefs

    @staticmethod
    def _report_type_label(report_type: str) -> str:
        if report_type == "daily_full_report":
            return "Daily guidance report"
        if report_type == "notification_report":
            return "Incident guidance report"
        return "Operational guidance report"

    @staticmethod
    def _alert_focus(metadata: dict[str, Any]) -> str:
        alerts_snapshot = metadata.get("alerts_snapshot", []) or []
        if not alerts_snapshot:
            return "No active high-priority alert"
        latest = alerts_snapshot[-1]
        return str(latest.get("category", latest.get("level", "review required"))).replace("_", " ").title()

    def render(
        self,
        structured_content: dict[str, Any],
        metadata: dict[str, Any],
        plot_paths: dict[str, Path],
    ) -> str:
        sanitized_sections = []
        for section in structured_content.get("sections", []):
            sanitized_sections.append(
                {
                    "heading": latex_escape(section.get("heading", "Section")),
                    "bullets": [latex_escape(item) for item in section.get("bullets", [])],
                }
            )
        return self.TEMPLATE.render(
            title=latex_escape(metadata["title"]),
            created_at=latex_escape(metadata["timestamp"]),
            report_type_label=latex_escape(self._report_type_label(str(metadata.get("type", "")))),
            generation_reason=latex_escape(str(metadata.get("generation_reason", "scheduled or operator initiated"))),
            queued_task_summary=latex_escape(f"{metadata.get('scheduled_tasks_count', 0)} queued task(s)"),
            alert_focus=latex_escape(self._alert_focus(metadata)),
            summary=latex_escape(structured_content.get("executive_summary", "")),
            sections=sanitized_sections,
            continuity_notes=[latex_escape(item) for item in structured_content.get("continuity_notes", [])],
            sources=[latex_escape(item) for item in structured_content.get("sources", [])],
            guidance_steps=self._build_guidance_steps(structured_content, metadata),
            alert_briefs=self._build_alert_briefs(metadata),
            task_briefs=self._build_task_briefs(metadata),
            metrics=self._build_metrics(metadata),
            metrics_plot=plot_paths["metrics_overview"].as_posix(),
            deviation_plot=plot_paths["metrics_deviation"].as_posix(),
        )


class LatexValidationTool:
    REQUIRED_BLOCKS = (r"\documentclass", r"\begin{document}", r"\end{document}")

    def validate(self, latex: str) -> list[str]:
        errors: list[str] = []
        for block in self.REQUIRED_BLOCKS:
            if block not in latex:
                errors.append(f"Missing required LaTeX block: {block}")
        if latex.count("{") != latex.count("}"):
            errors.append("Mismatched brace count detected.")
        if re.search(r"\\item\s*$", latex, re.MULTILINE):
            errors.append("Empty list item detected.")
        return errors


class PdfCompilationTool:
    def __init__(self) -> None:
        self.compiler = shutil.which("tectonic") or shutil.which("latexmk") or shutil.which("pdflatex")

    def compile(self, latex: str, workdir: Path) -> tuple[Path, str]:
        if not self.compiler:
            raise RuntimeError("No LaTeX compiler available. Install tectonic, latexmk, or pdflatex.")

        tex_file = workdir / "report.tex"
        tex_file.write_text(latex, encoding="utf-8")

        if self.compiler.endswith("tectonic"):
            command = [self.compiler, "--keep-logs", "--outdir", str(workdir), str(tex_file)]
        elif self.compiler.endswith("latexmk"):
            command = [self.compiler, "-pdf", "-interaction=nonstopmode", "-output-directory=" + str(workdir), str(tex_file)]
        else:
            command = [self.compiler, "-interaction=nonstopmode", "-output-directory", str(workdir), str(tex_file)]

        result = subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stdout + "\n" + result.stderr)

        pdf_file = workdir / "report.pdf"
        if not pdf_file.exists():
            raise RuntimeError("PDF compiler finished without producing report.pdf")
        return pdf_file, result.stdout + "\n" + result.stderr


class FileStorageTool:
    def __init__(self, artifacts_dir: Path) -> None:
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def store(self, report_id: str, latex: str, pdf_source: Path) -> tuple[Path, Path]:
        report_dir = self.artifacts_dir / report_id
        report_dir.mkdir(parents=True, exist_ok=True)
        tex_path = report_dir / "report.tex"
        pdf_path = report_dir / "report.pdf"
        tex_path.write_text(latex, encoding="utf-8")
        shutil.copy2(pdf_source, pdf_path)
        return tex_path, pdf_path


class LatexPdfPipeline:
    def __init__(self, artifacts_dir: Path) -> None:
        self.generator = LatexGenerationTool()
        self.validator = LatexValidationTool()
        self.compiler = PdfCompilationTool()
        self.storage = FileStorageTool(artifacts_dir)
        self.plotter = PlotAssetTool()

    def run(self, report_id: str, structured_content: dict[str, Any], metadata: dict[str, Any]) -> PipelineArtifacts:
        with tempfile.TemporaryDirectory(prefix=f"report-{report_id}-") as tempdir:
            workdir = Path(tempdir)
            plot_paths = self.plotter.generate(
                metadata.get("telemetry_snapshot", {}) or {},
                metadata.get("alerts_snapshot", []) or [],
                workdir,
            )
            latex = self.generator.render(structured_content, metadata, plot_paths)
            errors = self.validator.validate(latex)
            if errors:
                raise RuntimeError("; ".join(errors))

            pdf_file, _logs = self.compiler.compile(latex, workdir)
            tex_path, pdf_path = self.storage.store(report_id, latex, pdf_file)
        return PipelineArtifacts(latex=latex, pdf_path=pdf_path, tex_path=tex_path)
