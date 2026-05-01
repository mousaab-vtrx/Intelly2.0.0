# ML Model & Tool Recommendations for UV Reactor Ops Center

## Executive Summary

Your current stack uses **PyOD (Isolation Forest)** for anomaly detection and **Prophet** for time series forecasting. This document recommends additional ML models and tools that would enhance the agentic AI system's capabilities for a UV reactor monitoring and operator-assistance application.

Recommendations are organized by capability gap and include deployment considerations for your containerized FastAPI + React environment.

---

## Current Stack

### Models in Production
- **PyOD IForest** — Anomaly detection on 5-feature telemetry
- **Prophet** — UVT forecasting with daily seasonality

### Infrastructure
- **LLM**: Mistral API (primary) / Ollama (local fallback)
- **RAG**: ChromaDB with embeddings
- **Backend**: FastAPI + PostgreSQL + Redis
- **Container**: Docker Compose with MQTT + InfluxDB optional

---

## Recommended Model Additions

### 1. **Isolation Forest Extensions & Alternatives**

**Current Gap:** Single IForest model; no ensemble or domain adaptation.

#### 1A. DBSCAN (Clustering-based Anomaly)
- **Use Case**: Detect anomalies based on density rather than isolation.
- **Advantages**: Better for contextual outliers (e.g., "normal under high load, abnormal under low load").
- **Implementation**:
  ```python
  from sklearn.cluster import DBSCAN
  # Parameters tuned for UV dose/turbidity/lamp patterns
  dbscan = DBSCAN(eps=0.5, min_samples=5)
  labels = dbscan.fit_predict(telemetry_features)
  # Labels == -1 are anomalies
  ```
- **Integration**: Run in parallel with IForest; flag only if both agree.

#### 1B. Local Outlier Factor (LOF)
- **Use Case**: Detect local density deviations; good for multimodal telemetry.
- **Advantages**: Catches gradual shifts that IForest might miss.
- **Implementation**:
  ```python
  from sklearn.neighbors import LocalOutlierFactor
  lof = LocalOutlierFactor(n_neighbors=20, contamination=0.05)
  anomaly_scores = lof.fit_predict(telemetry)
  ```

#### 1C. **Ensemble Anomaly Detection**
- **Approach**: Combine IForest + DBSCAN + LOF with weighted voting.
- **Benefits**: Higher precision, lower false positive rate.
- **Example**:
  ```python
  iforest_score = model_iforest.decision_function(features)
  dbscan_label = model_dbscan.fit_predict(features)
  lof_score = model_lof.negative_outlier_factor_
  
  ensemble_anomaly = (normalize(iforest_score) * 0.5 + 
                      normalize(lof_score) * 0.3 +
                      (dbscan_label == -1) * 0.2)
  ```

---

### 2. **Time Series Forecasting Enhancements**

**Current Gap:** Prophet handles trend + daily seasonality; no uncertainty quantification or multivariate correlation.

#### 2A. LSTM (Long Short-Term Memory) Networks
- **Use Case**: Capture long-range dependencies in UV dose, lamp power degradation over hours/days.
- **Advantages**: Learns nonlinear relationships; handles variable-length sequences.
- **Trade-off**: Requires historical data (minimum 100 samples), GPU recommended.
- **Implementation**:
  ```python
  import tensorflow as tf
  model = tf.keras.Sequential([
    tf.keras.layers.LSTM(64, activation='relu', input_shape=(timesteps, n_features)),
    tf.keras.layers.Dropout(0.2),
    tf.keras.layers.LSTM(32, activation='relu'),
    tf.keras.layers.Dense(16, activation='relu'),
    tf.keras.layers.Dense(1)
  ])
  model.compile(optimizer='adam', loss='mse')
  # Train on historical telemetry; predict UV dose, turbidity
  ```
- **Integration**: Use alongside Prophet; average predictions or let operator choose mode.

#### 2B. Transformer Models (Temporal Fusion Transformer)
- **Use Case**: Multi-horizon forecasting with attention mechanisms.
- **Advantages**: Interpretable (can show which past time steps matter most).
- **Library**: `pytorch-forecasting` (PyTorch-based).
- **Complexity**: Medium; good for production if you need explainability.

#### 2C. AutoML for Time Series (AutoGluon)
- **Use Case**: Automatically select best Prophet/LSTM/ARIMA for your data.
- **Advantages**: Minimal tuning; adapts as data characteristics change.
- **Implementation**:
  ```python
  from autogluon.timeseries import TimeSeriesPredictor
  predictor = TimeSeriesPredictor(prediction_length=12, freq='min')
  predictor.fit(train_data, presets='fast_training')
  forecast = predictor.predict(test_data)
  ```
- **Trade-off**: Slower training, better generalization.

---

### 3. **Root Cause Analysis & Diagnostics**

**Current Gap:** Anomaly detected, but why? No automatic root-cause diagnosis.

#### 3A. Correlation & Causality Analysis
- **Use Case**: Detect which upstream metric (flow, lamp power, UVT) caused downstream problem.
- **Approach**: Compute Granger causality or cross-correlation matrix.
- **Implementation**:
  ```python
  from statsmodels.tsa.stattools import grangercausalitytests
  # Does lamp_power Granger-cause uv_dose?
  result = grangercausalitytests(data[['uv_dose', 'lamp_power']], maxlag=5)
  ```
- **Output**: Feed to LLM copilot: "Lamp power dropped 10% 5 minutes before dose fell."

#### 3B. SHAP (SHapley Additive exPlanations)
- **Use Case**: Explain why IForest flagged a sample as anomalous.
- **Advantages**: Shows feature contribution to anomaly score.
- **Implementation**:
  ```python
  import shap
  explainer = shap.TreeExplainer(model_iforest)
  shap_values = explainer.shap_values(latest_sample)
  # shap_values shows which features pushed score toward anomaly
  ```
- **Output**: Enhanced copilot context: "Anomaly driven by: 30% turbidity spike, 20% UVT dip."

---

### 4. **Optimization & Control Recommendations**

**Current Gap:** Reactive reporting; no proactive control suggestions.

#### 4A. Reinforcement Learning (RL) for Setpoint Optimization
- **Use Case**: Learn optimal lamp power, flow rate, etc. to maximize UV dose while minimizing degradation.
- **Approach**: Q-learning or PPO (Proximal Policy Optimization) trained on simulation.
- **Library**: OpenAI Gym, Stable Baselines3.
- **Example**:
  ```python
  from stable_baselines3 import PPO
  model = PPO('MlpPolicy', env, n_steps=2048)
  model.learn(total_timesteps=100000)
  # Learns: "Increase lamp power to 90% when flow > 50, UVT > 80%"
  ```
- **Deployment**: Use in advisory mode; operator approves recommendations before control handoff.

#### 4B. Constraint Programming (Linear/Mixed Integer Programming)
- **Use Case**: Find optimal operating point given hard constraints (max temp, min turbidity, target dose).
- **Library**: `scipy.optimize`, `PuLP`, or `Pyomo`.
- **Example**:
  ```python
  from scipy.optimize import linprog
  # Maximize uv_dose subject to: lamp_power <= 100%, temp <= 45C, flow >= 40 m³/h
  ```
- **Advantage**: Guaranteed feasible solutions; very fast (<1ms).

---

### 5. **Copilot & Communication Enhancement**

**Current Gap:** LLM is general-purpose; domain knowledge not fully leveraged.

#### 5A. Instruction Tuning on Domain Data
- **Use Case**: Fine-tune Mistral or open-source LLM (Llama 2) on UV reactor SOP docs.
- **Approach**: Use LoRA (Low-Rank Adaptation) for efficient fine-tuning.
- **Library**: `transformers`, `peft` (HuggingFace).
- **Example**:
  ```python
  from peft import LoRA_config, get_peft_model
  from transformers import AutoModelForCausalLM
  
  model = AutoModelForCausalLM.from_pretrained("meta-llama/Llama-2-7b")
  peft_config = LoRA_config(r=16, lora_alpha=32, target_modules=["q_proj", "v_proj"])
  model = get_peft_model(model, peft_config)
  # Fine-tune on UV SOP corpus
  ```
- **Result**: Better understanding of "dose threshold," "lamp degradation," "compliance."

#### 5B. Few-Shot Prompting with RAG
- **Current Setup**: Already using ChromaDB + LangChain.
- **Enhancement**: Automatically retrieve relevant SOP + past incident context and inject into prompt.
- **Example Prompt**:
  ```
  You are a UV reactor operator assistant.
  
  RELEVANT SOP:
  [... retrieved from ChromaDB ...]
  
  SIMILAR PAST INCIDENT:
  Date: 2025-10-15, Turbidity spike 8 NTU → adjusted flow from 50 to 60 m³/h
  
  CURRENT SITUATION:
  Turbidity: 7.5 NTU, Lamp Power: 95%, UVT: 75%
  
  Recommend action:
  ```
- **Benefit**: LLM context-aware without full fine-tuning.

#### 5C. Retrieval-Augmented Generation (RAG) Improvement
- **Current**: ChromaDB with default embeddings.
- **Enhancement**: Use domain-specific embeddings or hybrid search.
- **Options**:
  - `sentence-transformers` with fine-tuned model
  - Hybrid: Keyword (BM25) + semantic search
  - Dense-Passage-Retrieval (DPR) for better relevance

---

### 6. **Predictive Maintenance**

**Current Gap:** No degradation forecasting (lamp end-of-life prediction).

#### 6A. Remaining Useful Life (RUL) Prediction
- **Use Case**: Predict when lamp reaches 50% efficiency and needs replacement.
- **Approach**: Train regression model on lamp_health_pct time series.
- **Implementation**:
  ```python
  from sklearn.ensemble import GradientBoostingRegressor
  # Features: lamp_health_pct, operating hours, degradation rate
  model = GradientBoostingRegressor()
  model.fit(X_train, y_train)  # y_train = hours until replacement
  rul = model.predict(current_state)
  ```
- **Output**: "Lamp estimated replacement in 720 hours (30 days)."

#### 6B. Weibull Analysis
- **Use Case**: Model failure/degradation time distributions.
- **Library**: `reliability` (Python package).
- **Advantage**: Industry-standard for reliability engineering.

---

### 7. **Integration Recommendations**

#### Architecture Additions

```
Current:                        Recommended:
PyOD IForest                    ┌─ PyOD IForest
Prophet                         ├─ DBSCAN + LOF (ensemble)
Mistral LLM                     ├─ Prophet + LSTM
ChromaDB RAG                    ├─ RL Optimizer (advisory)
                                ├─ SHAP Explainability
                                ├─ Fine-tuned Llama-2 (optional)
                                └─ RUL Predictor
```

#### API Endpoint Structure
```python
# app.py additions

@app.get("/api/ai/tools/analysis")
async def get_tool_analysis(limit: int = 120):
    """Current: PyOD + Prophet"""
    return {"pyod": ..., "prophet": ...}

@app.get("/api/ai/tools/ensemble")
async def get_ensemble_analysis():
    """NEW: Multi-model anomaly ensemble"""
    iforest = run_pyod_tool(...)
    dbscan = run_dbscan_tool(...)
    lof = run_lof_tool(...)
    return {"ensemble": weighted_vote(...), "consensus": ...}

@app.post("/api/ai/diagnostics/root-cause")
async def diagnose_anomaly(context: dict):
    """NEW: Root cause analysis"""
    granger = compute_granger_causality(...)
    shap_explain = explain_anomaly(...)
    return {"causes": ..., "confidence": ...}

@app.post("/api/ai/optimization/recommend")
async def recommend_setpoint():
    """NEW: RL-based control suggestions"""
    rl_policy = load_policy(...)
    action = rl_policy.predict(current_state)
    return {"action": action, "expected_outcome": ...}
```

---

## Deployment Roadmap

### Phase 1 (1-2 weeks): Low-Risk Additions
- [ ] Add DBSCAN + LOF for ensemble anomaly detection
- [ ] Integrate SHAP for anomaly explanation
- [ ] Document domain knowledge in ChromaDB
- **Effort**: Medium | **Risk**: Low | **Benefit**: Improved diagnostics

### Phase 2 (2-4 weeks): Forecasting Enhancement
- [ ] Add LSTM baseline for UV dose forecasting
- [ ] A/B test Prophet vs LSTM vs hybrid
- [ ] Implement AutoGluon selector
- **Effort**: High | **Risk**: Medium | **Benefit**: Better predictions, easier tuning

### Phase 3 (4-8 weeks): Advanced Optimization
- [ ] Train RL policy on simulator (digital twin)
- [ ] Implement advisory-mode control suggestions
- [ ] Fine-tune LLM on domain corpus
- **Effort**: Very High | **Risk**: Medium-High | **Benefit**: Proactive operation guidance

### Phase 4 (Ongoing): Explainability & Maintenance
- [ ] Deploy SHAP + Granger causality to all analyses
- [ ] Build RUL predictor for lamp degradation
- [ ] Monitor model drift; retrain quarterly
- **Effort**: Ongoing | **Risk**: Low | **Benefit**: Regulatory compliance, predictive maintenance

---

## Technology Stack Recommendations

### Python Libraries to Add to `requirements.txt`

```
# Anomaly Detection Ensemble
scikit-learn>=1.0          # DBSCAN, LOF
pyod>=1.1.0               # Already in use; keep

# Time Series
tensorflow>=2.10          # LSTM (CPU or GPU)
# OR pytorch>=1.13 + pytorch-forecasting
autogluon-timeseries>=0.7

# Forecasting
statsmodels>=0.14         # Granger causality

# Explainability
shap>=0.41

# Optimization
scipy>=1.9                # Already used; add for optimization
# PuLP or Pyomo for constraint programming (optional)

# Reinforcement Learning (phase 3)
stable-baselines3>=1.8
gym>=0.26

# LLM Fine-tuning (phase 3)
peft>=0.4                 # LoRA
transformers>=4.30        # HuggingFace models
```

### Docker Considerations

1. **Separate services for heavyweight models**:
   ```yaml
   services:
     backend-api:        # FastAPI (current)
     ml-ensemble:        # PyOD + DBSCAN + LOF (separate container)
     ml-lstm:            # LSTM forecasting (optional GPU)
     ml-rl-policy:       # RL advisor (advisory mode)
   ```

2. **GPU Support** (for LSTM / RL training):
   ```dockerfile
   FROM nvidia/cuda:11.8-runtime
   # Add --gpus all to docker-compose
   ```

3. **Model Caching**:
   - Use Redis for trained model weights
   - Versioned model artifacts in PostgreSQL
   - Quick rollback on performance regression

---

## Production Considerations

### Monitoring & Logging

- Track model accuracy (anomaly F1, forecast MAPE) over time
- Alert on model drift (e.g., false positive rate >15%)
- Log all operator-approved vs rejected recommendations
- Version all models (ModelRegistry in MLflow)

### Retraining Schedule

- **Anomaly models**: Monthly on new telemetry
- **Forecasting**: Weekly (Prophet), monthly (LSTM)
- **RL policy**: Retrain quarterly on accumulated decisions
- **LLM fine-tuning**: Quarterly on new SOPs + past incidents

### Explainability & Compliance

- All anomalies must have SHAP explanation in audit log
- Root cause analysis mandatory for high-severity alerts
- RL recommendations always labeled "advisory; human approval required"

---

## Cost Estimate (AWS / GCP)

| Component | Option | Monthly Cost |
|-----------|--------|--------------|
| GPU for LSTM | p3.2xlarge | $100-150 (dev) |
| LLM fine-tuning | g4dn.xlarge | $50-100 (training) |
| Model serving | CPU only | $0 (existing) |
| ChromaDB + RAG | Managed Weaviate | $50-200 |
| **Total** | Minimal setup | $150-450 |

**Recommendation**: Start with CPU-only models (Phase 1-2); add GPU only if LSTM retraining becomes bottleneck.

---

## References & Resources

### Papers & Best Practices
- [Isolation Forest - Liu et al. 2008](https://cs.nju.edu.cn/zhouzh/zhouzh.files/publication/icdm08.pdf)
- [Prophet: Forecasting at Scale - Meta 2017](https://research.facebook.com/publications/prophet-forecasting-at-scale/)
- [SHAP: A Unified Approach to Interpreting Model Predictions - Lundberg & Lee 2017](https://arxiv.org/abs/1705.07874)
- [Stable Baselines3 - Christodoulou et al. 2019](https://jmlr.org/papers/v22/20-1364.html)

### Open-Source Tools
- [PyOD](https://pyod.readthedocs.io/)
- [AutoGluon Time Series](https://auto.gluon.ai/stable/tutorials/timeseries/index.html)
- [MLflow](https://mlflow.org/) for model tracking
- [Evidently AI](https://www.evidentlyai.com/) for model monitoring

### Domain-Specific
- UV Disinfection Standards: NWRI UV Disinfection Guidance Manual
- Reactor Monitoring: IEC 60050 (industrial electrotechnical terminology)

---

## Questions & Next Steps

1. **Data Retention**: How long do you keep telemetry? (affects LSTM training)
2. **Compliance**: Are there regulatory requirements (ISO 9001, GxP) for model decisions?
3. **Operator Feedback**: Are you capturing acceptance/rejection of recommendations for retraining?
4. **GPU Access**: Is GPU infrastructure available or should we prioritize CPU-only models?
5. **LLM Preference**: Mistral API indefinitely, or open-source Llama 2 eventually?

**Recommendation**: Start with Phase 1 (ensemble + SHAP) in parallel with current operations; measure impact before Phase 2.
