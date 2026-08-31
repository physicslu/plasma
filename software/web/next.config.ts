import type { NextConfig } from "next";

const productStandaloneBuild = process.env.PLASMA_PRODUCT_BUILD === "1";

const nextConfig: NextConfig = {
  ...(productStandaloneBuild ? { output: "standalone" as const } : {}),
  async rewrites() {
    return [
      {
        source: "/ppu",
        destination: "/",
      },
    ];
  },
};

export default nextConfig;
