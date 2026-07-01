/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 개발 편의: API 를 같은 오리진(/api/*)으로 프록시해 CORS 신경 안 쓰게.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" },
    ];
  },
};
export default nextConfig;
