import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import "./details.css";

const sans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-mono", subsets: ["latin"] });
const apiBaseStorageMigration = `
(() => {
  try {
    const versionKey = "plasma-api-base-version";
    if (window.localStorage.getItem(versionKey) === "2") return;

    const apiKey = "plasma-api-base";
    const savedApi = window.localStorage.getItem(apiKey);
    if (savedApi) {
      try {
        const normalized = new URL(savedApi).toString().replace(/\\/$/, "");
        const legacyApiBases = new Set([
          "https://swpc.tail820e64.ts.net",
          "https://swpc.tail820e64.ts.net:8443",
          "http://127.0.0.1:8080",
        ]);
        if (legacyApiBases.has(normalized)) {
          window.localStorage.removeItem(apiKey);
        }
      } catch {
        window.localStorage.removeItem(apiKey);
      }
    }

    window.localStorage.setItem(versionKey, "2");
  } catch {
    // Storage may be unavailable; the normal DEFAULT_API_BASE path still works.
  }
})();
`;

export const metadata: Metadata = {
  title: "Plasma Programmer Console",
  description: "Multi-channel IC programmer control console",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant">
      <head>
        <script dangerouslySetInnerHTML={{ __html: apiBaseStorageMigration }} />
      </head>
      <body className={`${sans.variable} ${mono.variable}`}>{children}</body>
    </html>
  );
}
