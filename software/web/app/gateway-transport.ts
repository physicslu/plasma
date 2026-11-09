/**
 * Browser Gateway routing transport.
 *
 * Gateway REST paths issued by the Console are held until the workspace has
 * resolved its routing (standalone Gateway origin or Manager-managed
 * `/api/manager/ppu/...` prefix) and are then rebased onto that route. A
 * state-changing request issued before routing is resolved is refused rather
 * than sent to an unknown target.
 *
 * This module carries no credential. PPU write authority is the enrolled
 * controller credential held by the Manager (LOM-P2A-2 G13); the retired
 * browser Bearer transport and the opt-in Bearer-principal Gateway are gone.
 */
type GatewayRoutingMode = "managed" | "standalone";

const MANAGED_PPU_PREFIX = "/api/manager/ppu";
let gatewayRoutingResolved = false;
let gatewayRoutingMode: GatewayRoutingMode = "standalone";
let resolvedGatewayApiBase: string | null = null;
let releaseGatewayRouting!: () => void;
const gatewayRoutingReady = new Promise<void>(resolve => { releaseGatewayRouting = resolve; });
let uninstallTransport: (() => void) | null = null;

const gatewayPathPrefixes = [
  "/api/status",
  "/api/jobs",
  "/api/batches",
  "/api/settings/gateway",
  "/api/mock/runtime",
  "/api/engineering",
  "/api/health",
  "/api/node",
];

export function markGatewayRoutingResolved(apiBase: string, mode: GatewayRoutingMode): void {
  const trimmed = apiBase.trim();
  const normalized = trimmed
    ? new URL(trimmed, window.location.href).toString().replace(/\/$/, "")
    : window.location.origin;
  resolvedGatewayApiBase = normalized;
  gatewayRoutingMode = mode;
  if (gatewayRoutingResolved) return;
  gatewayRoutingResolved = true;
  releaseGatewayRouting();
}

function directGatewayPath(pathname: string): boolean {
  return gatewayPathPrefixes.some(prefix => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

function directGatewayPathname(pathname: string): string | null {
  if (directGatewayPath(pathname)) return pathname;
  if (pathname.startsWith(`${MANAGED_PPU_PREFIX}/`)) {
    const directPath = pathname.slice(MANAGED_PPU_PREFIX.length);
    if (directGatewayPath(directPath)) return directPath;
  }
  return null;
}

function routingUnresolvedResponse(): Response {
  return Response.json(
    {
      ok: false,
      error: {
        error_code: "routing_unresolved",
        message: "Gateway routing is not resolved yet",
      },
    },
    {
      status: 503,
      headers: {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    },
  );
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method) return init.method.toUpperCase();
  if (typeof Request !== "undefined" && input instanceof Request) return input.method.toUpperCase();
  return "GET";
}

function isStateChanging(method: string): boolean {
  return !["GET", "HEAD", "OPTIONS"].includes(method);
}

function rebaseInput(
  input: RequestInfo | URL,
  directPath: string,
  search: string,
): RequestInfo | URL {
  if (!resolvedGatewayApiBase) return input;
  const rebasedUrl = `${resolvedGatewayApiBase}${directPath}${search}`;
  return typeof Request !== "undefined" && input instanceof Request
    ? new Request(rebasedUrl, input)
    : rebasedUrl;
}

export function installGatewayTransport(): () => void {
  if (typeof window === "undefined") return () => {};
  if (uninstallTransport) return uninstallTransport;

  const originalFetch = window.fetch.bind(window);
  const wrappedFetch: typeof window.fetch = async (input, init) => {
    let currentInput: RequestInfo | URL = input;
    const rawUrl = typeof Request !== "undefined" && currentInput instanceof Request ? currentInput.url : String(currentInput);
    const url = new URL(rawUrl, window.location.href);
    const directPath = directGatewayPathname(url.pathname);
    if (directPath === null) return await originalFetch(currentInput, init);

    if (!gatewayRoutingResolved) {
      if (isStateChanging(requestMethod(currentInput, init))) return routingUnresolvedResponse();
      await gatewayRoutingReady;
      if (!resolvedGatewayApiBase) return routingUnresolvedResponse();
      currentInput = rebaseInput(currentInput, directPath, url.search);
    } else if (gatewayRoutingMode === "managed" && resolvedGatewayApiBase) {
      currentInput = rebaseInput(currentInput, directPath, url.search);
    }
    return await originalFetch(currentInput, init);
  };

  window.fetch = wrappedFetch;
  uninstallTransport = () => {
    if (window.fetch === wrappedFetch) window.fetch = originalFetch;
    uninstallTransport = null;
  };
  return uninstallTransport;
}

// Imported by the root client provider: install before child effects issue
// the first Gateway request during hydration.
if (typeof window !== "undefined") installGatewayTransport();
