/** @type {import('next').NextConfig} */
// 백엔드(FastAPI) 주소. 로컬은 127.0.0.1:8000, 배포는 Vercel 환경변수 API_BASE 에
// Render 백엔드 URL 지정(예: https://football26-api.onrender.com). 프론트는 항상 /api/* 로만
// 호출하고 여기서 실제 백엔드로 프록시 → 브라우저는 same-origin(=CORS 불필요).
const API_BASE = process.env.API_BASE || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_BASE}/api/:path*` },
    ];
  },
};
export default nextConfig;
