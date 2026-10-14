"use client";
import type { Trend } from "@/lib/api";

// OVR 옆 추이 화살표. 2주 전 대비가 있으면 그것(진하게), 기록이 아직 2주치 안 쌓였으면 지난 시즌 대비(흐리게).
// 기록은 src/rating_history.py 가 매일 남긴다.
export function TrendArrow({ t, ovr }: { t?: Trend | null; ovr: number }) {
  if (!t) return null;
  if (t.ovr_d != null) {
    if (t.ovr_d === 0) return null;
    const up = t.ovr_d > 0;
    return <span className={`trend ${up ? "up" : "down"}`} title={`2주 전 대비 ${up ? "+" : ""}${t.ovr_d}`}>
      {up ? "▲" : "▼"}{Math.abs(t.ovr_d)}</span>;
  }
  if (t.ovr_prev != null) {
    const d = ovr - t.ovr_prev;
    if (d === 0) return null;
    return <span className={`trend season ${d > 0 ? "up" : "down"}`} title={`지난 시즌 ${t.ovr_prev} → 지금 ${ovr}`}>
      {d > 0 ? "▲" : "▼"}{Math.abs(d)}</span>;
  }
  return null;
}

const sign = (d: number) => (d > 0 ? `▲${d}` : d < 0 ? `▼${-d}` : "−");
const tone = (d: number) => (d > 0 ? "up" : d < 0 ? "down" : "flat");

// 선수 상세용 — 두 기준을 글로 함께
export function TrendLine({ t, ovr }: { t?: Trend | null; ovr: number }) {
  if (!t || (t.ovr_d == null && t.ovr_prev == null)) return null;
  return (
    <div className="trend-line">
      {t.ovr_d != null && <span>2주 <b className={tone(t.ovr_d)}>{sign(t.ovr_d)}</b></span>}
      {t.form_d != null && t.form_d !== 0 && <span>폼 <b className={tone(t.form_d)}>{sign(t.form_d)}</b></span>}
      {t.ovr_prev != null && <span>지난 시즌 {t.ovr_prev} <b className={tone(ovr - t.ovr_prev)}>{sign(ovr - t.ovr_prev)}</b></span>}
    </div>
  );
}
