import { forwardRef, useId, useState } from "react";
import { Link } from "react-router-dom";
import { Icon } from "./Icon.jsx";
import { applyTheme, storedTheme } from "./theme.js";

export function Spinner({ label }) {
  return label ? (
    <span role="status" className="cluster cluster-sm">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </span>
  ) : (
    <span className="spinner" aria-hidden="true" />
  );
}

/**
 * Buttons stay focusable while busy (aria-disabled) so screen readers keep their place;
 * clicks are ignored until the action finishes.
 */
export const Button = forwardRef(function Button({
  variant = "secondary",
  size,
  icon,
  loading = false,
  block = false,
  to,
  className = "",
  children,
  onClick,
  type = "button",
  disabled,
  ...rest
}, ref) {
  const classes = ["btn", `btn-${variant}`, size === "sm" ? "btn-sm" : "", block ? "btn-block" : "", className]
    .filter(Boolean)
    .join(" ");
  const content = (
    <>
      {loading ? <Spinner /> : null}
      {icon ? <Icon name={icon} /> : null}
      {children}
    </>
  );
  if (to) {
    return (
      <Link ref={ref} to={to} className={classes} {...rest}>
        {content}
      </Link>
    );
  }
  return (
    <button
      ref={ref}
      type={type}
      className={classes}
      disabled={disabled}
      aria-busy={loading || undefined}
      aria-disabled={loading || undefined}
      onClick={(event) => {
        if (loading) {
          event.preventDefault();
          return;
        }
        onClick?.(event);
      }}
      {...rest}
    >
      {content}
    </button>
  );
});

export const IconButton = forwardRef(function IconButton({ icon, label, className = "", ...rest }, ref) {
  return (
    <button ref={ref} type="button" className={`icon-btn ${className}`} aria-label={label} title={label} {...rest}>
      <Icon name={icon} />
    </button>
  );
});

/** A group of radio buttons that looks like a segmented control. */
export function Segmented({ label, options, value, onChange }) {
  const name = useId();
  return (
    <fieldset>
      <legend className="visually-hidden">{label}</legend>
      <div className="segmented">
        {options.map((option) => (
          <label key={option.value}>
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function Pagination({ page, pageSize, total, onPage, label = "Pages" }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total === 0) return null;
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(total, page * pageSize);
  return (
    <nav className="pagination" aria-label={label}>
      <span className="muted">
        Showing {first.toLocaleString("en-IN")}–{last.toLocaleString("en-IN")} of {total.toLocaleString("en-IN")}
      </span>
      <div className="cluster cluster-sm">
        <Button size="sm" icon="chevronLeft" aria-disabled={page <= 1 || undefined} onClick={() => page > 1 && onPage(page - 1)}>
          Previous
        </Button>
        <span aria-current="page">
          Page {page} of {pages}
        </span>
        <Button size="sm" aria-disabled={page >= pages || undefined} onClick={() => page < pages && onPage(page + 1)}>
          Next <Icon name="chevronRight" />
        </Button>
      </div>
    </nav>
  );
}

const THEME_ORDER = ["system", "light", "dark"];
const THEME_LABELS = { system: "Theme: match device", light: "Theme: light", dark: "Theme: dark" };
const THEME_ICONS = { system: "monitor", light: "sun", dark: "moon" };

export function ThemeToggle({ className }) {
  const [theme, setTheme] = useState(storedTheme);
  const next = THEME_ORDER[(THEME_ORDER.indexOf(theme) + 1) % THEME_ORDER.length];
  return (
    <IconButton
      className={className}
      icon={THEME_ICONS[theme]}
      label={`${THEME_LABELS[theme]}. Switch to ${next}.`}
      onClick={() => setTheme(applyTheme(next))}
    />
  );
}
