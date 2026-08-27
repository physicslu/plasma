export type SecurityScope = {
  facility_id: string;
  ppu_id: string;
  site_ids: "*" | number[];
};

export type SecurityPrincipal = {
  id: string;
  roles: string[];
  permissions: string[];
  scopes: SecurityScope[];
};

type SecurityMePayload = {
  ok?: boolean;
  principal?: SecurityPrincipal;
  error?: {
    error_code?: string;
    message?: string;
  };
};

export class SecurityProfileError extends Error {
  readonly status: number;
  readonly errorCode?: string;

  constructor(message: string, status: number, errorCode?: string) {
    super(message);
    this.name = "SecurityProfileError";
    this.status = status;
    this.errorCode = errorCode;
  }
}

export async function getSecurityPrincipal(apiBase: string): Promise<SecurityPrincipal> {
  const response = await fetch(`${apiBase.replace(/\/$/, "")}/api/security/me`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });

  let payload: SecurityMePayload = {};
  try {
    payload = await response.json() as SecurityMePayload;
  } catch {
    // Canonical non-secure Gateways do not implement this opt-in endpoint.
  }

  if (!response.ok || !payload.principal) {
    throw new SecurityProfileError(
      payload.error?.message ?? `Security profile request failed (HTTP ${response.status})`,
      response.status,
      payload.error?.error_code,
    );
  }
  return payload.principal;
}

export function principalHasPermission(principal: SecurityPrincipal | null, permission: string): boolean {
  return Boolean(principal?.permissions.includes(permission));
}
