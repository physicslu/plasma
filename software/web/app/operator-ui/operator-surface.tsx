import type { ButtonHTMLAttributes, ReactNode } from "react";

function joinClasses(...parts: Array<string | undefined | false>): string {
  return parts.filter(Boolean).join(" ");
}

export function OperatorCard({
  children,
  className,
  ariaLabel,
}: {
  children: ReactNode;
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <section className={joinClasses("operatorCard", className)} aria-label={ariaLabel}>
      {children}
    </section>
  );
}

export function OperatorField({
  label,
  hint,
  unit,
  children,
  className,
  controlClassName,
}: {
  label: ReactNode;
  hint?: ReactNode;
  unit?: ReactNode;
  children: ReactNode;
  className?: string;
  controlClassName?: string;
}) {
  return (
    <label className={joinClasses("operatorField", className)}>
      <span>{label}</span>
      <div className={joinClasses("operatorFieldControl", controlClassName)}>
        {children}
        {unit && <b>{unit}</b>}
      </div>
      {hint && <small>{hint}</small>}
    </label>
  );
}

export function OperatorActions({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={joinClasses("operatorActions", className)}>{children}</div>;
}

export function OperatorButton({
  variant = "secondary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "secondary" | "primary" | "danger";
}) {
  return (
    <button
      {...props}
      className={joinClasses("operatorButton", className)}
      data-variant={variant}
    />
  );
}

export function OperatorMessage({
  tone,
  children,
  role,
  className,
}: {
  tone: "error" | "success" | "info" | "warning";
  children: ReactNode;
  role?: "alert" | "status";
  className?: string;
}) {
  return (
    <p className={joinClasses("operatorMessage", className)} data-tone={tone} role={role}>
      {children}
    </p>
  );
}
