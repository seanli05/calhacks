import type { NextConfig } from "next";

/** The browser only ever talks to this app; `/api` is proxied to FastAPI, so no CORS setup. */
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // A second dev server (e.g. fixtures beside live data) needs its own build folder.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
