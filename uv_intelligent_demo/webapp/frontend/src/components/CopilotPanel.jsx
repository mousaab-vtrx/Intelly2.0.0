import { useState, useRef, useEffect } from "react";
import {
  AlertTriangle,
  ArrowUp,
  CheckCircle2,
  FileText,
  Info,
  Paperclip,
  Pin,
  Search,
  Wrench,
  XCircle,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API_BASE_URL } from "../api/client";
import { useEventPublish } from "../hooks/useEventBus";

function flattenMarkdownText(children) {
  return children
    .flatMap((child) => {
      if (typeof child === "string") return [child];
      if (typeof child === "number") return [String(child)];
      if (Array.isArray(child)) return flattenMarkdownText(child);
      if (child?.props?.children) return flattenMarkdownText(Array.isArray(child.props.children) ? child.props.children : [child.props.children]);
      return [];
    })
    .join("")
    .trim();
}

function headingIconFor(text) {
  const normalized = text.toLowerCase();
  if (normalized.startsWith("summary") || normalized.startsWith("analysis")) {
    return FileText;
  }
  if (normalized.startsWith("cause")) {
    return Search;
  }
  if (normalized.startsWith("risk") || normalized.startsWith("error")) {
    return AlertTriangle;
  }
  if (normalized.startsWith("recommendation") || normalized.startsWith("action")) {
    return CheckCircle2;
  }
  if (normalized.startsWith("evidence")) {
    return Paperclip;
  }
  if (normalized.startsWith("why it matters")) {
    return Pin;
  }
  if (normalized.startsWith("troubleshooting")) {
    return Wrench;
  }
  return FileText;
}

function statusMetaFor(text) {
  const normalized = text.toLowerCase();
  if (normalized.startsWith("warning:")) {
    return { Icon: AlertTriangle, tone: "warning", label: "Warning", body: text.slice(8).trim() };
  }
  if (normalized.startsWith("error:")) {
    return { Icon: XCircle, tone: "danger", label: "Error", body: text.slice(6).trim() };
  }
  if (normalized.startsWith("info:")) {
    return { Icon: Info, tone: "info", label: "Info", body: text.slice(5).trim() };
  }
  if (normalized.startsWith("recommendation:")) {
    return { Icon: CheckCircle2, tone: "success", label: "Recommendation", body: text.slice(15).trim() };
  }
  return null;
}

function CopilotHeading({ children }) {
  const text = flattenMarkdownText(Array.isArray(children) ? children : [children]);
  const Icon = headingIconFor(text);
  return (
    <h6 className="copilot-section-heading">
      <span className="copilot-section-icon" aria-hidden="true">
        <Icon size={15} />
      </span>
      <span>{text}</span>
    </h6>
  );
}

function CopilotParagraph({ children, ...props }) {
  const text = flattenMarkdownText(Array.isArray(children) ? children : [children]);
  const status = statusMetaFor(text);
  if (status) {
    const { Icon, tone, label, body } = status;
    return (
      <div className={`copilot-status-line tone-${tone}`} {...props}>
        <span className="copilot-status-icon" aria-hidden="true">
          <Icon size={15} />
        </span>
        <span>
          <strong>{label}</strong>
          {body ? `: ${body}` : ""}
        </span>
      </div>
    );
  }

  return <p className="markdown-paragraph" {...props}>{children}</p>;
}

export function CopilotPanel({ collapsed, isOpen, telemetry, width, onResize }) {
  const [messages, setMessages] = useState([
    {
      id: 0,
      role: "assistant",
      content:
        "Ready for UV operations questions.",
      timestamp: new Date(),
      sources: [],
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const panelRef = useRef(null);
  const messagesEndRef = useRef(null);
  const resizePointerIdRef = useRef(null);
  const resizeFrameRef = useRef(0);
  const pendingWidthRef = useRef(width);
  const publish = useEventPublish();
  const probableRequests = [
    "UV dose risk",
    "Anomaly summary",
    "Lamp maintenance",
    "Operational recommendation",
  ];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    pendingWidthRef.current = width;
  }, [width]);

  useEffect(() => {
    if (!isResizing) return undefined;

    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
    };
  }, [isResizing]);

  useEffect(
    () => () => {
      if (resizeFrameRef.current) {
        cancelAnimationFrame(resizeFrameRef.current);
      }
    },
    []
  );

  function isResizeEnabled() {
    return Boolean(onResize) && window.matchMedia("(min-width: 961px)").matches;
  }

  function queueResize(nextWidth) {
    if (!onResize) return;
    pendingWidthRef.current = nextWidth;
    if (resizeFrameRef.current) return;

    resizeFrameRef.current = requestAnimationFrame(() => {
      resizeFrameRef.current = 0;
      onResize(pendingWidthRef.current);
    });
  }

  function updateWidthFromPointer(clientX) {
    if (!panelRef.current || !isResizeEnabled()) return;
    const { right } = panelRef.current.getBoundingClientRect();
    queueResize(right - clientX);
  }

  function stopResizing(target) {
    if (target && resizePointerIdRef.current !== null && target.hasPointerCapture?.(resizePointerIdRef.current)) {
      target.releasePointerCapture(resizePointerIdRef.current);
    }
    resizePointerIdRef.current = null;
    setIsResizing(false);
  }

  async function handleSendMessage() {
    const question = input.trim();
    if (!question) return;

    // Add user message
    const userMsg = {
      id: `user-${Date.now()}`,
      role: "user",
      content: question,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    // Publish event for analytics
    publish("copilot:question_asked", { question });

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

      if (!response.ok) throw new Error("Chat failed");
      const data = await response.json();

      const assistantMsg = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: data.answer || "Unable to generate response.",
        timestamp: new Date(),
        sources: data.sources || [],
      };
      setMessages((prev) => [...prev, assistantMsg]);

      publish("notification:show", {
        severity: "success",
        title: "Copilot response received",
        duration: 2000,
      });
    } catch (err) {
      publish("notification:show", {
        severity: "error",
        title: "Copilot Error",
        message: err.message || "Failed to get response",
      });
    } finally {
      setIsLoading(false);
    }
  }

  function handleProbableRequest(prompt) {
    if (isLoading) return;
    setInput(prompt);
  }

  function handleResizePointerDown(event) {
    if (!isResizeEnabled()) return;
    resizePointerIdRef.current = event.pointerId;
    setIsResizing(true);
    updateWidthFromPointer(event.clientX);
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handleResizePointerMove(event) {
    if (!isResizing || resizePointerIdRef.current !== event.pointerId) return;
    updateWidthFromPointer(event.clientX);
  }

  function handleResizeKeyDown(event) {
    if (!onResize) return;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      onResize(width + 24);
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      onResize(width - 24);
    }
  }

  return (
    <section
      ref={panelRef}
      className={`copilot-panel ${isOpen ? "open" : "closed"} ${collapsed ? "sidebar-compact" : ""} ${
        isResizing ? "resizing" : ""
      }`}
    >
      {isOpen && (
        <div className="copilot-container">
          <button
            type="button"
            className={`copilot-resize-handle ${isResizing ? "dragging" : ""}`}
            aria-label="Resize copilot panel"
            title="Drag to resize"
            onPointerDown={handleResizePointerDown}
            onPointerMove={handleResizePointerMove}
            onPointerUp={(event) => stopResizing(event.currentTarget)}
            onPointerCancel={(event) => stopResizing(event.currentTarget)}
            onLostPointerCapture={(event) => stopResizing(event.currentTarget)}
            onKeyDown={handleResizeKeyDown}
          />
          <div className="copilot-topbar">
            <div className="copilot-topbar-title">
              <span className="copilot-title-dot" />
              <span>Copilot</span>
            </div>
          </div>
          <div className="copilot-request-list">
            {probableRequests.map((prompt) => (
              <button
                key={prompt}
                type="button"
                className="copilot-request-chip"
                onClick={() => handleProbableRequest(prompt)}
                disabled={isLoading}
              >
                {prompt}
              </button>
            ))}
          </div>
          <div className="messages-container">
            {messages.map((msg) => (
              <div key={msg.id} className={`message message-${msg.role}`}>
                <div className={`message-accent message-${msg.role}`} aria-hidden="true" />
                <div className="message-content">
                  {msg.role === "assistant" ? (
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        h1: ({ node, ...props }) => <h4 {...props} />,
                        h2: ({ node, ...props }) => <h5 {...props} />,
                        h3: ({ node, ...props }) => <CopilotHeading {...props} />,
                        p: ({ node, ...props }) => <CopilotParagraph {...props} />,
                        ul: ({ node, ...props }) => <ul className="markdown-list" {...props} />,
                        ol: ({ node, ...props }) => <ol className="markdown-list" {...props} />,
                        li: ({ node, ...props }) => <li className="markdown-list-item" {...props} />,
                        pre: ({ node, ...props }) => <pre className="code-block" {...props} />,
                        code: ({ node, inline, className, children, ...props }) =>
                          inline ? (
                            <code className="inline-code" {...props} />
                          ) : (
                            <code className={className} {...props}>{children}</code>
                          ),
                      }}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  ) : (
                    <p>{msg.content}</p>
                  )}
                  {msg.role === "assistant" && msg.sources?.length > 0 && (
                    <div className="message-sources">
                      {msg.sources.map((source, idx) => (
                        <span key={`${msg.id}-src-${idx}`} className="source-chip">{source}</span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="message message-assistant loading">
                <div className="message-accent message-assistant" aria-hidden="true" />
                <div className="message-content">
                  <span className="message-loading-dots" aria-label="Thinking">
                    <span />
                    <span />
                    <span />
                  </span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="input-area">
            <div className="input-row">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !isLoading && handleSendMessage()}
                placeholder="Ask about dose, anomalies, maintenance..."
                disabled={isLoading}
                className="chat-input"
              />
              <button
                onClick={handleSendMessage}
                disabled={isLoading || !input.trim()}
                className="send-btn"
                title="Send message"
              >
                <ArrowUp size={16} />
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
