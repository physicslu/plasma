"use client";

import { createContext, useContext } from "react";

export type PPUConsoleTarget = {
  apiBase: string;
  lockConnection?: boolean;
  label?: string;
};

const PPUConsoleTargetContext = createContext<PPUConsoleTarget | null>(null);

export function PPUConsoleTargetProvider({
  target,
  children,
}: {
  target: PPUConsoleTarget;
  children: React.ReactNode;
}) {
  return (
    <PPUConsoleTargetContext.Provider value={target}>
      {children}
    </PPUConsoleTargetContext.Provider>
  );
}

export function usePPUConsoleTarget(): PPUConsoleTarget | null {
  return useContext(PPUConsoleTargetContext);
}
