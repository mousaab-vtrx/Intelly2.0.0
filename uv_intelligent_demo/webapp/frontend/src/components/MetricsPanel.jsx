import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, Gauge, Eye, Droplets, RotateCcw, ZoomIn, ZoomOut } from "lucide-react";

const MIN_WINDOW_SIZE = 20;
const WINDOW_STEP = 10;

function InteractiveTrendChart({
  title,
  subtitle,
  points = [],
  color = "#9d7de7",
  unit = "",
  threshold = null,
  invertThreshold = false,
}) {
  const [windowSize, setWindowSize] = useState(60);
  const [offset, setOffset] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [hoverIndex, setHoverIndex] = useState(null);
  const dragStartX = useRef(0);
  const dragStartOffset = useRef(0);
  const pointerIdRef = useRef(null);

  const safeSeries = useMemo(
    () =>
      points.filter(
        (item) => item && Number.isFinite(item.value) && item.label !== undefined && item.label !== null
      ),
    [points]
  );
  const maxWindowSize = Math.max(MIN_WINDOW_SIZE, safeSeries.length || 180);
  const maxOffset = Math.max(safeSeries.length - windowSize, 0);
  const currentOffset = Math.max(0, Math.min(offset, maxOffset));
  const visible = safeSeries.slice(currentOffset, currentOffset + windowSize);

  useEffect(() => {
    setWindowSize((prev) => Math.max(MIN_WINDOW_SIZE, Math.min(prev, maxWindowSize)));
  }, [maxWindowSize]);

  useEffect(() => {
    setOffset((prev) => Math.max(0, Math.min(prev, maxOffset)));
  }, [maxOffset]);

  function updateHoverIndex(clientX, rect) {
    const ratio = Math.max(0, Math.min((clientX - rect.left) / rect.width, 1));
    const idx = Math.round(ratio * Math.max(visible.length - 1, 0));
    setHoverIndex(idx);
  }

  function resizeWindow(direction) {
    setWindowSize((prev) =>
      Math.max(MIN_WINDOW_SIZE, Math.min(maxWindowSize, prev + direction * WINDOW_STEP))
    );
  }

  function onWheel(event) {
    event.preventDefault();
    const direction = event.deltaY > 0 ? 1 : -1;
    resizeWindow(direction);
  }

  function onPointerDown(event) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    updateHoverIndex(event.clientX, event.currentTarget.getBoundingClientRect());
    if (safeSeries.length <= windowSize) return;
    setDragging(true);
    pointerIdRef.current = event.pointerId;
    dragStartX.current = event.clientX;
    dragStartOffset.current = currentOffset;
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    updateHoverIndex(event.clientX, rect);

    if (!dragging || pointerIdRef.current !== event.pointerId) return;
    const deltaX = event.clientX - dragStartX.current;
    const shift = Math.round(-deltaX / 8);
    setOffset(Math.max(0, Math.min(maxOffset, dragStartOffset.current + shift)));
  }

  function onPointerUp(event) {
    if (
      pointerIdRef.current !== null &&
      event.currentTarget.hasPointerCapture?.(pointerIdRef.current)
    ) {
      event.currentTarget.releasePointerCapture(pointerIdRef.current);
    }
    pointerIdRef.current = null;
    setDragging(false);
  }

  if (!visible.length) {
    return (
      <div className="trend-card">
        <div className="trend-header">
          <strong>{title}</strong>
          <small>{subtitle}</small>
        </div>
        <div className="trend-empty">Collecting trend data...</div>
      </div>
    );
  }

  const width = 420;
  const height = 170;
  const values = visible.map((item) => item.value);
  const minCandidate = Math.min(...values);
  const maxCandidate = Math.max(...values);
  const min = threshold !== null && Number.isFinite(threshold) ? Math.min(minCandidate, threshold) : minCandidate;
  const max = threshold !== null && Number.isFinite(threshold) ? Math.max(maxCandidate, threshold) : maxCandidate;
  const range = max - min || 1;
  const stepX = width / Math.max(values.length - 1, 1);
  const linePoints = values.map((value, index) => {
    const x = index * stepX;
    const y = height - ((value - min) / range) * height;
    return `${x},${y}`;
  });
  const activeIndex = hoverIndex !== null ? Math.max(0, Math.min(hoverIndex, visible.length - 1)) : null;
  const activeValue = activeIndex !== null ? visible[activeIndex] : null;
  const crossX = activeIndex !== null ? activeIndex * stepX : null;
  const crossY =
    activeValue !== null ? height - ((activeValue.value - min) / range) * height : null;
  const thresholdY =
    threshold !== null && Number.isFinite(threshold)
      ? height - ((threshold - min) / range) * height
      : null;
  const thresholdInRange = thresholdY !== null && thresholdY >= 0 && thresholdY <= height;
  const shadeAbove = invertThreshold;

  return (
    <div className="trend-card">
      <div className="trend-header-row">
        <div className="trend-header">
          <strong>{title}</strong>
          {subtitle ? <small>{subtitle}</small> : null}
        </div>
        <div className="trend-toolbar" aria-label={`${title} controls`}>
          <button type="button" className="trend-toolbar-button" onClick={() => resizeWindow(-1)} title="Zoom in">
            <ZoomIn size={16} />
          </button>
          <button type="button" className="trend-toolbar-button" onClick={() => resizeWindow(1)} title="Zoom out">
            <ZoomOut size={16} />
          </button>
          <button
            type="button"
            className="trend-toolbar-button"
            onClick={() => {
              setWindowSize(Math.min(maxWindowSize, 60));
              setOffset(0);
            }}
            title="Reset view"
          >
            <RotateCcw size={16} />
          </button>
        </div>
      </div>
      <div className="trend-meta">
        <span>min: {min.toFixed(2)}{unit}</span>
        <span>max: {max.toFixed(2)}{unit}</span>
        <span>window: {visible.length} pts</span>
        {threshold !== null && <span>threshold: {threshold.toFixed(2)}{unit}</span>}
      </div>
      <div
        className={`interactive-trend-surface ${dragging ? "dragging" : ""}`}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onLostPointerCapture={onPointerUp}
        onPointerLeave={() => {
          if (!dragging) {
            setHoverIndex(null);
          }
        }}
      >
        <svg className="trend-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
          {thresholdInRange && (
            <>
              <rect
                x={0}
                y={shadeAbove ? 0 : thresholdY}
                width={width}
                height={shadeAbove ? thresholdY : Math.max(height - thresholdY, 0)}
                className="trend-anomaly-band"
              />
              <line x1={0} x2={width} y1={thresholdY} y2={thresholdY} className="trend-threshold-line" />
            </>
          )}
          {crossX !== null && (
            <line
              x1={crossX}
              x2={crossX}
              y1={0}
              y2={height}
              className="trend-crosshair"
            />
          )}
          <polyline
            fill="none"
            stroke={color}
            strokeWidth="2.4"
            strokeLinejoin="round"
            strokeLinecap="round"
            points={linePoints.join(" ")}
          />
          {crossX !== null && crossY !== null && (
            <circle cx={crossX} cy={crossY} r="3.5" className="trend-point-marker" />
          )}
        </svg>
        {activeValue && (
          <div className="trend-tooltip">
            <div>{activeValue.label}</div>
            <strong>{activeValue.value.toFixed(2)}{unit}</strong>
          </div>
        )}
      </div>
    </div>
  );
}

export function MetricsPanel({
  telemetry,
  telemetryHistory = [],
}) {
  const metrics = [
    {
      label: "UV Dose",
      value: telemetry.uv_dose_mj_cm2,
      unit: "mJ/cm²",
      icon: Activity,
      threshold: { min: 40, max: 100 },
    },
    {
      label: "Lamp Power",
      value: telemetry.lamp_power_pct,
      unit: "%",
      icon: Gauge,
      threshold: { min: 60, max: 100 },
    },
    {
      label: "UVT",
      value: telemetry.uvt,
      unit: "%T",
      icon: Eye,
      threshold: { min: 0, max: 100 },
    },
    {
      label: "Turbidity",
      value: telemetry.turbidity_ntu,
      unit: "NTU",
      icon: Droplets,
      threshold: { min: 0, max: 2.5 },
    },
  ];

  function formatValue(value, digits = 1) {
    if (value === null || value === undefined || value === "") return "--";
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits) : "--";
  }

  function getStatusClass(value, threshold) {
    if (value === null || value === undefined || !threshold) return "nominal";
    const num = Number(value);
    if (!Number.isFinite(num)) return "nominal";
    if (num < threshold.min || num > threshold.max) return "alert";
    return "nominal";
  }

  function buildSeries(key) {
    return telemetryHistory
      .map((item, idx) => {
        const rawValue = Number(item?.[key]);
        if (!Number.isFinite(rawValue)) return null;
        const labelSource = item?.recorded_at || item?.ts || item?.timestamp || item?.source_timestamp;
        const label = labelSource ? new Date(labelSource).toLocaleTimeString() : `sample ${idx + 1}`;
        return { value: rawValue, label };
      })
      .filter(Boolean)
      .slice(-360);
  }

  const uvDoseTrend = buildSeries("uv_dose_mj_cm2");
  const lampPowerTrend = buildSeries("lamp_power_pct");
  const turbidityTrend = buildSeries("turbidity_ntu");
  return (
    <section className="metrics-panel">
      <div className="metrics-grid">
        {metrics.map((metric) => {
          const Icon = metric.icon;
          const status = getStatusClass(metric.value, metric.threshold);
          return (
            <div key={metric.label} className={`metric-card ${status}`}>
              <div className="metric-header">
                <div className="metric-icon-container">
                  <Icon size={20} />
                </div>
                <div>
                  <div className="metric-label">{metric.label}</div>
                </div>
              </div>
              <div className="metric-value">
                {formatValue(metric.value)}
                <span className="metric-unit">{metric.unit}</span>
              </div>
              <div className="metric-range">
                <small>Target: {metric.threshold.min}–{metric.threshold.max} {metric.unit}</small>
              </div>
            </div>
          );
        })}
      </div>

      <div className="trend-grid">
        <InteractiveTrendChart
          title="UV Dose Trend"
          subtitle=""
          points={uvDoseTrend}
          color="#735cff"
          unit=" mJ/cm²"
          threshold={40}
          invertThreshold={false}
        />
        <InteractiveTrendChart
          title="Lamp Power Trend"
          subtitle=""
          points={lampPowerTrend}
          color="#3fcbb6"
          unit="%"
          threshold={60}
          invertThreshold={false}
        />
        <InteractiveTrendChart
          title="Turbidity Trend"
          subtitle=""
          points={turbidityTrend}
          color="#56d8c3"
          unit=" NTU"
          threshold={2.5}
          invertThreshold={true}
        />
      </div>
    </section>
  );
}
