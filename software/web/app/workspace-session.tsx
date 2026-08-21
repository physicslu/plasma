"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
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

export type SelectionMap = Record<string, Record<string, number[]>>;
export type TargetSelection = { facilityId: string; ppuId: string };
export type EngineeringSection =
  | "overview"
  | "ppu-sites"
  | "programming"
  | "diagnostics"
  | "logs"
  | "tools"
  | "settings";

type SessionState = { apiBase: string; sessionId: string };
type SessionRequest = { apiBase: string; promise: Promise<string> };

type WorkspaceSessionContextValue = {
  hydrated: boolean;
  apiBase: string;
  setApiBase: (value: string) => string;
  engineeringSessionId: string | null;
  ensureEngineeringSession: (apiBase?: string) => Promise<string>;
  restartEngineeringSession: (apiBase?: string) => Promise<string>;

  programmingImage: File | null;
  setProgrammingImage: Dispatch<SetStateAction<File | null>>;

  pmodDraftSelection: SelectionMap;
  setPmodDraftSelection: Dispatch<SetStateAction<SelectionMap>>;
  pmodActiveSelection: SelectionMap;
  setPmodActiveSelection: Dispatch<SetStateAction<SelectionMap>>;
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
  emodeReadOffset: string;
  setEmodeReadOffset: Dispatch<SetStateAction<string>>;
  emodeReadLength: string;
  setEmodeReadLength: Dispatch<SetStateAction<string>>;
};

const WorkspaceSessionContext = createContext<WorkspaceSessionContextValue | null>(null);
const API_STORAGE_KEY = "plasma-api-base";

export function WorkspaceSessionProvider({ children }: { children: ReactNode }) {
  const [hydrated, setHydrated] = useState(false);
  const [apiBase, setApiBaseState] = useState(DEFAULT_API_BASE);
  const [sessionState, setSessionState] = useState<SessionState | null>(null);
  const sessionStateRef = useRef<SessionState | null>(null);
  const sessionRequestRef = useRef<SessionRequest | null>(null);

  const [programmingImage, setProgrammingImage] = useState<File | null>(null);

  const [pmodDraftSelection, setPmodDraftSelection] = useState<SelectionMap>({});
  const [pmodActiveSelection, setPmodActiveSelection] = useState<SelectionMap>({});
  const [pmodOperations, setPmodOperations] = useState<Operation[]>([]);
  const [pmodSelectorCollapsed, setPmodSelectorCollapsed] = useState(false);

  const [emodeSection, setEmodeSection] = useState<EngineeringSection>("overview");
  const [emodeSelection, setEmodeSelection] = useState<TargetSelection>({ facilityId: "", ppuId: "" });
  const [emodeSiteIds, setEmodeSiteIds] = useState<number[] | null>(null);
  const [emodeOperations, setEmodeOperations] = useState<Operation[]>([]);
  const [emodeReadOffset, setEmodeReadOffset] = useState("0");
  const [emodeReadLength, setEmodeReadLength] = useState("256");

  useEffect(() => {
    let saved = DEFAULT_API_BASE;
    try {
      const stored = window.localStorage.getItem(API_STORAGE_KEY);
      if (stored) saved = normalizeApiBase(stored);
    } catch {
      // Storage is optional. The compiled default remains valid.
    }
    queueMicrotask(() => {
      setApiBaseState(saved);
      setHydrated(true);
    });
  }, []);

  const setApiBase = useCallback((value: string): string => {
    const normalized = normalizeApiBase(value);
    setApiBaseState(normalized);
    try { window.localStorage.setItem(API_STORAGE_KEY, normalized); } catch { /* storage is optional */ }
    return normalized;
  }, []);

  const publishSession = useCallback((next: SessionState) => {
    sessionStateRef.current = next;
    setSessionState(next);
    return next.sessionId;
  }, []);

  const ensureEngineeringSession = useCallback(async (requestedBase?: string): Promise<string> => {
    const normalized = normalizeApiBase(requestedBase ?? apiBase);
    const current = sessionStateRef.current;
    if (current?.apiBase === normalized) return current.sessionId;
    const pending = sessionRequestRef.current;
    if (pending?.apiBase === normalized) return await pending.promise;

    const promise = beginEngineeringSession(normalized).then(session => publishSession({
      apiBase: normalized,
      sessionId: session.session_id,
    }));
    sessionRequestRef.current = { apiBase: normalized, promise };
    try {
      return await promise;
    } finally {
      if (sessionRequestRef.current?.promise === promise) sessionRequestRef.current = null;
    }
  }, [apiBase, publishSession]);

  const restartEngineeringSession = useCallback(async (requestedBase?: string): Promise<string> => {
    const normalized = normalizeApiBase(requestedBase ?? apiBase);
    const current = sessionStateRef.current;
    const previousSessionId = current?.apiBase === normalized ? current.sessionId : undefined;
    const session = await beginEngineeringSession(normalized, previousSessionId);
    return publishSession({ apiBase: normalized, sessionId: session.session_id });
  }, [apiBase, publishSession]);

  const engineeringSessionId = sessionState?.apiBase === apiBase ? sessionState.sessionId : null;

  const value = useMemo<WorkspaceSessionContextValue>(() => ({
    hydrated,
    apiBase,
    setApiBase,
    engineeringSessionId,
    ensureEngineeringSession,
    restartEngineeringSession,
    programmingImage,
    setProgrammingImage,
    pmodDraftSelection,
    setPmodDraftSelection,
    pmodActiveSelection,
    setPmodActiveSelection,
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
    emodeReadOffset,
    setEmodeReadOffset,
    emodeReadLength,
    setEmodeReadLength,
  }), [
    hydrated,
    apiBase,
    setApiBase,
    engineeringSessionId,
    ensureEngineeringSession,
    restartEngineeringSession,
    programmingImage,
    pmodDraftSelection,
    pmodActiveSelection,
    pmodOperations,
    pmodSelectorCollapsed,
    emodeSection,
    emodeSelection,
    emodeSiteIds,
    emodeOperations,
    emodeReadOffset,
    emodeReadLength,
  ]);

  return <WorkspaceSessionContext.Provider value={value}>{children}</WorkspaceSessionContext.Provider>;
}

export function useWorkspaceSession(): WorkspaceSessionContextValue {
  const context = useContext(WorkspaceSessionContext);
  if (!context) throw new Error("useWorkspaceSession must be used inside WorkspaceSessionProvider");
  return context;
}
