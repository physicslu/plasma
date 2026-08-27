"use client";

import { useEffect, useState, useSyncExternalStore, type FormEvent } from "react";
import {
  clearSecurityBearerToken,
  getSecurityTransportServerState,
  getSecurityTransportState,
  installSecurityTransport,
  setSecurityBearerToken,
  subscribeSecurityTransport,
} from "./security-transport";

export function SecurityTransportProvider({ children }: { children: React.ReactNode }) {
  const state = useSyncExternalStore(
    subscribeSecurityTransport,
    getSecurityTransportState,
    getSecurityTransportServerState,
  );
  const [dialogOpen, setDialogOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => installSecurityTransport(), []);

  function openCredentialDialog() {
    setDraft("");
    setError(null);
    setDialogOpen(true);
  }

  function closeCredentialDialog() {
    setDraft("");
    setError(null);
    setDialogOpen(false);
  }

  function applyCredential(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setSecurityBearerToken(draft);
      closeCredentialDialog();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Invalid Plasma Bearer token");
    }
  }

  function clearCredential() {
    clearSecurityBearerToken();
    closeCredentialDialog();
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
        onClick={openCredentialDialog}
        aria-label="Configure Plasma Bearer credential"
        title="Bearer credential is memory-only and is never written to browser storage."
      >
        <span aria-hidden="true">●</span>
        {label}
      </button>

      {dialogOpen && (
        <div className="securityCredentialBackdrop" role="presentation" onMouseDown={event => {
          if (event.currentTarget === event.target) closeCredentialDialog();
        }}>
          <form className="securityCredentialDialog" role="dialog" aria-modal="true" aria-labelledby="security-credential-title" onSubmit={applyCredential}>
            <div>
              <p>REMOTE WRITE SECURITY</p>
              <h2 id="security-credential-title">Plasma Bearer Credential</h2>
              <small>Credential stays only in browser memory and is cleared by a full reload.</small>
            </div>
            <label>
              Bearer token
              <input
                autoFocus
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={draft}
                onChange={event => setDraft(event.target.value)}
                placeholder="Paste token"
                aria-invalid={Boolean(error) || undefined}
              />
            </label>
            {error && <div className="securityCredentialError" role="alert">{error}</div>}
            <div className="securityCredentialActions">
              {state.credentialLoaded && <button type="button" className="danger" onClick={clearCredential}>Clear credential</button>}
              <span />
              <button type="button" onClick={closeCredentialDialog}>Cancel</button>
              <button type="submit" className="primary" disabled={!draft.trim()}>Apply</button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
