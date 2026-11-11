import { useRef } from "react";
import type { ChangeEvent, ReactNode } from "react";
import { batchReadinessGuidanceFromLabel } from "../batch-readiness";
import type { DeviceSearchResult } from "../device-catalog-api";
import { ICPickerField } from "../devices/ic-picker-field";
import { useI18n } from "../i18n";
import { OperatorPanel, OperatorPanelToggle } from "./operator-panel";
import type { ProgrammingSource } from "../engineering/bundle-programming-api";
import { ProgrammingSourceSelector } from "./programming-source-selector";
import "./programming-job-controls.css";
import "./production-workflow-guidance.css";

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
  /** Shown under the controls, e.g. why a policy is unavailable. */
  note?: ReactNode;
};

/** Programming Image / Bundle selector; only the formal managed backend offers it. */
export type ProgrammingJobSource = {
  value: ProgrammingSource;
  disabled: boolean;
  onChange: (source: ProgrammingSource) => void;
};

export type ProgrammingJobImage = {
  name: string;
  title?: string;
  source?: string;
  hint: ReactNode;
  /** Size and format of the picked file, shown under its name. */
  details?: ReactNode;
  browseLabel: string;
  browseDisabled: boolean;
  inputDisabled: boolean;
  inputAriaLabel: string;
  /** File types offered by the picker; defaults to a binary Image. */
  accept?: string;
  onFileChange: (file: File | null, event: ChangeEvent<HTMLInputElement>) => void;
};

export function ProgrammingJobPanel({
  mode,
  title,
  collapsed,
  onToggleCollapsed,
  expandLabel,
  collapseLabel,
  targetDevice,
  onTargetChange,
  targetDisabled,
  targetPlaceholder,
  targetLabel,
  targetLevels,
  imageLabel,
  image,
  source,
  operationsLabel,
  operations,
  policyLabel,
  policy,
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
  targetDevice: DeviceSearchResult | null;
  onTargetChange: (device: DeviceSearchResult | null) => void;
  targetDisabled: boolean;
  targetPlaceholder?: string;
  targetLabel: string;
  /** Catalog Levels offered by the IC Picker (display filter, never a gate). */
  targetLevels?: Array<1 | 2 | 3>;
  imageLabel: string;
  image: ProgrammingJobImage;
  source?: ProgrammingJobSource;
  operationsLabel: string;
  operations: ProgrammingJobOperation[];
  policyLabel: string;
  policy: ProgrammingJobPolicy;
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
  const { locale } = useI18n();
  const imageInputRef = useRef<HTMLInputElement>(null);
  const modeLabel = mode === "production" ? "Production" : "Engineering";
  const statusText = typeof statusValue === "string" ? statusValue : null;
  const readinessGuidance = statusText ? batchReadinessGuidanceFromLabel(statusText, locale) : null;
  const disabledStartTitle = startDisabled && statusText !== "BATCH READY" ? readinessGuidance ?? undefined : undefined;

  return (
    <OperatorPanel
      number={2}
      title={title}
      className={`programmingJobPanel unifiedBatchControlStack ${collapsed ? "is-collapsed" : ""}`}
      ariaLabel={`${modeLabel} Programming Job`}
      actions={(
        <OperatorPanelToggle
          expanded={!collapsed}
          expandLabel={expandLabel}
          collapseLabel={collapseLabel}
          ariaLabel={`${collapsed ? "Expand" : "Collapse"} ${modeLabel} Programming Job`}
          onClick={onToggleCollapsed}
        />
      )}
    >
      {!collapsed && (
        <div className="programmingJobGrid" data-programming-job-fields={mode}>
          <div className="programmingJobField" data-programming-job-field="target">
            <strong>1. {targetLabel}</strong>
            <ICPickerField
              value={targetDevice}
              onChange={onTargetChange}
              disabled={targetDisabled}
              placeholder={targetPlaceholder}
              levels={targetLevels}
            />
          </div>

          <div className="programmingJobField programmingJobImageField" data-programming-job-field="image">
            <strong>2. {imageLabel}</strong>
            {source && (
              <ProgrammingSourceSelector
                value={source.value}
                disabled={source.disabled}
                ariaLabel={`${modeLabel} Programming Source`}
                onChange={next => {
                  // A file picked for one Source must never be sent as the other.
                  if (imageInputRef.current) imageInputRef.current.value = "";
                  source.onChange(next);
                }}
              />
            )}
            <div className="programmingJobImageControl">
              <span data-image-source={image.source} title={image.title ?? image.name}>{image.name}</span>
              <button type="button" disabled={image.browseDisabled} onClick={() => imageInputRef.current?.click()}>{image.browseLabel}</button>
              <input
                ref={imageInputRef}
                type="file"
                aria-label={image.inputAriaLabel}
                accept={image.accept ?? ".bin,application/octet-stream"}
                hidden
                disabled={image.inputDisabled}
                onChange={event => image.onFileChange(event.target.files?.[0] ?? null, event)}
              />
            </div>
            {image.details && <small className="programmingJobImageDetails" data-image-details>{image.details}</small>}
            <small>{image.hint}</small>
          </div>

          <div className="programmingJobField" data-programming-job-field="operations">
            <strong>3. {operationsLabel}</strong>
            <div className="programmingJobOperationChecks" role="group" aria-label={`${modeLabel} batch operations`}>
              {operations.map(operation => (
                <label key={operation.key}>
                  <input
                    type="checkbox"
                    data-programming-job-operation={operation.key}
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
              <label>{policy.repeatLabel}<input data-programming-job-policy="repeat" aria-label={policy.repeatAriaLabel} type="number" min="1" max="10000" value={policy.repeatValue} disabled={policy.repeatDisabled} onChange={event => policy.onRepeatChange(event.target.value)} /></label>
              <label>{policy.retryLabel}<input data-programming-job-policy="retry" aria-label={policy.retryAriaLabel} type="number" min="0" max="20" value={policy.retryValue} disabled={policy.retryDisabled} onChange={event => policy.onRetryChange(event.target.value)} /></label>
              <label>{policy.stopLabel}
                <select data-programming-job-policy="stop" aria-label={policy.stopAriaLabel} value={policy.stopValue} disabled={policy.stopDisabled} onChange={event => policy.onStopChange(event.target.value)}>
                  {policy.stopOptions.map(option => <option value={option.value} key={option.value || "never"}>{option.label}</option>)}
                </select>
              </label>
            </div>
            {policy.note && <small className="programmingJobPolicyNote" data-programming-job-policy="note">{policy.note}</small>}
          </div>
        </div>
      )}

      <div className="programmingJobActionBar" data-programming-job-actions={mode}>
        <button
          type="button"
          className="programmingJobStart"
          data-programming-job-action="start"
          disabled={startDisabled}
          title={disabledStartTitle}
          onClick={() => void onStart()}
        >
          ▶ {startLabel}
        </button>
        <div className={`programmingJobStatus ${statusClassName}`.trim()} data-programming-job-action="status" role="status" aria-label={statusLabel}>
          <small>{statusLabel}</small>
          <b>{statusValue}</b>
          {readinessGuidance && <span className="programmingJobStatusHint">{readinessGuidance}</span>}
        </div>
        <button type="button" className="programmingJobAbort" data-programming-job-action="abort" disabled={abortDisabled} onClick={() => void onAbort()}>■ {abortLabel}</button>
      </div>
    </OperatorPanel>
  );
}
