import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Plasma Product Modes",
  description: "Choose between Production Mode and Engineering Mode",
};

export default function DemoLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
