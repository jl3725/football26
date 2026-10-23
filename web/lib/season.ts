import type { Window } from "./api";

/**
 * 시즌 단계 — 백엔드 season_context.season_phase 와 동일.
 *  - in_season : 데이터 시즌 == 달력 시즌 → 순위·라인업 중심, '다음 시즌' 뷰 숨김
 *  - offseason : 여름 이적시장(다음 시즌 준비) → 다음 시즌 로스터·예상 XI 먼저
 *  - stale     : 새 시즌이 시작됐는데 데이터 전환 전
 * phase 를 모르는 응답(구 캐시 스냅샷 등)은 기존 동작(오프시즌)으로 본다.
 */
export type Phase = "in_season" | "offseason" | "stale";

export const phaseOf = (w?: Pick<Window, "phase"> | null): Phase => w?.phase ?? "offseason";

/** '다음 시즌'(예상 XI·다음 시즌 로스터)을 보여줄 단계인가 */
export const showNextSeason = (w?: Pick<Window, "phase"> | null): boolean => phaseOf(w) !== "in_season";

/** 2026 → "2026/27" */
export function seasonLongLabel(startYear?: number | null): string {
  if (!startYear) return "";
  return `${startYear}/${String((startYear + 1) % 100).padStart(2, "0")}`;
}

/** 시즌 상태 한 줄 — 홈·오버뷰 공용. 예) "26/27 시즌 진행 중 · 겨울 이적시장 진행 중" */
export function seasonStatusText(w: Window | null | undefined, dataSeason: string, nextLabel: string): string {
  const win = w?.is_open ? ` · ${w.kr ?? ""} 이적시장 진행 중` : "";
  switch (phaseOf(w)) {
    case "in_season":
      return `${dataSeason} 시즌 진행 중${win}`;
    case "stale":
      return `${w?.label ?? nextLabel} 시즌 진행 중 · 표시 데이터 ${dataSeason}(갱신 대기)`;
    default:
      return `${dataSeason} 시즌 종료 · ${nextLabel} 개막 전${win}`;
  }
}

/** 상태바용 짧은 라벨 */
export function seasonChip(w: Window | null | undefined, dataSeason: string, short = false): string {
  switch (phaseOf(w)) {
    case "in_season":
      return short ? dataSeason : `${dataSeason} 시즌 진행 중`;
    case "stale":
      return `${dataSeason} 데이터 · 갱신 대기`;
    default:
      return `${dataSeason} 시즌 종료`;
  }
}
