from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
from prophet import Prophet
from pyod.models.iforest import IForest


NUMERIC_COLUMNS = (
    "flow_m3h",
    "turbidity_ntu",
    "uvt",
    "lamp_power_pct",
    "uv_intensity",
    "uv_dose_mj_cm2",
    "lamp_health_pct",
    "anomaly_score",
)


@dataclass
class ToolOutput:
    name: str
    summary: str
    payload: dict[str, Any]


def telemetry_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).copy()
    timestamp_col = "timestamp" if "timestamp" in df.columns else "recorded_at"
    df[timestamp_col] = pd.to_datetime(df[timestamp_col], utc=True, errors="coerce")
    df = df.dropna(subset=[timestamp_col]).sort_values(timestamp_col)
    df = df.rename(columns={timestamp_col: "timestamp"})

    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def run_pyod_tool(rows: list[dict[str, Any]]) -> ToolOutput:
    df = telemetry_frame(rows)
    feature_columns = [col for col in ("uv_dose_mj_cm2", "uvt", "turbidity_ntu", "lamp_power_pct", "lamp_health_pct") if col in df.columns]
    usable = df.dropna(subset=feature_columns) if feature_columns else pd.DataFrame()

    if len(usable) < 30 or not feature_columns:
        return ToolOutput(
            name="pyod_iforest",
            summary="PyOD anomaly tool needs at least 30 telemetry samples with UV dose, UVT, turbidity, lamp power, and lamp health to calibrate.",
            payload={"available_samples": int(len(usable)), "minimum_samples": 30, "features": feature_columns},
        )

    model = IForest(contamination=0.05, random_state=7)
    values = usable[feature_columns].to_numpy(dtype=float)
    model.fit(values[:-1])
    latest = values[-1:]
    score = float(model.decision_function(latest)[0])
    is_outlier = bool(model.predict(latest)[0] == 1)

    z_scores: dict[str, float] = {}
    baseline = usable.iloc[:-1]
    current = usable.iloc[-1]
    for col in feature_columns:
        std = float(baseline[col].std() or 0.0)
        if std <= 1e-9:
            z_scores[col] = 0.0
        else:
            z_scores[col] = float((current[col] - float(baseline[col].mean())) / std)
    ranked = sorted(z_scores.items(), key=lambda item: abs(item[1]), reverse=True)[:3]
    leading_signals = [
        {"metric": metric, "z_score": round(z, 3), "value": round(float(current[metric]), 3)}
        for metric, z in ranked
    ]

    summary = (
        f"PyOD Isolation Forest {'flagged' if is_outlier else 'did not flag'} the latest telemetry window as anomalous "
        f"(decision score {score:.3f})."
    )
    return ToolOutput(
        name="pyod_iforest",
        summary=summary,
        payload={
            "is_outlier": is_outlier,
            "decision_score": round(score, 3),
            "features": feature_columns,
            "leading_signals": leading_signals,
            "sample_size": int(len(usable)),
            "latest_timestamp": usable.iloc[-1]["timestamp"].isoformat(),
        },
    )


def run_prophet_tool(rows: list[dict[str, Any]], horizon_steps: int = 12) -> ToolOutput:
    df = telemetry_frame(rows)
    if "uvt" not in df.columns:
        return ToolOutput(
            name="prophet_uvt",
            summary="Prophet forecast tool requires a UVT history column.",
            payload={"available_columns": list(df.columns)},
        )

    model_df = df[["timestamp", "uvt"]].dropna().rename(columns={"timestamp": "ds", "uvt": "y"})
    if len(model_df) < 24:
        return ToolOutput(
            name="prophet_uvt",
            summary="Prophet forecast tool needs at least 24 UVT samples before producing a stable forecast.",
            payload={"available_samples": int(len(model_df)), "minimum_samples": 24},
        )

    model_df["ds"] = pd.to_datetime(model_df["ds"]).dt.tz_localize(None)
    model = Prophet(daily_seasonality=True, weekly_seasonality=False)
    model.fit(model_df)

    median_delta = model_df["ds"].diff().dropna().median()
    if pd.isna(median_delta) or median_delta <= pd.Timedelta(0):
        median_delta = pd.Timedelta(minutes=5)
    freq_minutes = max(1, int(median_delta.total_seconds() // 60))

    future = model.make_future_dataframe(periods=horizon_steps, freq=f"{freq_minutes}min")
    forecast = model.predict(future)[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(horizon_steps)
    latest_observed = float(model_df["y"].iloc[-1])
    final_row = forecast.iloc[-1]
    trend_delta = float(final_row["yhat"] - latest_observed)
    direction = "upward" if trend_delta > 0.25 else "downward" if trend_delta < -0.25 else "stable"
    threshold_risk = bool((forecast["yhat_lower"] < 70).any())

    preview = [
        {
            "timestamp": row.ds.isoformat(),
            "forecast_uvt": round(float(row.yhat), 3),
            "lower": round(float(row.yhat_lower), 3),
            "upper": round(float(row.yhat_upper), 3),
        }
        for row in forecast.itertuples(index=False)
    ]
    final_ts = pd.Timestamp(final_row["ds"])
    horizon_duration = timedelta(minutes=freq_minutes * horizon_steps)
    summary = (
        f"Prophet projects a {direction} UVT trend over the next {horizon_duration}; "
        f"final expected UVT is {float(final_row['yhat']):.2f}%T."
    )
    return ToolOutput(
        name="prophet_uvt",
        summary=summary,
        payload={
            "direction": direction,
            "latest_observed_uvt": round(latest_observed, 3),
            "final_forecast_uvt": round(float(final_row["yhat"]), 3),
            "final_lower_bound": round(float(final_row["yhat_lower"]), 3),
            "final_upper_bound": round(float(final_row["yhat_upper"]), 3),
            "threshold_risk_below_70": threshold_risk,
            "forecast_points": preview,
            "forecast_until": final_ts.isoformat(),
            "sample_size": int(len(model_df)),
            "step_minutes": freq_minutes,
        },
    )


def run_all_tools(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pyod = run_pyod_tool(rows)
    prophet = run_prophet_tool(rows)
    return {
        "pyod": {"summary": pyod.summary, **pyod.payload},
        "prophet": {"summary": prophet.summary, **prophet.payload},
    }
