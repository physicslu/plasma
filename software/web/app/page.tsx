"use client";

import SiteMatrixHome from "./site-matrix-home";
import { useWorkspaceSession } from "./workspace-session";
import "./site-matrix-routing.css";

export default function Home() {
  const { hydrated, apiBase, apiMode, managedPpuAlias } = useWorkspaceSession();

  if (!hydrated) {
    return (
      <main className="siteMatrixRoutingBootstrap" aria-busy="true">
        Resolving Control Station routing…
      </main>
    );
  }

  const routingKey = `${apiMode}|${apiBase}`;
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
