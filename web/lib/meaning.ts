// 숫자의 '뜻' — 사이트 전체가 같은 단어·같은 색으로 읽히게 하는 한 곳.
// 2026-10-15 사용자 지적: SEASON PROFILE 'ATTACK OUTPUT 52' 가 초록색이라 축구를 잘 모르는 사람은 52 가 좋은 건지
// 알 수 없다. 화면마다 색 기준이 달랐다(OVR 등급표 3종, 초록·빨강 계열 5~6가지, OVR 용 tier() 를 '50 = 평균' 지수에 사용).
// 규칙: 숫자 옆에는 이 파일의 단어(MeaningTag)를 붙이고, 색은 TONE 다섯 단계만 쓴다.

export type Tone = "best" | "good" | "avg" | "weak" | "bad";
export const TONE: Record<Tone, { c: string; bg: string; bar: string }> = {
  best: { c: "#3ecf8e", bg: "rgba(62,207,142,0.16)", bar: "linear-gradient(90deg,#1f9e6a,#3ecf8e)" },
  good: { c: "#9be0bd", bg: "rgba(155,224,189,0.13)", bar: "linear-gradient(90deg,#3f8f6b,#8fd8b2)" },
  avg: { c: "#aeb7c7", bg: "rgba(174,183,199,0.12)", bar: "linear-gradient(90deg,#5b6576,#9aa4b4)" },
  weak: { c: "#f2b06f", bg: "rgba(242,176,111,0.15)", bar: "linear-gradient(90deg,#a8692c,#f2b06f)" },
  bad: { c: "#ff7a8a", bg: "rgba(255,122,138,0.15)", bar: "linear-gradient(90deg,#b8404f,#ff7a8a)" },
};
export type Meaning = { label: string; tone: Tone; c: string; bg: string; bar: string };
const m = (label: string, tone: Tone): Meaning => ({ label, tone, ...TONE[tone] });

/** 리그 안 상대 지수 0~99 — 50 = 리그 평균(팀 프로필·전술 성향·분석 지수). */
export function idxMeaning(v: number | null | undefined): Meaning {
  if (v == null || Number.isNaN(v)) return m("자료 없음", "avg");
  if (v >= 80) return m("리그 최상위", "best");
  if (v >= 62) return m("평균 이상", "good");
  if (v > 38) return m("평균권", "avg");
  if (v > 20) return m("평균 이하", "weak");
  return m("리그 최하위", "bad");
}
export const IDX_NOTE = "50 = 리그 평균 · 62+ 평균 이상 · 80+ 리그 최상위 · 38 이하 평균 이하";

/** 백분위 0~100(높을수록 좋음) → '상위 N%'. */
export function pctMeaning(p: number | null | undefined): Meaning {
  if (p == null || Number.isNaN(p)) return m("자료 없음", "avg");
  const top = Math.max(1, Math.round(100 - p));
  if (p >= 90) return m(`상위 ${top}%`, "best");
  if (p >= 70) return m(`상위 ${top}%`, "good");
  if (p >= 30) return m("평균권", "avg");
  if (p >= 10) return m(`하위 ${Math.max(1, Math.round(p))}%`, "weak");
  return m(`하위 ${Math.max(1, Math.round(p))}%`, "bad");
}

/** 리그 순위(1 = 최고). */
export function rankMeaning(rank: number | null | undefined, n: number | null | undefined): Meaning {
  if (!rank || !n) return m("자료 없음", "avg");
  const q = (rank - 0.5) / n;
  if (q <= 0.15) return m("리그 최상위", "best");
  if (q <= 0.35) return m("상위권", "good");
  if (q < 0.65) return m("중위권", "avg");
  if (q < 0.85) return m("하위권", "weak");
  return m("리그 최하위", "bad");
}

// OVR(현재 기량 45~99) — OVR GUIDE 와 같은 띠. tier()(lib/ui) 도 같은 경계를 쓴다.
export const OVR_BANDS: { min: number; range: string; en: string; ko: string; desc: string; c: string; deep: string }[] = [
  { min: 90, range: "90+", en: "WORLD CLASS", ko: "월드클래스", desc: "세계 최정상 — 8개 리그 통틀어 10명 안팎", c: "#f9dd7e", deep: "#c2902a" },
  { min: 86, range: "86–89", en: "ELITE", ko: "엘리트", desc: "빅클럽 핵심 주전 · 대표팀 주축", c: "#7fe3b0", deep: "#1f8a4c" },
  { min: 82, range: "82–85", en: "TOP STARTER", ko: "상위 주전", desc: "상위권 팀 주전", c: "#8fdde3", deep: "#2a8f97" },
  { min: 77, range: "77–81", en: "STARTER", ko: "주전급", desc: "리그 주전급", c: "#7fb4f0", deep: "#2b62b0" },
  { min: 72, range: "72–76", en: "ROTATION", ko: "로테이션", desc: "로테이션 · 중하위권 주전", c: "#b3bccb", deep: "#5b6576" },
  { min: 65, range: "65–71", en: "SQUAD", ko: "스쿼드", desc: "백업 · 성장 중인 유망주", c: "#8f99aa", deep: "#454d5b" },
  { min: 0, range: "~64", en: "FRINGE", ko: "검증 전", desc: "출전이 적거나 검증 전", c: "#6f7889", deep: "#3a414d" },
];
export function ovrBand(ovr: number) {
  return OVR_BANDS.find((b) => ovr >= b.min) ?? OVR_BANDS[OVR_BANDS.length - 1];
}
export function ovrMeaning(ovr: number | null | undefined): Meaning {
  if (ovr == null) return m("자료 없음", "avg");
  const b = ovrBand(ovr);
  const tone: Tone = ovr >= 86 ? "best" : ovr >= 82 ? "good" : ovr >= 77 ? "avg" : ovr >= 72 ? "weak" : "bad";
  return { ...m(b.ko, tone), c: b.c };
}

/** 폼(이번 시즌 리그·포지션 안 위치 45~99, 중앙 72). */
export function formMeaning(f: number | null | undefined): Meaning {
  if (f == null) return m("기록 부족", "avg");
  if (f >= 90) return m("절정", "best");
  if (f >= 80) return m("좋음", "good");
  if (f >= 64) return m("보통", "avg");
  if (f >= 55) return m("주춤", "weak");
  return m("부진", "bad");
}
export const FORM_NOTE = "폼 = 이번 시즌 같은 리그·포지션 선수 중 위치(72 = 중간, 90+ 상위 10%)";

/** Sofascore 평점(6.0~10, 리그 평균 6.8~6.9). */
export function ssMeaning(r: number | null | undefined): Meaning {
  if (r == null || !r) return m("기록 부족", "avg");
  if (r >= 7.5) return m("최상급", "best");
  if (r >= 7.1) return m("좋음", "good");
  if (r >= 6.75) return m("보통", "avg");
  if (r >= 6.5) return m("아쉬움", "weak");
  return m("부진", "bad");
}
export const SS_NOTE = "평점 = Sofascore 경기 평점 평균(리그 평균 6.8~6.9 · 7.1+ 좋음 · 7.5+ 최상급)";

/** 0~100 적합도·유사도·점수(높을수록 좋음, 50 = 보통). */
export function scoreMeaning(v: number | null | undefined): Meaning {
  if (v == null) return m("자료 없음", "avg");
  if (v >= 80) return m("매우 높음", "best");
  if (v >= 65) return m("높음", "good");
  if (v >= 45) return m("보통", "avg");
  if (v >= 30) return m("낮음", "weak");
  return m("매우 낮음", "bad");
}

/** 포지션 뎁스 0~100(2·3번째 옵션의 질 + 인원). */
export function depthMeaning(d: number): Meaning {
  if (d >= 75) return m("탄탄", "best");
  if (d >= 65) return m("양호", "good");
  if (d >= 55) return m("보통", "avg");
  if (d >= 45) return m("얇음", "weak");
  return m("매우 얇음", "bad");
}

/** 승률·확률(%) — 기준(무작위 33% 등) 대비. */
export function vsBaseline(v: number, base: number): Meaning {
  const d = v - base;
  if (d >= 15) return m("기준보다 크게 높음", "best");
  if (d >= 5) return m("기준보다 높음", "good");
  if (d > -5) return m("기준 수준", "avg");
  return m("기준보다 낮음", "weak");
}

/** 차이 값(+면 좋음) 색. */
export function signTone(v: number, eps = 0): Meaning {
  return v > eps ? m("좋아짐", "good") : v < -eps ? m("나빠짐", "weak") : m("변화 없음", "avg");
}

/** 경기당 승점(0~3) — 시즌 페이스(38경기 환산 대략: 2.2 ≈ 84점 우승권 · 1.8 ≈ 68점 유럽권 · 1.0 ≈ 38점 강등권). */
export function ppgMeaning(v: number | null | undefined): Meaning {
  if (v == null || Number.isNaN(v)) return m("자료 없음", "avg");
  if (v >= 2.2) return m("우승권 페이스", "best");
  if (v >= 1.75) return m("유럽권 페이스", "good");
  if (v >= 1.25) return m("중위권 페이스", "avg");
  if (v >= 1.0) return m("하위권 페이스", "weak");
  return m("강등권 페이스", "bad");
}
