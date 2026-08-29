import type { ReactNode } from "react";

export function DiagnosticsTestPage({
  eyebrow,
  title,
  description,
  help,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  help?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="diagnosticsTestPage">
      <header className="diagnosticsTestHeader">
        <div>
          <p>{eyebrow}</p>
          <h2>{title}</h2>
          <span>{description}</span>
        </div>
        {help && <div className="diagnosticsTestHelp">{help}</div>}
      </header>
      {children}
    </section>
  );
}

export function DiagnosticsTestCard({
  title,
  description,
  className = "",
  children,
}: {
  title: string;
  description?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`diagnosticsTestCard ${className}`.trim()}>
      <header>
        <h3>{title}</h3>
        {description && <p>{description}</p>}
      </header>
      <div className="diagnosticsTestCardBody">{children}</div>
    </section>
  );
}

export function DiagnosticsTestNotice({ children }: { children: ReactNode }) {
  return (
    <div className="diagnosticsTestNotice" role="status">
      <span aria-hidden="true">i</span>
      <div>{children}</div>
    </div>
  );
}
