const BACKEND_INTERNAL_URL = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_INTERNAL_URL}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${BACKEND_INTERNAL_URL}/health`,
      },
      {
        source: "/docs",
        destination: `${BACKEND_INTERNAL_URL}/docs`,
      },
      {
        source: "/openapi.json",
        destination: `${BACKEND_INTERNAL_URL}/openapi.json`,
      },
      {
        source: "/ws/:path*",
        destination: `${BACKEND_INTERNAL_URL}/ws/:path*`,
      },
    ];
  },
};

export default nextConfig;
