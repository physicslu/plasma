type SecurityTransportState = {
  credentialLoaded: boolean;
  authenticationRequired: boolean;
  securityDetected: boolean;
  credentialRevision: number;
};

type Listener = () => void;

type SecurityErrorPayload = {
  error?: { error_code?: string };
};

const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_PLASMA_API_URL ?? "https://plasma.open4th.com";
const MANAGED_PPU_PREFIX = "/api/manager/ppu";
const MAX_AMBIGUOUS_COMMANDS = 256;
const listeners = new Set<Listener>();
const ambiguousCommandIds = new Map<string, string>();
const SERVER_SNAPSHOT: SecurityTransportState = {
  credentialLoaded: false,
  authenticationRequired: false,
  securityDetected: false,
  credentialRevision: 0,
};
let bearerToken: string | null = null;
let authenticationRequired = false;
let securityDetected = false;
let credentialRevision = 0;
let gatewayRoutingResolved = false;
let resolvedGatewayApiBase: string | null = null;
let releaseGatewayRouting!: () => void;
const gatewayRoutingReady = new Promise<void>(resolve => { releaseGatewayRouting = resolve; });
let stateSnapshot: SecurityTransportState = SERVER_SNAPSHOT;
let uninstallTransport: (() => void) | null = null;

const gatewayPathPrefixes = [
  "/api/status",
  "/api/jobs",
  "/api/batches",
  "/api/settings/gateway",
  "/api/mock/runtime",
  "/api/engineering",
  "/api/security",
  "/api/devices/search",
  "/api/health",
  "/api/node",
];

function emit(): void {
  stateSnapshot = {
    credentialLoaded: bearerToken !== null,
    authenticationRequired,
    securityDetected,
    credentialRevision,
  };
  listeners.forEach(listener => listener());
}

export function subscribeSecurityTransport(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getSecurityTransportState(): SecurityTransportState {
  return stateSnapshot;
}

export function getSecurityTransportServerState(): SecurityTransportState {
  return SERVER_SNAPSHOT;
}

export function markGatewayRoutingResolved(apiBase: string): void {
  resolvedGatewayApiBase = apiBase;
  if (gatewayRoutingResolved) return;
  gatewayRoutingResolved = true;
  releaseGatewayRouting();
}

export function setSecurityBearerToken(token: string): void {
  const normalized = token.trim();
  if (normalized.length < 32 || normalized.length > 512) {
    throw new Error("Plasma Bearer token must contain 32..512 characters");
  }
  bearerToken = normalized;
  securityDetected = true;
  authenticationRequired = false;
  credentialRevision += 1;
  emit();
}

export function clearSecurityBearerToken(): void {
  bearerToken = null;
  authenticationRequired = securityDetected;
  ambiguousCommandIds.clear();
  credentialRevision += 1;
  emit();
}

function savedGatewayApiBase(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem("plasma-api-base");
  } catch {
    return null;
  }
}

function configuredGatewayOrigins(): Set<string> {
  const origins = new Set<string>();
  for (const candidate of [DEFAULT_API_BASE, savedGatewayApiBase(), resolvedGatewayApiBase]) {
    if (!candidate) continue;
    try {
      origins.add(new URL(candidate).origin);
    } catch {
      // Invalid saved API values are handled by the normal API-base migration.
    }
  }
  if (typeof window !== "undefined") origins.add(window.location.origin);
  return origins;
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

function isGatewayPath(pathname: string): boolean {
  return directGatewayPathname(pathname) !== null;
}

function isGatewayRequest(url: URL): boolean {
  return configuredGatewayOrigins().has(url.origin) && isGatewayPath(url.pathname);
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

function commandIdentity(url: URL, method: string, init?: RequestInit): string {
  const body = typeof init?.body === "string" ? init.body : "";
  return `${method}\n${url.toString()}\n${body}`;
}

function commandIdFor(identity: string): string {
  const existing = ambiguousCommandIds.get(identity);
  if (existing) return existing;
  if (ambiguousCommandIds.size >= MAX_AMBIGUOUS_COMMANDS) {
    const oldest = ambiguousCommandIds.keys().next().value as string | undefined;
    if (oldest) ambiguousCommandIds.delete(oldest);
  }
  const commandId = `browser-${window.crypto.randomUUID()}`;
  ambiguousCommandIds.set(identity, commandId);
  return commandId;
}

function isStateChanging(method: string): boolean {
  return !["GET", "HEAD", "OPTIONS"].includes(method);
}

function mergedHeaders(input: RequestInfo | URL, init?: RequestInit): Headers {
  const headers = new Headers(typeof Request !== "undefined" && input instanceof Request ? input.headers : undefined);
  if (init?.headers) {
    new Headers(init.headers).forEach((value, key) => headers.set(key, value));
  }
  return headers;
}

async function securityErrorCode(response: Response): Promise<string | undefined> {
  if (response.status !== 401 && response.status !== 409) return undefined;
  try {
    const payload = await response.clone().json() as SecurityErrorPayload;
    return payload.error?.error_code;
  } catch {
    return undefined;
  }
}

function responseFilename(response: Response, fallback: string): string {
  const disposition = response.headers.get("Content-Disposition");
  const matched = disposition?.match(/filename="([^"]+)"/i);
  return matched?.[1] ?? fallback;
}

function outputDownloadAnchor(target: EventTarget | null): HTMLAnchorElement | null {
  if (!(target instanceof Element)) return null;
  const anchor = target.closest("a[href]");
  if (!(anchor instanceof HTMLAnchorElement)) return null;
  try {
    const url = new URL(anchor.href, window.location.href);
    if (!isGatewayRequest(url)) return null;
    if (!/^\/api\/(?:manager\/ppu\/api\/)?(?:engineering\/targets\/[^/]+\/[^/]+\/api\/)?jobs\/[^/]+\/files\/[^/]+$/.test(url.pathname)) {
      return null;
    }
    return anchor;
  } catch {
    return null;
  }
}

export function installSecurityTransport(): () => void {
  if (typeof window === "undefined") return () => {};
  if (uninstallTransport) return uninstallTransport;

  const originalFetch = window.fetch.bind(window);
  const wrappedFetch: typeof window.fetch = async (input, init) => {
    let currentInput: RequestInfo | URL = input;
    let rawUrl = typeof Request !== "undefined" && currentInput instanceof Request ? currentInput.url : String(currentInput);
    let url = new URL(rawUrl, window.location.href);
    const unresolvedDirectPath = directGatewayPathname(url.pathname);

    if (!gatewayRoutingResolved && unresolvedDirectPath !== null) {
      const unresolvedMethod = requestMethod(currentInput, init);
      if (isStateChanging(unresolvedMethod)) return routingUnresolvedResponse();
      await gatewayRoutingReady;
      if (!resolvedGatewayApiBase) return routingUnresolvedResponse();
      const rebasedUrl = `${resolvedGatewayApiBase}${unresolvedDirectPath}${url.search}`;
      currentInput = typeof Request !== "undefined" && currentInput instanceof Request
        ? new Request(rebasedUrl, currentInput)
        : rebasedUrl;
      rawUrl = typeof Request !== "undefined" && currentInput instanceof Request ? currentInput.url : String(currentInput);
      url = new URL(rawUrl, window.location.href);
    }

    if (!isGatewayRequest(url)) return await originalFetch(currentInput, init);

    const method = requestMethod(currentInput, init);
    const headers = mergedHeaders(currentInput, init);
    if (securityDetected && bearerToken && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${bearerToken}`);
    }

    let identity: string | null = null;
    if (securityDetected && isStateChanging(method) && !headers.has("Idempotency-Key")) {
      identity = commandIdentity(url, method, init);
      headers.set("Idempotency-Key", commandIdFor(identity));
    }

    const nextInit: RequestInit = { ...init, headers };
    const request = typeof Request !== "undefined" && currentInput instanceof Request
      ? new Request(currentInput, nextInit)
      : currentInput;

    try {
      const response = await originalFetch(request, request === currentInput ? nextInit : undefined);
      const errorCode = await securityErrorCode(response);
      if (response.status === 401 && errorCode === "E4101") {
        const changed = !securityDetected || !authenticationRequired;
        securityDetected = true;
        authenticationRequired = true;
        if (changed) emit();
      } else if (securityDetected && bearerToken && authenticationRequired) {
        authenticationRequired = false;
        emit();
      }
      if (identity && errorCode !== "E4104") {
        ambiguousCommandIds.delete(identity);
      }
      return response;
    } catch (error) {
      // Keep the same command identity after an ambiguous transport failure.
      // A retry of the same request will reuse Idempotency-Key and cannot
      // accidentally issue a second physical command.
      throw error;
    }
  };

  const onClick = (event: MouseEvent) => {
    const anchor = outputDownloadAnchor(event.target);
    if (!anchor || !securityDetected) return;
    event.preventDefault();
    if (!bearerToken) {
      if (!authenticationRequired) {
        authenticationRequired = true;
        emit();
      }
      return;
    }
    const url = new URL(anchor.href, window.location.href);
    void wrappedFetch(url.toString(), { method: "GET" })
      .then(async response => {
        if (!response.ok) throw new Error(`Readback download HTTP ${response.status}`);
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        try {
          const download = document.createElement("a");
          download.href = objectUrl;
          download.download = responseFilename(
            response,
            decodeURIComponent(url.pathname.split("/").pop() ?? "readback.bin"),
          );
          download.style.display = "none";
          document.body.appendChild(download);
          download.click();
          download.remove();
        } finally {
          URL.revokeObjectURL(objectUrl);
        }
      })
      .catch(error => {
        console.error("Authenticated readback download failed", error);
      });
  };

  window.fetch = wrappedFetch;
  document.addEventListener("click", onClick, true);
  uninstallTransport = () => {
    if (window.fetch === wrappedFetch) window.fetch = originalFetch;
    document.removeEventListener("click", onClick, true);
    uninstallTransport = null;
  };
  return uninstallTransport;
}

// This module is imported by the root client provider. Installing at module
// evaluation time ensures the transport exists before child polling/effects can
// issue the first protected Gateway request during hydration.
if (typeof window !== "undefined") installSecurityTransport();
