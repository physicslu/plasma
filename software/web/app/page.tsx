"use client";

import { useEffect, useState } from "react";
import SiteMatrixHome from "./site-matrix-home";
import { useWorkspaceSession } from "./workspace-session";
import "./site-matrix-routing.css";

export default function Home() {
  const { hydrated, apiBase, apiMode, managedPpuAlias } = useWorkspaceSession();
  const routingKey = hydrated ? `${apiMode}|${apiBase}` : "";
  const [syncedRoutingKey, setSyncedRoutingKey] = useState("");

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem("plasma-api-base", apiBase);
      window.localStorage.setItem("plasma-api-mode", apiMode);
    } catch {
      // Storage is optional; WorkspaceSession remains authoritative.
    }
    setSyncedRoutingKey(routingKey);
  }, [apiBase, apiMode, hydrated, routingKey]);

  if (!hydrated || syncedRoutingKey !== routingKey) {
    return (
      <main className="siteMatrixRoutingBootstrap" aria-busy="true">
        Resolving Control Station routing…
      </main>
    );
  }

  return (
    <div data-site-matrix-routing-mode={apiMode}>
      {apiMode === "managed" && (
        <div className="siteMatrixManagedRouteNotice" role="status">
          Managed routing · Plasma Manager · {managedPpuAlias ?? "selected PPU"}
        </div>
      )}
      <SiteMatrixHome key={routingKey} />
    </div>
  );
}
