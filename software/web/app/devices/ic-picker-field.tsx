"use client";

import { useEffect, useState } from "react";
import {
  searchDevices,
  type DeviceSearchResult,
} from "../device-catalog-api";
import "./ic-picker-field.css";

export type ICPickerFieldProps = {
  apiBase: string;
  value: DeviceSearchResult | null;
  onChange: (device: DeviceSearchResult | null) => void;
  disabled?: boolean;
  placeholder?: string;
};

export function ICPickerField({
  apiBase,
  value,
  onChange,
  disabled = false,
  placeholder = "Search admitted ICPN...",
}: ICPickerFieldProps) {
  const [query, setQuery] = useState(value?.icpn ?? value?.identifier ?? "");
  const [results, setResults] = useState<DeviceSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const normalized = query.trim();
    const selectedLabel = value?.icpn ?? value?.identifier ?? "";
    if (!normalized || normalized === selectedLabel) return;

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const response = await searchDevices(normalized, {
          apiBase,
          limit: 8,
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setResults(response.results);
          setOpen(true);
        }
      } catch {
        if (!controller.signal.aborted) setResults([]);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 160);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [apiBase, query, value]);

  function choose(device: DeviceSearchResult) {
    const label = device.icpn ?? device.identifier;
    setQuery(label);
    setResults([]);
    setOpen(false);
    setLoading(false);
    onChange(device);
  }

  function update(valueText: string) {
    setQuery(valueText);
    setResults([]);
    setLoading(false);
    setOpen(true);
    const selectedLabel = value?.icpn ?? value?.identifier ?? "";
    if (valueText !== selectedLabel) onChange(null);
  }

  return (
    <div className="icPicker" data-selected={value ? "true" : "false"}>
      <div className="icPickerInput">
        <input
          type="text"
          value={query}
          disabled={disabled}
          autoComplete="off"
          placeholder={placeholder}
          aria-label="Target IC"
          onFocus={() => setOpen(true)}
          onChange={event => update(event.target.value)}
        />
        <span aria-hidden="true">{loading ? "…" : "⌄"}</span>
      </div>
      {open && results.length > 0 && (
        <div className="icPickerMenu" role="listbox" aria-label="Target IC search results">
          {results.map(device => (
            <button
              type="button"
              role="option"
              aria-selected={value?.identifier === device.identifier && value?.vendor === device.vendor}
              key={`${device.vendor}:${device.identifier}`}
              onMouseDown={event => event.preventDefault()}
              onClick={() => choose(device)}
            >
              <b>{device.icpn ?? device.identifier}</b>
              <span>{device.vendor} · {device.family}</span>
              <small>
                Exact ICPN · {device.backend.mapping_status === "mapped" ? "OCD Mapped" : device.backend.mapping_status}
              </small>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
