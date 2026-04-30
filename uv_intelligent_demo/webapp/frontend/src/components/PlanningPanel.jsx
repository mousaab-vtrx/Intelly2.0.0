import {
  Plus,
  Clock,
  Briefcase,
  CalendarDays,
  CheckCircle2,
  TimerReset,
  AlertCircle,
  CheckCheck,
  Pause,
  ListTodo,
  Waves,
  ShieldCheck,
  Sparkles,
  ArrowRight,
} from "lucide-react";
import { useEffect, useState } from "react";
import { API_BASE_URL } from "../api/client";
import { useEventPublish, useEventSubscribe } from "../hooks/useEventBus";

export function PlanningPanel({ selectedDate }) {
  const [newTask, setNewTask] = useState("");
  const [scheduled, setScheduled] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [overridingTask, setOverridingTask] = useState(null);
  const [taskActionLoading, setTaskActionLoading] = useState(null);
  const [editingTaskId, setEditingTaskId] = useState(null);
  const [editText, setEditText] = useState("");
  const [editScheduledFor, setEditScheduledFor] = useState("");
  const [confirmRemovalTaskId, setConfirmRemovalTaskId] = useState(null);
  const publish = useEventPublish();

  async function loadScheduledTasks() {
    try {
      const response = await fetch(`${API_BASE_URL}/api/scheduled-tasks`);
      if (!response.ok) return;
      const data = await response.json();
      setScheduled(data.tasks || []);
    } catch (_err) {
      // Keep UI usable even when backend is unavailable.
    }
  }

  useEffect(() => {
    loadScheduledTasks();
    const intervalId = setInterval(loadScheduledTasks, 30000);
    return () => clearInterval(intervalId);
  }, []);

  useEventSubscribe("scheduled_task:update", () => {
    loadScheduledTasks();
  }, [selectedDate]);

  function getExecutionMidnightIso(targetDate) {
    const now = new Date();
    const base = new Date(targetDate || now);
    const midnightUtc = new Date(Date.UTC(base.getUTCFullYear(), base.getUTCMonth(), base.getUTCDate(), 0, 0, 0, 0));
    if (midnightUtc <= now) {
      midnightUtc.setUTCDate(midnightUtc.getUTCDate() + 1);
    }
    return midnightUtc.toISOString();
  }

  async function addTask() {
    const sanitized = newTask.trim();
    if (!sanitized || isSubmitting) return;

    const task = {
      id: Date.now(),
      text: sanitized,
      completed: false,
      createdAt: new Date().toISOString(),
      scheduledFor: getExecutionMidnightIso(selectedDate),
    };
    setIsSubmitting(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/schedule-task`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(task),
      });
      if (!response.ok) throw new Error("Unable to schedule task");

      await loadScheduledTasks();
      setNewTask("");

      publish("notification:show", {
        severity: "success",
        title: "Task Scheduled",
        message: `Task scheduled for ${new Date(task.scheduledFor).toLocaleString()}: "${task.text}"`,
        duration: 3000,
      });
    } catch (err) {
      publish("notification:show", {
        severity: "error",
        title: "Scheduling failed",
        message: err.message || "Task could not be scheduled.",
        duration: 3000,
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  async function overrideTask(taskId, action, reason) {
    setOverridingTask(taskId);
    try {
      const response = await fetch(`${API_BASE_URL}/api/task/${taskId}/override`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, reason }),
      });
      if (!response.ok) throw new Error("Unable to override task");

      await loadScheduledTasks();
      const actionLabel = action === "execute" ? "executed" : "cancelled";
      publish("notification:show", {
        severity: "info",
        title: "Task Override",
        message: `Task manually ${actionLabel}: ${reason}`,
        duration: 3000,
      });
    } catch (err) {
      publish("notification:show", {
        severity: "error",
        title: "Override failed",
        message: err.message || "Unable to override task.",
        duration: 3000,
      });
    } finally {
      setOverridingTask(null);
    }
  }

  async function updateTask(taskId, updates) {
    setTaskActionLoading(taskId);
    try {
      const response = await fetch(`${API_BASE_URL}/api/task/${taskId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || body.message || "Unable to update task");
      }

      await loadScheduledTasks();
      publish("notification:show", {
        severity: "success",
        title: "Task updated",
        message: "Task details were updated successfully.",
        duration: 3000,
      });
      return true;
    } catch (err) {
      publish("notification:show", {
        severity: "error",
        title: "Update failed",
        message: err.message || "Unable to update task.",
        duration: 3000,
      });
      return false;
    } finally {
      setTaskActionLoading(null);
    }
  }

  async function removeTask(taskId) {
    setTaskActionLoading(taskId);
    try {
      const response = await fetch(`${API_BASE_URL}/api/task/${taskId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || body.message || "Unable to remove task");
      }

      await loadScheduledTasks();
      publish("notification:show", {
        severity: "info",
        title: "Task removed",
        message: "The task was removed from the queue.",
        duration: 3000,
      });
    } catch (err) {
      publish("notification:show", {
        severity: "error",
        title: "Remove failed",
        message: err.message || "Unable to remove task.",
        duration: 3000,
      });
    } finally {
      setTaskActionLoading(null);
      setConfirmRemovalTaskId(null);
    }
  }

  function toLocalDatetime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";

    const tzOffset = date.getTimezoneOffset() * 60000;
    const localDate = new Date(date.getTime() - tzOffset);
    return localDate.toISOString().slice(0, 16);
  }

  function startEditTask(task) {
    setEditingTaskId(task.id);
    setEditText(task.text || "");
    setEditScheduledFor(toLocalDatetime(task.scheduledFor));
  }

  function cancelEdit() {
    setEditingTaskId(null);
    setEditText("");
    setEditScheduledFor("");
  }

  async function saveEdit(taskId) {
    const trimmed = editText.trim();
    if (!trimmed) {
      publish("notification:show", {
        severity: "warning",
        title: "Invalid task",
        message: "Task text cannot be empty.",
        duration: 2500,
      });
      return;
    }

    const updates = {
      text: trimmed,
      scheduledFor: editScheduledFor ? new Date(editScheduledFor).toISOString() : undefined,
    };

    const success = await updateTask(taskId, updates);
    if (success) {
      cancelEdit();
    }
  }

  function promptRemoveTask(taskId) {
    setConfirmRemovalTaskId(taskId);
  }

  function cancelRemove() {
    setConfirmRemovalTaskId(null);
  }

  const queuedTasks = scheduled
    .filter((item) => !item.completed)
    .sort((a, b) => new Date(a.scheduledFor) - new Date(b.scheduledFor));
  const executedTasks = scheduled
    .filter((item) => item.completed)
    .sort((a, b) => new Date(b.executedAt || b.scheduledFor) - new Date(a.executedAt || a.scheduledFor))
    .slice(0, 5);

  const selectedDateLabel = (selectedDate || new Date()).toLocaleDateString(undefined, {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
  const nextRunLabel = new Date(getExecutionMidnightIso(selectedDate)).toLocaleString();
  const summaryCards = [
    { label: "Selected date", value: selectedDateLabel, icon: CalendarDays },
    { label: "Direct window", value: nextRunLabel, icon: Clock },
    { label: "Tasks", value: `${queuedTasks.length} task(s)`, icon: ListTodo },
  ];

  return (
    <section className="planning-panel orchestrator-experience">
      <div className="orchestrator-hero">
        <div className="orchestrator-hero-copy">
          <h3>
            <Briefcase size={22} />
            Orchestrator
          </h3>
          <p>
            Create review-ready orchestration steps so the system can assess current reactor conditions and produce direct operator guidance with a detailed PDF package.
          </p>
        </div>
        <div className="orchestrator-flow">
          <div className="flow-node">
            <Waves size={18} />
            <span>Intake</span>
          </div>
          <ArrowRight size={16} />
          <div className="flow-node">
            <Sparkles size={18} />
            <span>AI Review</span>
          </div>
          <ArrowRight size={16} />
          <div className="flow-node">
            <ShieldCheck size={18} />
            <span>Direct</span>
          </div>
        </div>
      </div>

      <div className="orchestrator-summary">
        {summaryCards.map(({ label, value, icon: Icon }) => (
          <div key={label} className="orchestrator-card">
            <div className="orchestrator-card-icon">
              <Icon size={18} />
            </div>
            <div className="orchestrator-card-copy">
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          </div>
        ))}
      </div>

      <div className="orchestrator-composer">
        <div className="task-input">
          <input
            type="text"
            value={newTask}
            onChange={(e) => setNewTask(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !isSubmitting && addTask()}
            placeholder="Create orchestration step for selected date..."
            className="task-input-field"
            disabled={isSubmitting}
          />
          <button
            onClick={addTask}
            className="task-add-btn"
            title="Schedule task"
            disabled={isSubmitting || !newTask.trim()}
          >
            <Plus size={18} />
          </button>
        </div>
      </div>

      <div className="orchestrator-grid">
        <div className="tasks-list orchestrator-column">
          <h4 className="planning-subtitle">
            <Clock size={16} />
            Queued for review
          </h4>
          {queuedTasks.length === 0 ? (
            <div className="empty-state-small">
              <p>No queued tasks. Create an orchestration step.</p>
            </div>
          ) : (
            queuedTasks.map((task) => {
              const isBusy = taskActionLoading === task.id || overridingTask === task.id;

              return (
                <div key={task.id} className="task-item task-item-queued">
                  {confirmRemovalTaskId === task.id ? (
                    <div className="confirm-card">
                      <p><AlertCircle size={16} /> Confirm removal of this task?</p>
                      <div className="task-action-row">
                        <button
                          onClick={() => removeTask(task.id)}
                          disabled={taskActionLoading === task.id}
                          className="task-action-btn task-action-remove"
                        >
                          Confirm
                        </button>
                        <button
                          onClick={cancelRemove}
                          className="task-action-btn task-action-cancel"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : editingTaskId === task.id ? (
                    <div className="task-edit-form">
                      <input
                        className="task-edit-input"
                        type="text"
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        placeholder="Edit task description"
                      />
                      <label className="task-edit-label">
                        Scheduled for
                        <input
                          type="datetime-local"
                          className="task-edit-input"
                          value={editScheduledFor}
                          onChange={(e) => setEditScheduledFor(e.target.value)}
                        />
                      </label>
                      <div className="task-action-row">
                        <button
                          onClick={() => saveEdit(task.id)}
                          disabled={taskActionLoading === task.id}
                          className="task-action-btn"
                        >
                          Save
                        </button>
                        <button
                          onClick={cancelEdit}
                          disabled={taskActionLoading === task.id}
                          className="task-action-btn task-action-cancel"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="task-content">
                        <p className="task-text">{task.text}</p>
                        <small className="task-time">
                          Scheduled for {new Date(task.scheduledFor).toLocaleString()}
                        </small>
                      </div>
                      <div className="task-action-row">
                        <button
                          onClick={() => startEditTask(task)}
                          disabled={isBusy}
                          className="task-action-btn"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => promptRemoveTask(task.id)}
                          disabled={isBusy}
                          className="task-action-btn task-action-remove"
                        >
                          Remove
                        </button>
                      </div>
                    </>
                  )}
                </div>
              );
            })
          )}
        </div>

        <div className="tasks-list orchestrator-column">
          <h4 className="planning-subtitle">
            <CheckCircle2 size={16} />
            Recently reviewed
          </h4>
          {executedTasks.length === 0 ? (
            <div className="empty-state-small">
              <p>No reviewed tasks yet.</p>
            </div>
          ) : (
            executedTasks.map((item) => {
              const aiEval = item.ai_evaluation;
              const isDeferredOrCancelled = item.status === "deferred" || item.status === "cancelled";

              return (
                <div key={`scheduled-${item.id}`} className={`task-item task-item-reviewed ${item.status}`}>
                  {confirmRemovalTaskId === item.id ? (
                    <div className="confirm-card">
                      <p><AlertCircle size={16} /> Confirm removal of this task?</p>
                      <div className="task-action-row">
                        <button
                          onClick={() => removeTask(item.id)}
                          disabled={taskActionLoading === item.id}
                          className="task-action-btn task-action-remove"
                        >
                          Confirm
                        </button>
                        <button
                          onClick={cancelRemove}
                          className="task-action-btn task-action-cancel"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="task-content">
                      <div className="task-row">
                        <p className="task-text">{item.text}</p>
                        {isDeferredOrCancelled ? (
                          <span className="task-status-chip">
                            <AlertCircle size={14} />
                            {item.status === "deferred" ? "Deferred" : "Cancelled"}
                          </span>
                        ) : null}
                      </div>
                      <small className="task-time">
                        {item.status === "executed" ? "Directed" : "Reviewed"}{" "}
                        {new Date(item.executedAt || item.scheduledFor).toLocaleString()}
                      </small>
                      {aiEval ? (
                        <div className={`ai-eval-card ${aiEval.ai_decision ? "approve" : "defer"}`}>
                          <p className="ai-eval-line">
                            <strong>AI Decision</strong>
                            {aiEval.ai_decision ? (
                              <span className="ai-decision approve">
                                <CheckCheck size={14} /> Direct
                              </span>
                            ) : (
                              <span className="ai-decision defer">
                                <Pause size={14} /> Defer
                              </span>
                            )}
                            <span className="ai-confidence">
                              {(aiEval.confidence * 100).toFixed(0)}% confidence
                            </span>
                          </p>
                          <p className="ai-eval-copy">
                            <strong>Reason:</strong> {aiEval.reason || "N/A"}
                          </p>
                          <p className="ai-eval-copy">
                            <strong>Health:</strong> {aiEval.health_status}
                          </p>
                          {!isDeferredOrCancelled ? (
                            <div className="task-override-actions">
                              {!aiEval.ai_decision ? (
                                <button
                                  onClick={() => overrideTask(item.id, "execute", "Operator force-executed")}
                                  disabled={overridingTask === item.id}
                                  className="override-btn approve"
                                >
                                  Force Direct
                                </button>
                              ) : null}
                              <button
                                onClick={() => overrideTask(item.id, "cancel", "Operator cancelled")}
                                disabled={overridingTask === item.id}
                                className="override-btn cancel"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                      {confirmRemovalTaskId === item.id ? (
                        <div className="confirm-card">
                          <p><AlertCircle size={16} /> Confirm removal of this task?</p>
                          <div className="task-action-row">
                            <button
                              onClick={() => removeTask(item.id)}
                              disabled={taskActionLoading === item.id}
                              className="task-action-btn task-action-remove"
                            >
                              Confirm
                            </button>
                            <button
                              onClick={cancelRemove}
                              className="task-action-btn task-action-cancel"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="task-action-row">
                          <button
                            onClick={() => promptRemoveTask(item.id)}
                            disabled={taskActionLoading === item.id}
                            className="task-action-btn task-action-remove"
                          >
                            Remove
                          </button>
                        </div>
                      )}
                      {item.status === "executed" ? <TimerReset size={16} className="task-executed-icon" /> : null}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </section>
  );
}
