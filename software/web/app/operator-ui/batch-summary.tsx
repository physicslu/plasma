import type { ReactNode } from "react";
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
    <section className={`batchSummary ${title ? "has-title" : ""}`.trim()} aria-label={ariaLabel}>
      {title && (
        <header className="batchSummaryHeader">
          <strong>{title}</strong>
          {meta && <small>{meta}</small>}
        </header>
      )}
      <div className="batchSummaryGrid">
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
