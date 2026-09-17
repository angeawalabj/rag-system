/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",

  // Headers de sécurité
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options",  value: "nosniff" },
          { key: "X-Frame-Options",          value: "DENY" },
          { key: "Referrer-Policy",          value: "strict-origin-when-cross-origin" },
        ],
      },
      // SSE : désactive le buffering nginx/proxies pour les routes /api/query
      {
        source: "/api/query",
        headers: [
          { key: "X-Accel-Buffering", value: "no" },
          { key: "Cache-Control",     value: "no-cache, no-transform" },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
