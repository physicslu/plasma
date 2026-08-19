import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Plasma Fleet Demo",
  description: "Read-only Facility and PPU fleet observation demo",
};

export default function FleetLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
