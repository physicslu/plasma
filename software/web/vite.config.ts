import vinext from "vinext";
import { defineConfig } from "vite";
import hostingConfig from "./.openai/hosting.json";
import { sites } from "./build/sites-vite-plugin";

const SITE_CREATOR_PLACEHOLDER_DATABASE_ID =
  "00000000-0000-4000-8000-000000000000";

const { d1, r2 } = hostingConfig;

// macOS Seatbelt blocks FSEvents, so Codex previews need polling for HMR.
const isCodexSeatbeltSandbox = process.env.CODEX_SANDBOX === "seatbelt";

// The Cloudflare/Vinext application executes server routes inside a Worker
// runtime. Host process environment variables are not Worker bindings by
// themselves, so explicitly bridge the approved Fleet and Manager BFF runtime
// settings into Worker text bindings. The routes keep their own loopback-only
// validation and alias-based routing boundaries.
const fleetWorkerVars = {
  PLASMA_FLEET_UI_ENABLED: process.env.PLASMA_FLEET_UI_ENABLED ?? "0",
  PLASMA_MANAGER_API_URL:
    process.env.PLASMA_MANAGER_API_URL ?? "http://127.0.0.1:18180",
  PLASMA_MANAGER_PPU_ALIAS: process.env.PLASMA_MANAGER_PPU_ALIAS ?? "",
};

const localBindingConfig = {
  main: "./worker/index.ts",
  compatibility_flags: [
    "nodejs_compat",
    "nodejs_compat_populate_process_env",
  ],
  vars: fleetWorkerVars,
  d1_databases: d1
    ? [
        {
          binding: d1,
          database_name: "site-creator-d1",
          database_id: SITE_CREATOR_PLACEHOLDER_DATABASE_ID,
        },
      ]
    : [],
  r2_buckets: r2
    ? [
        {
          binding: r2,
          bucket_name: "site-creator-r2",
        },
      ]
    : [],
};

export default defineConfig(async () => {
  // Keep Wrangler and Miniflare state project-local. These are non-secret tool
  // settings; application environment belongs in ignored `.env*` files.
  process.env.WRANGLER_WRITE_LOGS ??= "false";
  process.env.WRANGLER_LOG_PATH ??= ".wrangler/logs";
  process.env.MINIFLARE_REGISTRY_PATH ??= ".wrangler/registry";

  // Wrangler snapshots its log path while the Cloudflare plugin is imported.
  const { cloudflare } = await import("@cloudflare/vite-plugin");

  return {
    server: {
      host: "0.0.0.0",
      allowedHosts: [
        "terminal.local",
        "swpc.tail820e64.ts.net",
        "plasma.open4th.com",
      ],
      proxy: {
        // PPU-local API calls still go to the Python Gateway. Fleet and Manager
        // namespaces are deliberately excluded so Vinext owns both same-origin
        // BFF surfaces instead of leaking control-plane requests into the PPU
        // execution API surface.
        "^/api/(?!fleet(?:/|$))(?!manager(?:/|$))": {
          target: "http://127.0.0.1:18080",
          changeOrigin: true,
        },
      },
      ...(isCodexSeatbeltSandbox
        ? { watch: { useFsEvents: false, usePolling: true } }
        : {}),
    },
    plugins: [
      vinext(),
      sites(),
      cloudflare({
        viteEnvironment: { name: "rsc", childEnvironments: ["ssr"] },
        inspectorPort: false,
        config: localBindingConfig,
      }),
    ],
  };
});
