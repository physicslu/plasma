import { useRef } from "react";
import type { ChangeEvent, ReactNode } from "react";
import type { DeviceSearchResult } from "../device-catalog-api";
import { ICPickerField } from "../devices/ic-picker-field";
import { OperatorPanel } from "./operator-panel";

export type ProgrammingJobOperation = {
  key: string;
  code: string;
  label: string;
  checked: boolean;
  disabled: boolean;
  ariaLabel?: string;
  onChange: () => void;
};

export type ProgrammingJobPolicyOption = {
  value: string;
  label: string;
};

export type ProgrammingJobPolicy = {
  repeatLabel: string;
  repeatValue: string;
  repeatDisabled: boolean;
  repeatAriaLabel: string;
  onRepeatChange: (value: string) => void;
  retryLabel: string;
  retryValue: string;
  retryDisabled: boolean;
  retryAriaLabel: string;
  onRetryChange: (value: string) => void;
  stopLabel: string;
  stopValue: string;
  stopDisabled: boolean;
  stopAriaLabel: string;
  stopOptions: ProgrammingJobPolicyOption[];
  onStopChange: (value: string) => void;
};

export type ProgrammingJobImage = {
  name: string;
  title?: string;
  source?: string;
  hint: ReactNode;
  browseLabel: string;
  browseDisabled: boolean;
  inputDisabled: boolean;
  inputAriaLabel: string;
  onFileChange: (file: File | null, event: ChangeEvent<HTMLInputElement>) => void;
};

export function ProgrammingJobPanel({
  mode,
  title,
  collapsed,
  onToggleCollapsed,
  expandLabel,
  collapseLabel,
  apiBase,
  targetDevice,
  onTargetChange,
  targetDisabled,
  targetPlaceholder,
  targetLabel,
  imageLabel,
  image,
  operationsLabel,
  operations,
  policyLabel,
  policy,
  compatibilityFields,
  startLabel,
  startDisabled,
  onStart,
  statusLabel,
  statusValue,
  statusClassName = "",
  abortLabel,
  abortDisabled,
  onAbort,
}: {
  mode: "production" | "engineering";
  title: string;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  expandLabel: string;
  collapseLabel: string;
  apiBase: string;
  targetDevice: DeviceSearchResult | null;
  onTargetChange: (device: DeviceSearchResult | null) => void;
  targetDisabled: boolean;
  targetPlaceholder?: string;
  targetLabel: string;
  imageLabel: string;
  image: ProgrammingJobImage;
  operationsLabel: string;
  operations: ProgrammingJobOperation[];
  policyLabel: string;
  policy: ProgrammingJobPolicy;
  compatibilityFields?: ReactNode;
  startLabel: string;
  startDisabled: boolean;
  onStart: () => void | Promise<void>;
  statusLabel: string;
  statusValue: ReactNode;
  statusClassName?: string;
  abortLabel: string;
  abortDisabled: boolean;
  onAbort: () => void | Promise<void>;
}) {
  const toggleLabel = collapsed ? expandLabel : collapseLabel;
  const imageInputRef = useRef<HTMLInputElement>(null);

  return (
    <OperatorPanel
      number={2}
      title={title}
      className={`programmingJobPanel unifiedBatchControlStack ${collapsed ? "is-collapsed" : ""}`}
      ariaLabel={`${mode === "production" ? "Production" : "Engineering"} Programming Job`}
      actions={(
        <button
          type="button"
          className="programmingJobCollapseButton"
          aria-label={`${collapsed ? "Expand" : "Collapse"} ${mode === "production" ? "Production" : "Engineering"} Programming Job`}
          aria-expanded={!collapsed}
          onClick={onToggleCollapsed}
        >
          {toggleLabel} {collapsed ? "⌄" : "⌃"}
        </button>
      )}
    >
      {!collapsed && (
        <div className="programmingJobGrid" data-programming-job-fields={mode}>
          <div className="programmingJobField" data-programming-job-field="target">
            <strong>1. {targetLabel}</strong>
            <ICPickerField
              apiBase={apiBase}
              value={targetDevice}
              onChange={onTargetChange}
              disabled={targetDisabled}
              placeholder={targetPlaceholder}
            />
          </div>

          <div className="programmingJobField programmingJobImageField" data-programming-job-field="image">
            <strong>2. {imageLabel}</strong>
            <div className="programmingJobImageControl">
              <span data-image-source={image.source} title={image.title ?? image.name}>{image.name}</span>
              <button type="button" disabled={image.browseDisabled} onClick={() => imageInputRef.current?.click()}>{image.browseLabel}</button>
              <input
                ref={imageInputRef}
                type="file"
                aria-label={image.inputAriaLabel}
                accept=".bin,application/octet-stream"
                hidden
                disabled={image.inputDisabled}
                onChange={event => image.onFileChange(event.target.files?.[0] ?? null, event)}
              />
            </div>
            <small>{image.hint}</small>
          </div>

          <div className="programmingJobField" data-programming-job-field="operations">
            <strong>3. {operationsLabel}</strong>
            <div className="programmingJobOperationChecks" role="group" aria-label={`${mode === "production" ? "Production" : "Engineering"} batch operations`}>
              {operations.map(operation => (
                <label key={operation.key}>
                  <input
                    type="checkbox"
                    aria-label={operation.ariaLabel}
                    checked={operation.checked}
                    disabled={operation.disabled}
                    onChange={operation.onChange}
                  />
                  <b>{operation.code}</b>
                  <span>{operation.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="programmingJobField" data-programming-job-field="policy">
            <strong>4. {policyLabel}</strong>
            <div className="programmingJobPolicyControls">
              <label>{policy.repeatLabel}<input aria-label={policy.repeatAriaLabel} type="number" min="1" max="10000" value={policy.repeatValue} disabled={policy.repeatDisabled} onChange={event => policy.onRepeatChange(event.target.value)} /></label>
              <label>{policy.retryLabel}<input aria-label={policy.retryAriaLabel} type="number" min="0" max="20" value={policy.retryValue} disabled={policy.retryDisabled} onChange={event => policy.onRetryChange(event.target.value)} /></label>
              <label>{policy.stopLabel}
                <select aria-label={policy.stopAriaLabel} value={policy.stopValue} disabled={policy.stopDisabled} onChange={event => policy.onStopChange(event.target.value)}>
                  {policy.stopOptions.map(option => <option value={option.value} key={option.value || "never"}>{option.label}</option>)}
                </select>
              </label>
            </div>
          </div>
        </div>
      )}

      {compatibilityFields && <div className="programmingJobCompatibility" hidden>{compatibilityFields}</div>}

      <div className="programmingJobActionBar" data-programming-job-actions={mode}>
        <button type="button" className="programmingJobStart" data-programming-job-action="start" disabled={startDisabled} onClick={() => void onStart()}>▶ {startLabel}</button>
        <div className={`programmingJobStatus ${statusClassName}`.trim()} data-programming-job-action="status" role="status" aria-label={statusLabel}>
          <small>{statusLabel}</small>
          <b>{statusValue}</b>
        </div>
        <button type="button" className="programmingJobAbort" data-programming-job-action="abort" disabled={abortDisabled} onClick={() => void onAbort()}>■ {abortLabel}</button>
      </div>
    </OperatorPanel>
  );
}
