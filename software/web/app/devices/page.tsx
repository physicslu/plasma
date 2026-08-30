"use client";

import { useWorkspaceSession } from "../workspace-session";
import { ICSelector } from "./ic-selector";

export default function DevicesPage() {
  const { hydrated, apiBase } = useWorkspaceSession();

  if (!hydrated) {
    return <main className="devicesPage" aria-busy="true">Resolving Control Station routing…</main>;
  }

  return (
    <main className="devicesPage">
      <ICSelector usage="lookup" apiBase={apiBase} />
    </main>
  );
}
