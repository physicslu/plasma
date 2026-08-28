import type { ReactNode } from "react";
import "./operator-panel.css";

export function OperatorPanelToggle({
  expanded,
  onClick,
  expandLabel,
  collapseLabel,
  ariaLabel,
  disabled = false,
  className = "",
}: {
  expanded: boolean;
  onClick: () => void;
  expandLabel: string;
  collapseLabel: string;
  ariaLabel: string;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={`operatorPanelToggle ${className}`.trim()}
      aria-label={ariaLabel}
      aria-expanded={expanded}
      disabled={disabled}
      onClick={onClick}
    >
      {expanded ? collapseLabel : expandLabel} {expanded ? "⌃" : "⌄"}
    </button>
  );
}

export function OperatorPanel({
  number,
  title,
  meta,
  actions,
  children,
  className = "",
  ariaLabel,
}: {
  number?: number;
  title: string;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <section className={`operatorPanel ${className}`.trim()} aria-label={ariaLabel ?? title}>
      <header className="operatorPanelHeader">
        <div className="operatorPanelTitle">
          {typeof number === "number" && <span>{number}.</span>}
          <strong>{title}</strong>
          {meta && <small>{meta}</small>}
        </div>
        {actions && <div className="operatorPanelActions">{actions}</div>}
      </header>
      <div className="operatorPanelBody">{children}</div>
    </section>
  );
}
