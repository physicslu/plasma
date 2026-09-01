import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import DemoLandingPage from "../app/demo/page";
import DevicesPage from "../app/devices/page";
import DocumentsPage from "../app/documents/page";
import EngineeringPage from "../app/engineering/page";
import FleetPage from "../app/fleet/page";
import { GlobalNav } from "../app/global-nav";
import { I18nProvider } from "../app/i18n";
import { WorkspaceSessionProvider } from "../app/workspace-session";
import { replaceRoute, usePathname } from "./next-navigation";
import "../app/globals.css";
import "../app/details.css";
import "../app/global-nav.css";

function RetiredFleetProgrammingRoute() {
  useEffect(() => {
    replaceRoute("/fleet");
  }, []);
  return <FleetPage />;
}

function RetiredPpuConsoleRoute() {
  useEffect(() => {
    replaceRoute("/engineering");
  }, []);
  return <EngineeringPage />;
}

function CurrentPage() {
  const pathname = usePathname();
  if (pathname === "/devices" || pathname.startsWith("/devices/")) return <DevicesPage />;
  if (pathname === "/documents" || pathname.startsWith("/documents/")) return <DocumentsPage />;
  if (pathname === "/fleet/programming") return <RetiredFleetProgrammingRoute />;
  if (pathname === "/fleet" || pathname.startsWith("/fleet/")) return <FleetPage />;
  if (pathname === "/engineering" || pathname.startsWith("/engineering/")) {
    return <EngineeringPage />;
  }
  if (pathname === "/ppu") return <RetiredPpuConsoleRoute />;
  return <DemoLandingPage />;
}

const container = document.getElementById("root");
if (container === null) throw new Error("Plasma render root is missing");

createRoot(container).render(
  <StrictMode>
    <I18nProvider>
      <WorkspaceSessionProvider>
        <GlobalNav />
        <CurrentPage />
      </WorkspaceSessionProvider>
    </I18nProvider>
  </StrictMode>,
);
