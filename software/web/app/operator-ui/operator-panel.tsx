import type { ReactNode } from "react";
import "./operator-panel.css";

export type OperatorKpi = {
  key: string;
  label: string;
  value: ReactNode;
  tone?: "neutral" | "info" | "pass" | "fail";
};

export function OperatorKpiStrip({ items, ariaLabel }: { items: OperatorKpi[]; ariaLabel: string }) {
  return (
    <section className="operatorKpiStrip" aria-label={ariaLabel}>
      {items.map(item => (
        <article key={item.key} data-kpi={item.key} data-tone={item.tone ?? "neutral"}>
          <small>{item.label}</small>
          <b>{item.value}</b>
        </article>
      ))}
    </section>
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
