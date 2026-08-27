type SecurityTransportState = {
  credentialLoaded: boolean;
  authenticationRequired: boolean;
};

type Listener = () => void;

const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_PLASMA_API_URL ?? "https://plasma.open4th.com";
const listeners = new Set<Listener>();
const ambiguousCommandIds = new Map<string, string>();
let bearerToken: string | null = null;
let authenticationRequired = false;
let uninstallTransport: (() => void) | null = null;

const gatewayPathPrefixes = [
  "/api/status",
  "/api/jobs",
  "/api/batches",
  "/api/settings/gateway",
  "/api/mock/runtime",
  "/api/engineering",
  "/api/devices/search",
  "/api/health",
  "/api/node",
];

function emit(): void {
  listeners.forEach(listener => listener());
}

export function subscribeSecurityTransport(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getSecurityTransportState(): SecurityTransportState {
  return {
    credentialLoaded: bearerToken !== null,
    authenticationRequired,
  };
}

export function getSecurityTransportServerState(): SecurityTransportState {
  return { credentialLoaded: false, authenticationRequired: false };
}

export function setSecurityBearerToken(token: string): void {
  const normalized = token.trim();
  if (normalized.length < 32 || normalized.length > 512) {
    throw new Error("Plasma Bearer token must contain 32..512 characters");
  }
  bearerToken = normalized;
  authenticationRequired = false;
  emit();
}

export function clearSecurityBearerToken(): void {
  bearerToken = null;
  authenticationRequired = false;
  ambiguousCommandIds.clear();
  emit();
}

function configuredGatewayOrigins(): Set<string> {
  const origins = new Set<string>();
  for (const candidate of [
    DEFAULT_API_BASE,
    typeof window !== "undefined" ? window.localStorage.getItem("plasma-api-base") : null,
  ]) {
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

function isGatewayPath(pathname: string): boolean {
  return gatewayPathPrefixes.some(prefix => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

function isGatewayRequest(url: URL): boolean {
  return configuredGatewayOrigins().has(url.origin) && isGatewayPath(url.pathname);
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
    if (!/^\/api\/(?:engineering\/targets\/[^/]+\/[^/]+\/api\/)?jobs\/[^/]+\/files\/[^/]+$/.test(url.pathname)) {
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
    const rawUrl = typeof Request !== "undefined" && input instanceof Request ? input.url : String(input);
    const url = new URL(rawUrl, window.location.href);
    if (!isGatewayRequest(url)) return await originalFetch(input, init);

    const method = requestMethod(input, init);
    const headers = mergedHeaders(input, init);
    if (bearerToken && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${bearerToken}`);
    }

    let identity: string | null = null;
    if (isStateChanging(method) && !headers.has("Idempotency-Key")) {
      identity = commandIdentity(url, method, init);
      const commandId = ambiguousCommandIds.get(identity) ?? `browser-${window.crypto.randomUUID()}`;
      ambiguousCommandIds.set(identity, commandId);
      headers.set("Idempotency-Key", commandId);
    }

    const nextInit: RequestInit = { ...init, headers };
    const request = typeof Request !== "undefined" && input instanceof Request
      ? new Request(input, nextInit)
      : input;

    try {
      const response = await originalFetch(request, request === input ? nextInit : undefined);
      if (response.status === 401) {
        if (!authenticationRequired) {
          authenticationRequired = true;
          emit();
        }
      } else if (bearerToken && authenticationRequired) {
        authenticationRequired = false;
        emit();
      }
      if (identity && response.status !== 409) ambiguousCommandIds.delete(identity);
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
    if (!anchor || !bearerToken) return;
    event.preventDefault();
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
