import type { ReactNode } from "react";
import "./operator-panel.css";
import "./batch-summary.css";

export type OperatorKpi = {
  key: string;
  label: string;
  value: ReactNode;
  tone?: "neutral" | "info" | "pass" | "fail";
};

export type BatchSummaryProps = {
  items: OperatorKpi[];
  ariaLabel: string;
  title?: string;
  meta?: ReactNode;
};

export function BatchSummary({
  items,
  ariaLabel,
  title,
  meta,
}: BatchSummaryProps) {
  return (
    <section className={`batchSummary operatorKpiSummary ${title ? "has-title" : ""}`.trim()} aria-label={ariaLabel}>
      {title && (
        <header className="operatorKpiSummaryHeader">
          <strong>{title}</strong>
          {meta && <small>{meta}</small>}
        </header>
      )}
      <div className="operatorKpiStrip">
        {items.map(item => (
          <article key={item.key} data-kpi={item.key} data-tone={item.tone ?? "neutral"}>
            <small>{item.label}</small>
            <b>{item.value}</b>
          </article>
        ))}
      </div>
    </section>
  );
}

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
