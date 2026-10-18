"use client";
import { OVR_BANDS, TONE, type Meaning, type Tone } from "@/lib/meaning";

// 숫자 옆 '뜻' 꼬리표 — lib/meaning 의 단어·색(다섯 단계)을 그대로 쓴다.
export function MeaningTag({ m, title, sm = false }: { m: Meaning; title?: string; sm?: boolean }) {
  return (
    <span className={`mn-tag${sm ? " sm" : ""}`} style={{ color: m.c, background: m.bg }} title={title}>{m.label}</span>
  );
}

const LEGENDS: Record<string, [string, Tone][]> = {
  idx: [["리그 최상위 80+", "best"], ["평균 이상 62+", "good"], ["평균권 (50 = 리그 평균)", "avg"], ["평균 이하", "weak"], ["리그 최하위 20↓", "bad"]],
  pct: [["상위 10%", "best"], ["상위 30%", "good"], ["평균권", "avg"], ["하위 30%", "weak"], ["하위 10%", "bad"]],
  rank: [["리그 최상위", "best"], ["상위권", "good"], ["중위권", "avg"], ["하위권", "weak"], ["리그 최하위", "bad"]],
  form: [["절정 90+", "best"], ["좋음 80+", "good"], ["보통 (72 = 중간)", "avg"], ["주춤", "weak"], ["부진", "bad"]],
  ss: [["최상급 7.5+", "best"], ["좋음 7.0+", "good"], ["보통 (평균 6.8~6.9)", "avg"], ["아쉬움", "weak"], ["부진 6.3↓", "bad"]],
};

/** 색 범례 한 줄 — kind: idx(50 = 평균 지수) · pct(백분위) · rank(순위) · form · ss(평점) · ovr. */
export function ScaleLegend({ kind, lead }: { kind: "idx" | "pct" | "rank" | "form" | "ss" | "ovr"; lead?: string }) {
  if (kind === "ovr") {
    return (
      <div className="mn-legend">
        {lead && <b>{lead}</b>}
        {OVR_BANDS.slice(0, 6).map((b) => <span key={b.range}><i style={{ background: b.c }} />{b.ko} {b.range}</span>)}
      </div>
    );
  }
  return (
    <div className="mn-legend">
      {lead && <b>{lead}</b>}
      {LEGENDS[kind].map(([l, t]) => <span key={l}><i style={{ background: TONE[t].c }} />{l}</span>)}
    </div>
  );
}
