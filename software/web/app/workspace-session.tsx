"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import {
  beginEngineeringSession,
  DEFAULT_API_BASE,
  normalizeApiBase,
  type Operation,
} from "./plasma-api";
import {
  getSecurityTransportServerState,
  getSecurityTransportState,
  subscribeSecurityTransport,
} from "./security-transport";

export type SelectionMap = Record<string, Record<string, number[]>>;
export type ProductionSet = SelectionMap;
export type BatchSelection = SelectionMap;
export type TargetSelection = { facilityId: string; ppuId: string };
export type EngineeringSection =
  | "overview"
  | "ppu-sites"
  | "programming"
  | "diagnostics"
  | "logs"
  | "tools"
  | "settings";
export type WorkspaceSessionAuditEntry = {
  id: number;
  time: string;
  message: string;
};

type SessionState = { apiBase: string; sessionId: string; credentialRevision: number };
type SessionRequest = { apiBase: string; credentialRevision: number; promise: Promise<string> };
type ApiMode = "managed" | "standalone";
type ManagedRoutingDiscovery = { managed: boolean; alias: string | null } | null;

type WorkspaceSessionContextValue = {
  hydrated: boolean;
  apiBase: string;
  apiMode: ApiMode;
  managedPpuAlias: string | null;
  setApiBase: (value: string) => string;
  engineeringSessionId: string | null;
  ensureEngineeringSession: (apiBase?: string) => Promise<string>;
  restartEngineeringSession: (apiBase?: string) => Promise<string>;
  sessionAuditEntries: WorkspaceSessionAuditEntry[];
  clearSessionAuditEntries: () => void;

  programmingImage: File | null;
  setProgrammingImage: Dispatch<SetStateAction<File | null>>;

  pmodDraftSelection: SelectionMap;
  setPmodDraftSelection: Dispatch<SetStateAction<SelectionMap>>;
  pmodProductionSet: ProductionSet;
  setPmodProductionSet: Dispatch<SetStateAction<ProductionSet>>;
  pmodBatchSelection: BatchSelection;
  setPmodBatchSelection: Dispatch<SetStateAction<BatchSelection>>;
  pmodOperations: Operation[];
  setPmodOperations: Dispatch<SetStateAction<Operation[]>>;
  pmodSelectorCollapsed: boolean;
  setPmodSelectorCollapsed: Dispatch<SetStateAction<boolean>>;

  emodeSection: EngineeringSection;
  setEmodeSection: Dispatch<SetStateAction<EngineeringSection>>;
  emodeSelection: TargetSelection;
  setEmodeSelection: Dispatch<SetStateAction<TargetSelection>>;
  emodeSiteIds: number[] | null;
  setEmodeSiteIds: Dispatch<SetStateAction<number[] | null>>;
  emodeOperations: Operation[];
  setEmodeOperations: Dispatch<SetStateAction<Operation[]>>;
};

const WorkspaceSessionContext = createContext<WorkspaceSessionContextValue | null>(null);
const API_STORAGE_KEY = "plasma-api-base";
const API_MODE_STORAGE_KEY = "plasma-api-mode";

function nowTime(): string {
  return new Date().toLocaleTimeString("en-GB", { hour12: false });
}

function managedApiBase(): string {
  return `${window.location.origin}/api/manager/ppu`;
}

async function discoverManagedRouting(): Promise<ManagedRoutingDiscovery> {
  try {
    const response = await fetch("/api/manager/ppu", {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const payload: unknown = await response.json();
    if (!payload || typeof payload !== "object") return null;
    const record = payload as Record<string, unknown>;
    const managed = record.managed === true;
    const alias = typeof record.ppu_alias === "string" && record.ppu_alias.trim()
      ? record.ppu_alias.trim()
      : null;
    if (response.ok && (record.ok !== true || !managed || !alias)) return null;
    return { managed, alias };
  } catch {
    return null;
  }
}

export function WorkspaceSessionProvider({ children }: { children: ReactNode }) {
  const securityTransport = useSyncExternalStore(
    subscribeSecurityTransport,
    getSecurityTransportState,
    getSecurityTransportServerState,
  );
  const [hydrated, setHydrated] = useState(false);
  const [apiBase, setApiBaseState] = useState(DEFAULT_API_BASE);
  const [apiMode, setApiMode] = useState<ApiMode>("standalone");
  const [managedPpuAlias, setManagedPpuAlias] = useState<string | null>(null);
  const [sessionState, setSessionState] = useState<SessionState | null>(null);
  const [sessionAuditEntries, setSessionAuditEntries] = useState<WorkspaceSessionAuditEntry[]>([]);
  const sessionStateRef = useRef<SessionState | null>(null);
  const sessionRequestRef = useRef<SessionRequest | null>(null);
  const sessionAuditSequence = useRef(0);

  const [programmingImage, setProgrammingImage] = useState<File | null>(null);

  // Production deliberately keeps the three responsibility domains separate:
  // draft = transient tree edit state, Production Set = committed equipment scope,
  // Batch Selection = operator intent. Server Batch Runtime remains server-owned.
  const [pmodDraftSelection, setPmodDraftSelection] = useState<SelectionMap>({});
  const [pmodProductionSet, setPmodProductionSet] = useState<ProductionSet>({});
  const [pmodBatchSelection, setPmodBatchSelection] = useState<BatchSelection>({});
  const [pmodOperations, setPmodOperations] = useState<Operation[]>([]);
  const [pmodSelectorCollapsed, setPmodSelectorCollapsed] = useState(false);

  const [emodeSection, setEmodeSection] = useState<EngineeringSection>("overview");
  const [emodeSelection, setEmodeSelection] = useState<TargetSelection>({ facilityId: "", ppuId: "" });
  const [emodeSiteIds, setEmodeSiteIds] = useState<number[] | null>(null);
  const [emodeOperations, setEmodeOperations] = useState<Operation[]>([]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      let saved = DEFAULT_API_BASE;
      let storedMode: ApiMode | null = null;
      let stored: string | null = null;
      try {
        const rawMode = window.localStorage.getItem(API_MODE_STORAGE_KEY);
        if (rawMode === "managed" || rawMode === "standalone") storedMode = rawMode;
        stored = window.localStorage.getItem(API_STORAGE_KEY);
      } catch {
        // Storage is optional. Runtime discovery remains authoritative.
      }

      const discovery = await discoverManagedRouting();
      let nextMode: ApiMode = "standalone";
      let nextManagedPpuAlias: string | null = null;

      if (discovery?.managed === true) {
        saved = managedApiBase();
        nextMode = "managed";
        nextManagedPpuAlias = discovery.alias;
      } else if (discovery === null && storedMode === "managed") {
        // A previously managed Control Station remains fail-closed when the
        // same-origin BFF discovery request is temporarily unavailable.
        saved = managedApiBase();
        nextMode = "managed";
      } else {
        try {
          if (stored && storedMode !== "managed") saved = normalizeApiBase(stored);
        } catch {
          saved = DEFAULT_API_BASE;
        }
      }

      if (nextMode === "managed") {
        try {
          window.localStorage.setItem(API_MODE_STORAGE_KEY, nextMode);
          window.localStorage.setItem(API_STORAGE_KEY, saved);
        } catch {
          // Storage is optional.
        }
      }

      if (!cancelled) {
        setApiBaseState(saved);
        setApiMode(nextMode);
        setManagedPpuAlias(nextManagedPpuAlias);
        setHydrated(true);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const setApiBase = useCallback((value: string): string => {
    const normalized = normalizeApiBase(value);
    const managedBase = managedApiBase();
    if (apiMode === "managed" && normalized !== managedBase) {
      throw new Error("Managed Control Station routing is locked to the selected Manager PPU");
    }
    const mode: ApiMode = normalized === managedBase ? "managed" : "standalone";
    setApiBaseState(normalized);
    setApiMode(mode);
    if (mode === "standalone") setManagedPpuAlias(null);
    try {
      window.localStorage.setItem(API_STORAGE_KEY, normalized);
      window.localStorage.setItem(API_MODE_STORAGE_KEY, mode);
    } catch { /* storage is optional */ }
    return normalized;
  }, [apiMode]);

  const appendSessionAudit = useCallback((message: string) => {
    setSessionAuditEntries(current => [...current, {
      id: ++sessionAuditSequence.current,
      time: nowTime(),
      message,
    }].slice(-100));
  }, []);

  const clearSessionAuditEntries = useCallback(() => {
    setSessionAuditEntries([]);
  }, []);

  const publishSession = useCallback((next: SessionState) => {
    sessionStateRef.current = next;
    setSessionState(next);
    return next.sessionId;
  }, []);

  const ensureEngineeringSession = useCallback(async (requestedBase?: string): Promise<string> => {
    const normalized = normalizeApiBase(requestedBase ?? apiBase);
    const credentialRevision = securityTransport.credentialRevision;
    const current = sessionStateRef.current;
    if (current?.apiBase === normalized && current.credentialRevision === credentialRevision) {
      return current.sessionId;
    }
    const pending = sessionRequestRef.current;
    if (pending?.apiBase === normalized && pending.credentialRevision === credentialRevision) {
      return await pending.promise;
    }

    const promise = beginEngineeringSession(normalized).then(session => {
      if (getSecurityTransportState().credentialRevision !== credentialRevision) {
        throw new Error("Engineering credential changed while the session was starting");
      }
      const sessionId = publishSession({
        apiBase: normalized,
        sessionId: session.session_id,
        credentialRevision,
      });
      appendSessionAudit(`[SESSION] NEW · fresh connection · ${sessionId.slice(0, 8)}…`);
      return sessionId;
    });
    sessionRequestRef.current = { apiBase: normalized, credentialRevision, promise };
    try {
      return await promise;
    } finally {
      if (sessionRequestRef.current?.promise === promise) sessionRequestRef.current = null;
    }
  }, [apiBase, appendSessionAudit, publishSession, securityTransport.credentialRevision]);

  const restartEngineeringSession = useCallback(async (requestedBase?: string): Promise<string> => {
    const normalized = normalizeApiBase(requestedBase ?? apiBase);
    const credentialRevision = securityTransport.credentialRevision;
    const current = sessionStateRef.current;
    const previousSessionId = current?.apiBase === normalized && current.credentialRevision === credentialRevision
      ? current.sessionId
      : undefined;
    const session = await beginEngineeringSession(normalized, previousSessionId);
    if (getSecurityTransportState().credentialRevision !== credentialRevision) {
      throw new Error("Engineering credential changed while the session was restarting");
    }
    const sessionId = publishSession({
      apiBase: normalized,
      sessionId: session.session_id,
      credentialRevision,
    });
    appendSessionAudit(
      `[SESSION] NEW · ${session.previous_session_cleared ? "previous Programming Asset cache cleared" : "fresh connection"} · ${sessionId.slice(0, 8)}…`,
    );
    return sessionId;
  }, [apiBase, appendSessionAudit, publishSession, securityTransport.credentialRevision]);

  const engineeringSessionId = sessionState?.apiBase === apiBase
    && sessionState.credentialRevision === securityTransport.credentialRevision
    ? sessionState.sessionId
    : null;

  const value = useMemo<WorkspaceSessionContextValue>(() => ({
    hydrated,
    apiBase,
    apiMode,
    managedPpuAlias,
    setApiBase,
    engineeringSessionId,
    ensureEngineeringSession,
    restartEngineeringSession,
    sessionAuditEntries,
    clearSessionAuditEntries,
    programmingImage,
    setProgrammingImage,
    pmodDraftSelection,
    setPmodDraftSelection,
    pmodProductionSet,
    setPmodProductionSet,
    pmodBatchSelection,
    setPmodBatchSelection,
    pmodOperations,
    setPmodOperations,
    pmodSelectorCollapsed,
    setPmodSelectorCollapsed,
    emodeSection,
    setEmodeSection,
    emodeSelection,
    setEmodeSelection,
    emodeSiteIds,
    setEmodeSiteIds,
    emodeOperations,
    setEmodeOperations,
  }), [
    hydrated,
    apiBase,
    apiMode,
    managedPpuAlias,
    setApiBase,
    engineeringSessionId,
    ensureEngineeringSession,
    restartEngineeringSession,
    sessionAuditEntries,
    clearSessionAuditEntries,
    programmingImage,
    pmodDraftSelection,
    pmodProductionSet,
    pmodBatchSelection,
    pmodOperations,
    pmodSelectorCollapsed,
    emodeSection,
    emodeSelection,
    emodeSiteIds,
    emodeOperations,
  ]);

  return <WorkspaceSessionContext.Provider value={value}>{children}</WorkspaceSessionContext.Provider>;
}

export function useWorkspaceSession(): WorkspaceSessionContextValue {
  const context = useContext(WorkspaceSessionContext);
  if (!context) throw new Error("useWorkspaceSession must be used inside WorkspaceSessionProvider");
  return context;
}
