import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

const renderRoot = fileURLToPath(new URL("./", import.meta.url));
const webRoot = fileURLToPath(new URL("../", import.meta.url));

export default defineConfig({
  root: renderRoot,
  publicDir: fileURLToPath(new URL("../public", import.meta.url)),
  plugins: [react()],
  define: {
    "process.env.NEXT_PUBLIC_PLASMA_API_URL": "window.location.origin",
  },
  resolve: {
    alias: {
      "@": webRoot,
      "next/link": fileURLToPath(new URL("./next-link.tsx", import.meta.url)),
      "next/navigation": fileURLToPath(new URL("./next-navigation.ts", import.meta.url)),
    },
  },
  build: {
    outDir: fileURLToPath(new URL("../dist-render", import.meta.url)),
    emptyOutDir: true,
    sourcemap: false,
  },
});
