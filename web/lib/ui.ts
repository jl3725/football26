// 공용 UI 헬퍼 — OVR 티어 색·색 유틸.

export type Tier = { light: string; deep: string; name: string };

export function tier(v: number): Tier {
  if (v >= 85) return { light: "#f9dd7e", deep: "#c2902a", name: "ELITE" };
  if (v >= 80) return { light: "#7fe3b0", deep: "#1f8a4c", name: "STRONG" };
  if (v >= 75) return { light: "#7fb4f0", deep: "#2b62b0", name: "SOLID" };
  return { light: "#aeb7c7", deep: "#5b6576", name: "DEVELOPING" };
}

export function hexA(hex: string, a: number): string {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(full, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

// 역할(Role Reality) 태그 → 색 계열 (검증 강도 순). 대회별 사용량 기반.
export function roleClass(role: string): string {
  if (role === "핵심 주전") return "r-core";
  if (role === "주전·유럽 로테이션" || role === "리그 주전") return "r-starter";
  if (role === "로테이션" || role === "유망주 출전") return "r-rot";
  return "r-fringe"; // 백업 · 컵 전용 · 주변 자원
}

// 어두운 팀컬러는 살짝 밝혀 강조색으로.
export function accent(hex: string): string {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(full, 16);
  let r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  if (lum < 0.32) {
    const k = 0.42;
    r = Math.round(r + (255 - r) * k);
    g = Math.round(g + (255 - g) * k);
    b = Math.round(b + (255 - b) * k);
  }
  return `rgb(${r},${g},${b})`;
}
