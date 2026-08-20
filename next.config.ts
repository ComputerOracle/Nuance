import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Pin the workspace root to this project: a stray lockfile in the parent
  // home directory otherwise makes Next.js's auto-detection ambiguous.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
