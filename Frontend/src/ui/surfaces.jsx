import { Link } from "react-router-dom";
import { Icon } from "./Icon.jsx";

export function Card({ title, actions, children, className = "", as: Tag = "section", headingLevel = 2, ...rest }) {
  const Heading = `h${headingLevel}`;
  return (
    <Tag className={`card ${className}`} {...rest}>
      {title || actions ? (
        <div className="card-header">
          {title ? <Heading className="card-title">{title}</Heading> : <span />}
          {actions ? <div className="cluster">{actions}</div> : null}
        </div>
      ) : null}
      <div className="card-body">{children}</div>
    </Tag>
  );
}

export function PageHeader({ title, description, actions, back }) {
  return (
    <header className="page-header">
      <div>
        {back ? (
          <Link className="back-link" to={back.to}>
            <Icon name="arrowLeft" /> {back.label}
          </Link>
        ) : null}
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="cluster">{actions}</div> : null}
    </header>
  );
}

const BANNER_ICONS = { info: "info", warning: "alert", danger: "alertCircle", success: "checkCircle" };

export function Banner({ tone = "info", title, children, role }) {
  return (
    <div className={`banner banner-${tone}`} role={role ?? (tone === "danger" ? "alert" : undefined)}>
      <Icon name={BANNER_ICONS[tone]} />
      <div>
        {title ? <p><strong>{title}</strong></p> : null}
        {children}
      </div>
    </div>
  );
}

export function Pill({ tone, children }) {
  return <span className={`pill${tone ? ` pill-${tone}` : ""}`}>{children}</span>;
}

export function LoanStatus({ status }) {
  return status === "closed" ? <Pill>Closed</Pill> : <Pill tone="success">Open</Pill>;
}

export function Details({ items }) {
  return (
    <dl className="details">
      {items.filter(Boolean).map(([term, value]) => (
        <div key={term}>
          <dt>{term}</dt>
          <dd>{value ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function SummaryList({ rows }) {
  return (
    <dl className="summary-list">
      {rows.filter(Boolean).map(({ label, value, total }) => (
        <div key={label} className={total ? "total" : undefined}>
          <dt>{label}</dt>
          <dd className="num">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Stepper({ steps, current }) {
  return (
    <ol className="stepper" aria-label="Progress">
      {steps.map((step, index) => (
        <li
          key={step}
          aria-current={index === current ? "step" : undefined}
          data-state={index < current ? "done" : undefined}
        >
          <span>
            {step}
            {index < current ? <span className="visually-hidden"> (completed)</span> : null}
          </span>
        </li>
      ))}
    </ol>
  );
}
