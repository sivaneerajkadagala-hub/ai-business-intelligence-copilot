import type { NextConfig } from "next";

// Server-side proxy so the browser only ever talks to this app's origin.
// In dev NEXT_PUBLIC_API_URL points straight at :8000 and this is unused;
// in the Docker build API_INTERNAL_URL targets the backend's private host.
const apiInternalUrl =
  process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiInternalUrl}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
