"use client";

import { useEffect, useMemo, useState } from "react";
import {
  configuredDeviceApiBase,
  searchDevices,
  type DeviceSearchResult,
} from "../device-catalog-api";

export type ICPickerFieldProps = {
  apiBase?: string;
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
  placeholder = "Search ICPN / IC identifier...",
}: ICPickerFieldProps) {
  const [query, setQuery] = useState(value?.icpn ?? value?.identifier ?? "");
  const [results, setResults] = useState<DeviceSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const resolvedApiBase = useMemo(() => apiBase ?? configuredDeviceApiBase(), [apiBase]);

  useEffect(() => {
    const label = value?.icpn ?? value?.identifier ?? "";
    if (label && label !== query) setQuery(label);
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const normalized = query.trim();
    const selectedLabel = value?.icpn ?? value?.identifier ?? "";
    if (!normalized || normalized === selectedLabel) {
      setResults([]);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const response = await searchDevices(normalized, {
          apiBase: resolvedApiBase,
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
  }, [query, resolvedApiBase, value]);

  function choose(device: DeviceSearchResult) {
    const label = device.icpn ?? device.identifier;
    setQuery(label);
    setResults([]);
    setOpen(false);
    onChange(device);
  }

  function update(valueText: string) {
    setQuery(valueText);
    setOpen(true);
    const selectedLabel = value?.icpn ?? value?.identifier ?? "";
    if (valueText !== selectedLabel) onChange(null);
  }

  return (
    <div className="productionIcPicker" data-selected={value ? "true" : "false"}>
      <div className="productionIcPickerInput">
        <input
          type="text"
          value={query}
          disabled={disabled}
          autoComplete="off"
          placeholder={placeholder}
          aria-label="Target IC"
          aria-expanded={open && results.length > 0}
          onFocus={() => setOpen(true)}
          onChange={event => update(event.target.value)}
        />
        <span aria-hidden="true">{loading ? "…" : "⌄"}</span>
      </div>
      {open && results.length > 0 && (
        <div className="productionIcPickerMenu" role="listbox" aria-label="Target IC search results">
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
              <small>{device.identifier_kind === "manufacturer_part_number" ? "Exact ICPN" : device.identifier_kind.replaceAll("_", " ")}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
