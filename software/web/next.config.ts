import type { NextConfig } from "next";

const productStandaloneBuild = process.env.PLASMA_PRODUCT_BUILD === "1";

const nextConfig: NextConfig = {
  ...(productStandaloneBuild ? { output: "standalone" as const } : {}),
  async redirects() {
    return [
      {
        source: "/",
        has: [{ type: "host", value: "plasma.open4th.com" }],
        destination: "/demo",
        permanent: false,
      },
    ];
  },
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
