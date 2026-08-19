import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      {
        source: "/",
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
