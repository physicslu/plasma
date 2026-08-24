"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import "./production-workspace-nav.css";

export default function ProductionWorkspaceNav() {
  const pathname = usePathname();
  const factoryActive = pathname === "/fleet";
  const singlePpuActive = pathname === "/fleet/programming" || pathname.startsWith("/fleet/programming/");

  return (
    <nav className="productionWorkspaceNav" aria-label="Production workspaces">
      <span>PRODUCTION</span>
      <Link href="/fleet" aria-current={factoryActive ? "page" : undefined}>
        Factory Console
      </Link>
      <Link href="/fleet/programming" aria-current={singlePpuActive ? "page" : undefined}>
        Single PPU Programming
      </Link>
    </nav>
  );
}
