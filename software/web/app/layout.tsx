import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import "./details.css";
import "./global-nav.css";
import "./security-transport.css";
import { GlobalNav } from "./global-nav";
import { I18nProvider } from "./i18n";
import { SecurityTransportProvider } from "./security-transport-provider";
import { WorkspaceSessionProvider } from "./workspace-session";

const sans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-mono", subsets: ["latin"] });
const apiBaseStorageMigration = `
(() => {
  try {
    const versionKey = "plasma-api-base-version";
    const migrationComplete = window.localStorage.getItem(versionKey) === "3";
    const apiKey = "plasma-api-base";
    if (!migrationComplete) {
      // Schema v3 retires Browser-owned direct Gateway endpoints. Clear any
      // previously stored absolute endpoint and let runtime routing resolve to
      // same-origin standalone or Manager-owned managed transport.
      window.localStorage.removeItem(apiKey);
      window.localStorage.setItem(versionKey, "3");
    }
  } catch {
    // Storage is optional; runtime routing remains authoritative.
  }
})();
`;

export const metadata: Metadata = {
  title: "Plasma Control Station",
  description: "Multi-site IC programming Control Station",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant">
      <head>
        <script dangerouslySetInnerHTML={{ __html: apiBaseStorageMigration }} />
      </head>
      <body className={`${sans.variable} ${mono.variable}`}>
        <I18nProvider>
          <WorkspaceSessionProvider>
            <SecurityTransportProvider>
              <GlobalNav />
              {children}
            </SecurityTransportProvider>
          </WorkspaceSessionProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
