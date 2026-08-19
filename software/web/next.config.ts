import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
