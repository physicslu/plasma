import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import DemoLandingPage from "../app/demo/page";
import EngineeringPage from "../app/engineering/page";
import FleetPage from "../app/fleet/page";
import { GlobalNav } from "../app/global-nav";
import { I18nProvider } from "../app/i18n";
import PPUConsole from "../app/page";
import { WorkspaceSessionProvider } from "../app/workspace-session";
import { usePathname } from "./next-navigation";
import "../app/globals.css";
import "../app/details.css";
import "../app/global-nav.css";

function CurrentPage() {
  const pathname = usePathname();
  if (pathname === "/fleet" || pathname.startsWith("/fleet/")) return <FleetPage />;
  if (pathname === "/engineering" || pathname.startsWith("/engineering/")) {
    return <EngineeringPage />;
  }
  if (pathname === "/ppu") return <PPUConsole />;
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
