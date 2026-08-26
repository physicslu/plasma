import type { ReactNode } from "react";
import "./settings-ui.css";

function joinClasses(...parts: Array<string | undefined | false>): string {
  return parts.filter(Boolean).join(" ");
}

export type SettingsGuideItem = {
  term: ReactNode;
  description: ReactNode;
};

export type SettingsGuideTest = {
  title?: ReactNode;
  description: ReactNode;
};

export function SettingsPage({
  eyebrow,
  title,
  subtitle,
  revision,
  children,
  ariaLabel,
  className,
}: {
  eyebrow: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  revision?: ReactNode;
  children: ReactNode;
  ariaLabel: string;
  className?: string;
}) {
  return (
    <section className={joinClasses("settingsPage", className)} aria-label={ariaLabel}>
      <header className="settingsPageHeader">
        <div>
          <small>{eyebrow}</small>
          <h1>{title}</h1>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {revision !== undefined && revision !== null && <span className="settingsRevisionBadge">REV {revision}</span>}
      </header>
      {children}
    </section>
  );
}

export function SettingsTabs({ children, ariaLabel }: { children: ReactNode; ariaLabel: string }) {
  return <nav className="settingsTabs" aria-label={ariaLabel}>{children}</nav>;
}

export function SettingsCard({
  eyebrow,
  title,
  description,
  children,
  ariaLabel,
  className,
}: {
  eyebrow?: ReactNode;
  title?: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  ariaLabel?: string;
  className?: string;
}) {
  return (
    <section className={joinClasses("settingsCard", className)} aria-label={ariaLabel}>
      {(eyebrow || title || description) && (
        <header className="settingsCardHeader">
          {eyebrow && <small>{eyebrow}</small>}
          {title && <h2>{title}</h2>}
          {description && <p>{description}</p>}
        </header>
      )}
      {children}
    </section>
  );
}

export function SettingsGrid({
  columns = 2,
  children,
  className,
}: {
  columns?: 1 | 2 | 3 | 4;
  children: ReactNode;
  className?: string;
}) {
  return <div className={joinClasses("settingsGrid", className)} data-columns={columns}>{children}</div>;
}

export function SettingsField({
  label,
  hint,
  unit,
  children,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  unit?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={joinClasses("settingsField", className)}>
      <span>{label}</span>
      <div className="settingsFieldControl">
        {children}
        {unit && <b>{unit}</b>}
      </div>
      {hint && <small>{hint}</small>}
    </label>
  );
}

export function SettingsActions({ children }: { children: ReactNode }) {
  return <div className="settingsActions">{children}</div>;
}

export function SettingsMessage({
  tone,
  children,
  role,
}: {
  tone: "error" | "success" | "info";
  children: ReactNode;
  role?: "alert" | "status";
}) {
  return <p className="settingsMessage" data-tone={tone} role={role}>{children}</p>;
}

export function SettingsMetaGrid({
  items,
}: {
  items: Array<{ key: string; label: ReactNode; value: ReactNode }>;
}) {
  return (
    <dl className="settingsMetaGrid">
      {items.map(item => (
        <div key={item.key}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function SettingsGuide({
  eyebrow,
  title,
  intro,
  items,
  testTitle,
  testIntro,
  tests,
  caution,
  ariaLabel,
}: {
  eyebrow: ReactNode;
  title: ReactNode;
  intro: ReactNode;
  items: SettingsGuideItem[];
  testTitle: ReactNode;
  testIntro: ReactNode;
  tests: SettingsGuideTest[];
  caution: ReactNode;
  ariaLabel: string;
}) {
  return (
    <section className="settingsGuide" aria-label={ariaLabel}>
      <header>
        <small>{eyebrow}</small>
        <h2>{title}</h2>
        <p>{intro}</p>
      </header>
      <div className="settingsGuideGrid">
        <article>
          <dl>
            {items.map((item, index) => (
              <div key={index}>
                <dt>{item.term}</dt>
                <dd>{item.description}</dd>
              </div>
            ))}
          </dl>
        </article>
        <article>
          <h3>{testTitle}</h3>
          <p>{testIntro}</p>
          <ol>
            {tests.map((entry, index) => (
              <li key={index}>
                {entry.title && <b>{entry.title}</b>}
                <span>{entry.description}</span>
              </li>
            ))}
          </ol>
        </article>
      </div>
      <p className="settingsGuideCaution">{caution}</p>
    </section>
  );
}
