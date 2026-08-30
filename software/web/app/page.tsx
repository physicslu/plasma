"use client";

import SiteMatrixHome from "./site-matrix-home";
import { useWorkspaceSession } from "./workspace-session";
import "./site-matrix-routing.css";

export default function Home() {
  const { hydrated, apiBase, apiMode, managedPpuAlias } = useWorkspaceSession();
  const routingMode = hydrated ? apiMode : "managed";
  const routingKey = hydrated ? `${apiMode}|${apiBase}` : "routing-unresolved";

  return (
    <div
      data-site-matrix-routing-mode={routingMode}
      data-routing-hydrated={hydrated ? "true" : "false"}
      aria-busy={hydrated ? undefined : true}
    >
      {hydrated && apiMode === "managed" && (
        <div className="siteMatrixManagedRouteNotice" role="status">
          Managed routing · Plasma Manager · {managedPpuAlias ?? "selected PPU"}
        </div>
      )}
      <SiteMatrixHome key={routingKey} />
    </div>
  );
}
