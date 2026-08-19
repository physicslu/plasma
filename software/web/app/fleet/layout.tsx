import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Plasma Production Mode",
  description: "Factory Production Console for multi-PPU production observation",
};

export default function FleetLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
