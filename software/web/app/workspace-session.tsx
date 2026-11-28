"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import { markGatewayRoutingResolved } from "./gateway-transport";

export type SelectionMap = Record<string, Record<string, number[]>>;
export type ProductionSet = SelectionMap;
export type BatchSelection = SelectionMap;
export type EngineeringSection =
  | "overview"
  | "ppu-sites"
  | "programming"
  | "diagnostics"
  | "logs"
  | "tools"
  | "settings";

type WorkspaceSessionContextValue = {
  hydrated: boolean;
  /** Always the Manager-managed PPU prefix: the Console has no standalone mode (U10). */
  apiBase: string;

  pmodDraftSelection: SelectionMap;
  setPmodDraftSelection: Dispatch<SetStateAction<SelectionMap>>;
  pmodProductionSet: ProductionSet;
  setPmodProductionSet: Dispatch<SetStateAction<ProductionSet>>;
  pmodBatchSelection: BatchSelection;
  setPmodBatchSelection: Dispatch<SetStateAction<BatchSelection>>;
  pmodSelectorCollapsed: boolean;
  setPmodSelectorCollapsed: Dispatch<SetStateAction<boolean>>;

  emodeSection: EngineeringSection;
  setEmodeSection: Dispatch<SetStateAction<EngineeringSection>>;
};

const WorkspaceSessionContext = createContext<WorkspaceSessionContextValue | null>(null);

const subscribeNever = () => () => {};

function managedApiBase(): string {
  return `${window.location.origin}/api/manager/ppu`;
}

export function WorkspaceSessionProvider({ children }: { children: ReactNode }) {
  // "" on the server and during hydration; the managed prefix on the client.
  const hydrated = useSyncExternalStore(subscribeNever, () => true, () => false);
  const apiBase = hydrated ? managedApiBase() : "";

  // Production deliberately keeps the three responsibility domains separate:
  // draft = transient tree edit state, Production Set = committed equipment scope,
  // Batch Selection = operator intent. Every Batch is Manager-owned.
  const [pmodDraftSelection, setPmodDraftSelection] = useState<SelectionMap>({});
  const [pmodProductionSet, setPmodProductionSet] = useState<ProductionSet>({});
  const [pmodBatchSelection, setPmodBatchSelection] = useState<BatchSelection>({});
  const [pmodSelectorCollapsed, setPmodSelectorCollapsed] = useState(false);

  const [emodeSection, setEmodeSection] = useState<EngineeringSection>("overview");

  useEffect(() => {
    // The Console reaches a PPU only through the Plasma Manager (U10): every
    // Gateway path is rebased onto the same-origin managed prefix. There is
    // no Browser-chosen Gateway URL and no direct-Gateway fallback.
    markGatewayRoutingResolved(managedApiBase());
  }, []);

  const value = useMemo<WorkspaceSessionContextValue>(() => ({
    hydrated,
    apiBase,
    pmodDraftSelection,
    setPmodDraftSelection,
    pmodProductionSet,
    setPmodProductionSet,
    pmodBatchSelection,
    setPmodBatchSelection,
    pmodSelectorCollapsed,
    setPmodSelectorCollapsed,
    emodeSection,
    setEmodeSection,
  }), [
    hydrated,
    apiBase,
    pmodDraftSelection,
    pmodProductionSet,
    pmodBatchSelection,
    pmodSelectorCollapsed,
    emodeSection,
  ]);

  return <WorkspaceSessionContext.Provider value={value}>{children}</WorkspaceSessionContext.Provider>;
}

export function useWorkspaceSession(): WorkspaceSessionContextValue {
  const context = useContext(WorkspaceSessionContext);
  if (!context) throw new Error("useWorkspaceSession must be used inside WorkspaceSessionProvider");
  return context;
}
