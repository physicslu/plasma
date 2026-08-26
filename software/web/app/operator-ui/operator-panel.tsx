import type { ReactNode } from "react";
import { BatchSummary, type BatchSummaryProps } from "./batch-summary";
import "./operator-panel.css";

export { BatchSummary, type BatchSummaryProps, type OperatorKpi } from "./batch-summary";

/* Compatibility entry point for existing PMode / EMode call sites. Both now
 * render the canonical shared BatchSummary component and therefore cannot
 * drift visually through separate markup implementations. */
export function OperatorKpiStrip(props: BatchSummaryProps) {
  return <BatchSummary {...props} />;
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
