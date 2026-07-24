"use client";
// 공용 스켈레톤 — 모든 탭의 "불러오는 중…" 텍스트를 형태 보존 로딩으로 대체.

export function Skel({ w = "100%", h = 14, r, circle = false, style }: {
  w?: number | string; h?: number | string; r?: number; circle?: boolean; style?: React.CSSProperties;
}) {
  return (
    <span
      className={`skel${circle ? " skel-circle" : ""}`}
      style={{ display: "block", width: w, height: h, ...(r != null ? { borderRadius: r } : {}), ...style }}
    />
  );
}

/* 카드 그리드 (선수 카드·듀오 카드 등) */
export function SkelCards({ n = 6, cols = "repeat(auto-fill, minmax(230px, 1fr))", face = true }: {
  n?: number; cols?: string; face?: boolean;
}) {
  return (
    <div className="skel-grid" style={{ gridTemplateColumns: cols }}>
      {Array.from({ length: n }, (_, i) => (
        <div className="skel-card" key={i}>
          <div className="skel-row">
            {face && <Skel w={46} h={46} circle />}
            <div className="skel-stack" style={{ flex: 1, gap: 7 }}>
              <Skel w="72%" h={13} />
              <Skel w="46%" h={10} />
            </div>
          </div>
          <Skel h={8} />
          <Skel w="58%" h={8} />
        </div>
      ))}
    </div>
  );
}

/* 행 리스트 (일정·시그널·이적 목록 등) */
export function SkelRows({ n = 8, h = 40 }: { n?: number; h?: number }) {
  return (
    <div className="skel-stack skel-wrap">
      {Array.from({ length: n }, (_, i) => <Skel key={i} h={h} r={10} />)}
    </div>
  );
}

/* 피치 로딩 (라인업·전술판) */
export function SkelPitch() {
  return (
    <div className="skel-wrap">
      <Skel h={380} r={16} />
    </div>
  );
}

/* 탭 전체 로딩 — 히어로 + 카드 그리드 근사 */
export function SkelTab() {
  return (
    <div className="skel-wrap">
      <Skel h={128} r={18} style={{ marginBottom: 16 }} />
      <SkelCards n={6} />
    </div>
  );
}

export function EmptyState({ icon = "📭", title, hint }: { icon?: string; title: string; hint?: string }) {
  return (
    <div className="placeholder">
      <div className="ph-icon">{icon}</div>
      <div className="ph-title">{title}</div>
      {hint && <div className="ph-sub">{hint}</div>}
    </div>
  );
}
