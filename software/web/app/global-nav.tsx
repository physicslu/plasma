"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navigationItems = [
  { href: "/demo", label: "入口" },
  { href: "/ppu", label: "單機 PPU" },
  { href: "/fleet", label: "多機 Fleet" },
] as const;

function isActive(pathname: string, href: string): boolean {
  if (href === "/ppu") return pathname === "/" || pathname === "/ppu" || pathname.startsWith("/ppu/");
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function GlobalNav() {
  const pathname = usePathname();

  return (
    <header className="globalAppNav">
      <Link className="globalAppNavBrand" href="/demo" aria-label="Plasma demo entry">
        <span>P</span>
        <b>PLASMA</b>
      </Link>
      <nav aria-label="Plasma global navigation">
        {navigationItems.map(item => {
          const active = isActive(pathname, item.href);
          return (
            <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined}>
              {item.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
