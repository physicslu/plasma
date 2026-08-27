"use client";

import { useEffect, useSyncExternalStore } from "react";
import {
  clearSecurityBearerToken,
  getSecurityTransportServerState,
  getSecurityTransportState,
  installSecurityTransport,
  setSecurityBearerToken,
  subscribeSecurityTransport,
} from "./security-transport";

export function SecurityTransportProvider({ children }: { children: React.ReactNode }) {
  if (typeof window !== "undefined") installSecurityTransport();

  const state = useSyncExternalStore(
    subscribeSecurityTransport,
    getSecurityTransportState,
    getSecurityTransportServerState,
  );

  useEffect(() => installSecurityTransport(), []);

  function configureCredential() {
    const value = window.prompt(
      state.credentialLoaded
        ? "Replace Plasma Bearer token. Leave blank to clear the current in-memory credential."
        : "Paste Plasma Bearer token. It is kept only in browser memory and is cleared on full reload.",
      "",
    );
    if (value === null) return;
    if (!value.trim()) {
      clearSecurityBearerToken();
      return;
    }
    try {
      setSecurityBearerToken(value);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Invalid Plasma Bearer token");
    }
  }

  const label = state.authenticationRequired
    ? "AUTH REQUIRED"
    : state.credentialLoaded
      ? "AUTH READY"
      : "AUTH OFF";

  return (
    <>
      {children}
      <button
        type="button"
        className={`securityCredentialControl ${state.authenticationRequired ? "required" : state.credentialLoaded ? "ready" : "off"}`}
        onClick={configureCredential}
        aria-label="Configure Plasma Bearer credential"
        title="Bearer credential is memory-only and is never written to localStorage/sessionStorage."
      >
        <span aria-hidden="true">●</span>
        {label}
      </button>
    </>
  );
}
