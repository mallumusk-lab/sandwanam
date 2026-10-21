import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { Button, IconButton, Spinner } from "./controls.jsx";
import { Icon } from "./Icon.jsx";

export function EmptyState({ icon = "info", title, children, action, headingLevel = 3 }) {
  const Heading = `h${headingLevel}`;
  return (
    <div className="state">
      <div className="state-icon">
        <Icon name={icon} />
      </div>
      <Heading>{title}</Heading>
      {children ? <p>{children}</p> : null}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry, title = "This couldn't be loaded" }) {
  return (
    <div className="state state-error" role="alert">
      <div className="state-icon">
        <Icon name="alertCircle" />
      </div>
      <h3>{title}</h3>
      <p>{error?.message ?? "Something went wrong."}</p>
      {onRetry ? (
        <Button icon="refresh" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function Skeleton({ width = "100%", height = "1rem" }) {
  return <span className="skeleton" style={{ width, height }} aria-hidden="true" />;
}

export function SkeletonRows({ rows = 5, label = "Loading" }) {
  return (
    <div className="stack stack-sm" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} height="2.5rem" />
      ))}
    </div>
  );
}

export function PageLoading({ label = "Loading…" }) {
  return (
    <div className="page-loading">
      <Spinner label={label} />
    </div>
  );
}

/* ── Toasts: polite live region, auto-dismiss, closable ─────────────────────── */
const ToastContext = createContext(null);
const TOAST_ICONS = { success: "checkCircle", error: "alertCircle", info: "info" };

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const counter = useRef(0);
  const timers = useRef(new Map());

  const dismiss = useCallback((id) => {
    clearTimeout(timers.current.get(id));
    timers.current.delete(id);
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const schedule = useCallback(
    (id, duration) => {
      clearTimeout(timers.current.get(id));
      timers.current.set(id, setTimeout(() => dismiss(id), duration));
    },
    [dismiss],
  );

  const show = useCallback(
    (tone, title, message, { duration = tone === "error" ? 10000 : 6000 } = {}) => {
      const id = ++counter.current;
      setToasts((current) => [...current.slice(-3), { id, tone, title, message, duration }]);
      schedule(id, duration);
      return id;
    },
    [schedule],
  );

  const pause = useCallback((id) => clearTimeout(timers.current.get(id)), []);

  const renderToast = (toast) => (
    <div key={toast.id} className={`toast toast-${toast.tone}`}
      onMouseEnter={() => pause(toast.id)} onMouseLeave={() => schedule(toast.id, toast.duration)}
      onFocus={() => pause(toast.id)} onBlur={() => schedule(toast.id, toast.duration)}>
      <Icon name={TOAST_ICONS[toast.tone]} />
      <div className="toast-body">
        <strong>{toast.title}</strong>
        {toast.message ? <span>{toast.message}</span> : null}
      </div>
      <IconButton icon="x" label="Dismiss notification" onClick={() => dismiss(toast.id)} />
    </div>
  );

  const api = useMemo(
    () => ({
      success: (title, message, options) => show("success", title, message, options),
      error: (title, message, options) => show("error", title, message, options),
      info: (title, message, options) => show("info", title, message, options),
      dismiss,
    }),
    [show, dismiss],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-region">
        {/* Always-present live regions: screen readers only announce changes inside them. */}
        <div role="alert" className="toast-stack">
          {toasts.filter((t) => t.tone === "error").map(renderToast)}
        </div>
        <div role="status" aria-live="polite" className="toast-stack">
          {toasts.filter((t) => t.tone !== "error").map(renderToast)}
        </div>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside <ToastProvider>");
  return context;
}
