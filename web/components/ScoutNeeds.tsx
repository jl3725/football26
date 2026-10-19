"use client";
import { fmtEur, type Needs, type PositionNeed } from "@/lib/api";
import { hexA, tier } from "@/lib/ui";
import { TONE } from "@/lib/meaning";
import { usePeek } from "./PlayerPeek";

// 스카우트 데스크 — 포지션 니즈 v2(api _position_needs): 뎁스 · 지금 가용(부상) · 이번 창 순증감 · 주전 폼 · 나이·계약.
// 2026-10-19 사용자: "아스날 좌윙(마르티넬리·트로사르 이탈, 촐리스 1명 영입)이 얇은데 '수비 약점'이라고 한다 —
// 부상·폼·이적 평가·이적 정책까지 시즌 중에 유기적으로". 리크루트 풀·드림 타깃도 같은 니즈 순서로 후보를 고른다.
const LEVEL: Record<PositionNeed["level"], { ko: string; tone: keyof typeof TONE }> = {
  urgent: { ko: "시급", tone: "bad" }, need: { ko: "보강 필요", tone: "weak" }, watch: { ko: "관찰", tone: "avg" }, ok: { ko: "충분", tone: "good" },
};

function RoleCard({ n, team }: { n: PositionNeed; team: string }) {
  const peek = usePeek();
  const lv = LEVEL[n.level];
  const t = TONE[lv.tone];
  const w = n.window;
  return (
    <div className="pn-card" style={{ borderLeftColor: t.c }}>
      <div className="pn-top">
        <span className="pn-role">{n.role}</span>
        <span className="pn-label">{n.label}</span>
        <span className="pn-lv" style={{ color: t.c, background: t.bg }}>{lv.ko}</span>
        <span className="pn-when" title="1월 창 = 지금 공백(장기 부상·대체 안 된 이탈·뎁스 부족) · 여름 창 = 노쇠·계약 같은 승계 과제">{n.when}</span>
      </div>
      <div className="pn-bar" title={`시급도 ${n.urgency}/100`}><i style={{ width: `${n.urgency}%`, background: t.c }} /><b>{n.urgency}</b></div>
      <ul className="pn-why">{n.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
      {(w.out.length > 0 || w.in.length > 0) && (
        <div className="pn-win">
          <span className="pn-win-k">이번 창</span>
          {w.out.length > 0 && <span className="out">▼ {w.out.map((x) => x.player.split(" ").slice(-1)[0]).join(" · ")}</span>}
          {w.in.length > 0 && <span className="in">▲ {w.in.map((x) => x.player.split(" ").slice(-1)[0]).join(" · ")}</span>}
          {w.verdict && <em className={w.verdict === "대체 안 됨" ? "bad" : "ok"}>{w.verdict}</em>}
        </div>
      )}
      <div className="pn-depth">
        {n.depth.map((d) => (
          <button key={d.player} className={`pn-chip${d.kind === "secondary" ? " sec" : ""}${d.injured ? " hurt" : ""} peekable`}
            title={`${d.player} · OVR ${d.ovr}${d.kind === "secondary" ? " · 2·3포지션" : ""}${d.injured ? ` · 부상 ${d.until || ""}` : ""}${d.recent != null ? ` · LAST 5 폼 ${d.recent}` : ""}`}
            onClick={(e) => peek(e, { name: d.player, club: team, hint: { photo: d.photo, ovr: d.ovr } })}>
            {d.player.split(" ").slice(-1)[0]} <b style={{ color: tier(d.ovr).light }}>{d.ovr}</b>{d.injured ? <i>부상</i> : null}
          </button>
        ))}
        {n.depth.length === 0 && <span className="pn-none">이 자리 선수 없음</span>}
      </div>
    </div>
  );
}

export default function ScoutNeeds({ needs, team, accent }: { needs: Needs; team: string; accent: string }) {
  const roles = needs.positions ?? [];
  const hot = roles.filter((r) => r.urgency >= 15).slice(0, 6);
  const fine = roles.filter((r) => r.urgency < 15 && r.demand > 0);
  const p = needs.policy;
  return (
    <div className="scout-desk">
      <div className="scout-hd">
        <span className="scout-tag" style={{ color: accent }}>SCOUT DESK</span>
        <b>POSITION NEEDS</b>
        <span className="scout-d">포지션 니즈 — 부상(복귀 시점)·주전 LAST 5 폼·이번 창 이탈 대비 영입·나이·계약을 매일 다시 계산</span>
        {needs.team_ovr != null && <span className="scout-cnt">팀 OVR {needs.team_ovr} · 영입 {needs.window.signings.length} · 방출 {needs.window.departures.length}</span>}
      </div>
      {hot.length > 0 ? (
        <div className="pn-grid">{hot.map((n) => <RoleCard key={n.role} n={n} team={team} />)}</div>
      ) : <div className="mgr-meta">시급한 포지션 없음 ✓</div>}
      {fine.length > 0 && (
        <div className="pn-fine"><span>충분</span>{fine.map((r) => <em key={r.role} title={r.label}>{r.role}</em>)}</div>
      )}
      {p && (
        <div className="pn-policy">
          <div className="pn-policy-h"><b>TRANSFER POLICY</b><span>이적 정책 — 최근 두 시즌 영입 {p.n}명(임대 제외) · 추천 후보를 이 기준과 대조</span></div>
          <div className="pn-policy-row">
            {p.age_lo != null && <span><em>나이</em><b>{p.age_lo}~{p.age_hi}세</b><small>중앙 {p.age_med} · U23 {Math.round((p.u23_share ?? 0) * 100)}%</small></span>}
            {p.fee_med != null && <span><em>이적료</em><b>{fmtEur(p.fee_med)}</b><small>중앙 · 최고 {fmtEur(p.fee_max ?? 0)}</small></span>}
            <span><em>국내 영입</em><b>{Math.round(p.domestic_share * 100)}%</b><small>유료 {Math.round(p.paid_share * 100)}%</small></span>
            <span><em>출신 리그</em><b style={{ fontSize: 12.5 }}>{p.sources.map((s) => `${s.league} ${s.n}`).join(" · ")}</b></span>
          </div>
          {p.big.length > 0 && (
            <div className="pn-policy-big">최고 지출: {p.big.map((b) => `${b.player} ${fmtEur(b.fee)}${b.age ? ` (${b.age}세)` : ""}`).join(" · ")}</div>
          )}
        </div>
      )}
      <p className="pn-foot" style={{ borderColor: hexA(accent, 0.25) }}>
        아래 스카우팅 풀·드림 타깃은 위 시급 포지션 순서로 후보를 고르고, 경쟁 팀 핵심 주전은 '영입 가능성 낮음'으로 돌립니다.
      </p>
    </div>
  );
}
