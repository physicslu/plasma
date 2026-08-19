import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Plasma Demos",
  description: "Choose between the standalone PPU Console and read-only Manager/Fleet demo",
};

export default function DemoLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
