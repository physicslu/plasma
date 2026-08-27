import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import "./details.css";
import "./global-nav.css";
import "./operator-ui/programming-job-controls.css";
import "./security-transport.css";
import { DEFAULT_API_BASE } from "./plasma-api";
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
    const migrationComplete = window.localStorage.getItem(versionKey) === "2";
    const apiKey = "plasma-api-base";
    const defaultApiBase = new URL(${JSON.stringify(DEFAULT_API_BASE)}).toString().replace(/\\/$/, "");
    const savedApi = window.localStorage.getItem(apiKey);
    if (savedApi) {
      try {
        const normalized = new URL(savedApi).toString().replace(/\\/$/, "");
        const legacyApiBases = new Set([
          "https://swpc.tail820e64.ts.net",
          "https://swpc.tail820e64.ts.net:8443",
          "http://127.0.0.1:8080",
        ]);
        if (normalized === defaultApiBase || (!migrationComplete && legacyApiBases.has(normalized))) {
          window.localStorage.removeItem(apiKey);
        }
      } catch {
        window.localStorage.removeItem(apiKey);
      }
    }

    if (!migrationComplete) {
      window.localStorage.setItem(versionKey, "2");
    }
  } catch {
    // Storage may be unavailable; the normal DEFAULT_API_BASE path still works.
  }
})();
`;

export const metadata: Metadata = {
  title: "Plasma PPU Console",
  description: "Multi-site IC programming unit control console",
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
