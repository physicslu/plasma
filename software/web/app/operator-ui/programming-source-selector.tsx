import type { ProgrammingSource } from "../engineering/bundle-programming-api";
import "./programming-source-selector.css";

export const PROGRAMMING_SOURCES: Array<{ value: ProgrammingSource; label: string }> = [
  { value: "image", label: "Image" },
  { value: "bundle", label: "Bundle" },
];

export const PROGRAMMING_SOURCE_ACCEPT: Record<ProgrammingSource, string> = {
  image: ".bin,application/octet-stream",
  bundle: ".zip,application/zip",
};

/** Shared by EMode and PMode: two mutually exclusive Programming Sources. */
export function ProgrammingSourceSelector({
  value,
  onChange,
  disabled,
  ariaLabel,
}: {
  value: ProgrammingSource;
  onChange: (source: ProgrammingSource) => void;
  disabled: boolean;
  ariaLabel: string;
}) {
  return (
    <div className="programmingSourceSelector" role="radiogroup" aria-label={ariaLabel}>
      {PROGRAMMING_SOURCES.map(source => (
        <button
          key={source.value}
          type="button"
          role="radio"
          aria-checked={value === source.value}
          data-programming-source={source.value}
          className={value === source.value ? "is-selected" : ""}
          disabled={disabled}
          onClick={() => { if (value !== source.value) onChange(source.value); }}
        >
          {source.label}
        </button>
      ))}
    </div>
  );
}
