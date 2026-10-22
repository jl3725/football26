// 공용 UI 헬퍼 — OVR 티어 색·색 유틸.
import { ovrBand } from "./meaning";

export type Tier = { light: string; deep: string; name: string; ko: string };

// OVR 전용 색·등급 — OVR GUIDE(lib/meaning OVR_BANDS)와 같은 경계. 예전엔 85 가 여기선 ELITE(금색),
// 기준표에선 TOP STARTER 였다. '50 = 평균' 지수·점수에는 쓰지 말고 lib/meaning 의 idxMeaning·scoreMeaning 을 쓴다.
export function tier(v: number): Tier {
  const b = ovrBand(v);
  return { light: b.c, deep: b.deep, name: b.en, ko: b.ko };
}

// 선수 카드 등급(FUT 카드 느낌) — OVR 띠와 맞춤: 월드클래스 90+ · 엘리트 86+ · 주전급 77+ · 그 외
export function futTier(ovr: number): "elite" | "gold" | "silver" | "bronze" {
  return ovr >= 90 ? "elite" : ovr >= 86 ? "gold" : ovr >= 77 ? "silver" : "bronze";
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


/** 나이 표기 — 0·빈값이면 '나이 —'(출처마다 나이가 빈 선수가 '0세'로 보였다, 2026-10-22). */
export const ageText = (a: number | null | undefined): string => (a && a > 0 ? `${Math.floor(a)}세` : "나이 —");
