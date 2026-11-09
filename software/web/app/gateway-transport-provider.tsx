"use client";

import { useEffect } from "react";
import { installGatewayTransport } from "./gateway-transport";

/** Installs the Gateway routing transport for the whole Console. */
export function GatewayTransportProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => installGatewayTransport(), []);
  return <>{children}</>;
}
