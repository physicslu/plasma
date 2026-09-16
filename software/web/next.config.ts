import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const productStandaloneBuild = process.env.PLASMA_PRODUCT_BUILD === "1";
const configDir = dirname(fileURLToPath(import.meta.url));
const productManifestPath = resolve(configDir, "../../release/product.json");
const productManifest = JSON.parse(readFileSync(productManifestPath, "utf8")) as {
  product_version?: unknown;
};
const productVersion = productManifest.product_version;

if (typeof productVersion !== "string" || !/^\d+\.\d+\.\d+$/.test(productVersion)) {
  throw new Error("release/product.json must define a semantic product_version");
}

const nextConfig: NextConfig = {
  ...(productStandaloneBuild ? { output: "standalone" as const } : {}),
  env: {
    NEXT_PUBLIC_PLASMA_PRODUCT_VERSION: productVersion,
  },
  async redirects() {
    return [
      {
        source: "/ppu",
        destination: "/engineering",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
