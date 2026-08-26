import type { ReactNode } from "react";
import "./operator-panel.css";

export {
  BatchSummary,
  BatchSummary as OperatorKpiStrip,
  type BatchSummaryProps,
  type OperatorKpi,
} from "./batch-summary";

/* `operatorKpiStrip` is retained only as historical migration vocabulary for
 * source-contract traceability. `OperatorKpiStrip` is now a module-level alias
 * of BatchSummary, not a wrapper component and not a visual-style owner. */

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
