"use client";
import type { Fixture, FixtureSide } from "@/lib/api";

// 다가오는 경기 카드 — 글로벌 '이번 주 빅매치'·팀 Overview '다음 경기' 공용.
// 일정은 클라우드 daily_data 가 매일 갱신(ESPN), 순위·폼·전력은 API 가 붙인다(src/match_center.py).
const FORM_C: Record<string, string> = { W: "#2fae6a", D: "#6b7382", L: "#c8414f" };

// 두 팀 색이 비슷하면(예: 노팅엄·아스날 모두 빨강) 원정 쪽은 중립색 — 전력 막대가 한 덩어리로 보이지 않게
function close(a: string, b: string) {
  const rgb = (h: string) => { const x = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(x.slice(i, i + 2), 16) || 0); };
  const [p, q] = [rgb(a), rgb(b)];
  return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]) < 90;
}

function dday(d: number) {
  return d <= 0 ? "오늘" : d === 1 ? "내일" : `D-${d}`;
}

function Side({ s, onPick, align }: { s: FixtureSide; onPick?: (team: string, league?: string | null) => void; align: "l" | "r" }) {
  return (
    <button className={`mc-side ${align}`} onClick={(e) => { e.stopPropagation(); onPick?.(s.team, s.league); }}
      disabled={!onPick || !s.league} title={s.league ? `${s.team} 열기` : s.team}>
      {s.logo ? <img className="mc-logo" src={s.logo} alt="" /> : <span className="mc-logo ph" style={{ background: s.color }} />}
      <span className="mc-team">{s.team}</span>
      <span className="mc-meta">
        {s.rank ? <b>{s.rank}위</b> : null}
        {s.form.length > 0 && <span className="mc-form">{s.form.map((r, i) => <i key={i} style={{ background: FORM_C[r] }} title={r} />)}</span>}
      </span>
    </button>
  );
}

export default function MatchCard({ m, onPick, compact = false }:
  { m: Fixture; onPick?: (team: string, league?: string | null) => void; compact?: boolean }) {
  const ho = m.home.ovr, ao = m.away.ovr;
  const share = ho && ao ? Math.round((ho ** 4 / (ho ** 4 + ao ** 4)) * 100) : null;   // 전력 비교(팀 OVR, 차이 강조)
  return (
    <div className={`mc-card${compact ? " compact" : ""}${m.comp_code === "uefa.champions" ? " ucl" : ""}`}>
      <div className="mc-top">
        <span className="mc-comp">{m.comp}</span>
        <span className="mc-when">{m.kst}</span>
        <span className="mc-dday">{dday(m.d_day)}</span>
      </div>
      <div className="mc-teams">
        <Side s={m.home} onPick={onPick} align="l" />
        <span className="mc-vs">vs</span>
        <Side s={m.away} onPick={onPick} align="r" />
      </div>
      {share !== null && (
        <div className="mc-power" title={`팀 OVR ${ho} : ${ao}`}>
          <span style={{ width: `${share}%`, background: m.home.color }} />
          <span style={{ width: `${100 - share}%`, background: close(m.home.color, m.away.color) ? "#8a94a8" : m.away.color }} />
        </div>
      )}
      {!compact && m.tags.length > 0 && (
        <div className="mc-tags">{m.tags.map((t) => <span key={t}>{t}</span>)}</div>
      )}
    </div>
  );
}
