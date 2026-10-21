"use client";
import { useEffect, useState } from "react";
import { fmtEur, type Needs, type PositionNeed } from "@/lib/api";
import { tier } from "@/lib/ui";
import { TONE } from "@/lib/meaning";
import { usePeek } from "./PlayerPeek";
import Info from "./Info";

// 스카우트 데스크 — 포지션 니즈 v2(api _position_needs)를 그림으로: 피치 위 포지션마다 시급도 점(색·크기),
// 누르면 그 포지션 근거를 아이콘 칩으로(뎁스 칸 · 이번 창 나감→영입 사진 · 부상 주 수 · 폼 · 나이·계약).
// 2026-10-19 사용자: '글이 너무 많다 — 시각적으로 직관적으로'. 문장은 툴팁(reasons)으로만 남긴다.
const LEVEL: Record<PositionNeed["level"], { ko: string; tone: keyof typeof TONE }> = {
  urgent: { ko: "시급", tone: "bad" }, need: { ko: "보강 필요", tone: "weak" }, watch: { ko: "관찰", tone: "avg" }, ok: { ko: "충분", tone: "good" },
};
// 피치 위 자리(%, 위 = 상대 골문)
const SPOT: Record<string, [number, number]> = {
  ST: [50, 13], LW: [17, 23], RW: [83, 23], AM: [50, 33], CM: [50, 47], DM: [50, 60],
  LB: [14, 70], CB: [50, 76], RB: [86, 70], GK: [50, 91],
};
const last = (n: string) => n.split(" ").slice(-1)[0];

function Face({ name, photo, mark, tone, sub }: { name: string; photo?: string; mark?: string; tone?: string; sub?: string }) {
  return (
    <span className="sn-face" title={name}>
      <span className="sn-face-img" style={tone ? { borderColor: tone } : undefined}>
        {photo ? <img src={photo} alt="" /> : <i>{name.split(" ").map((w) => w[0]).slice(0, 2).join("")}</i>}
        {mark && <em style={{ background: tone }}>{mark}</em>}
      </span>
      <span className="sn-face-n">{last(name)}</span>
      {sub && <span className="sn-face-s">{sub}</span>}
    </span>
  );
}

function Detail({ n, team }: { n: PositionNeed; team: string }) {
  const peek = usePeek();
  const lv = LEVEL[n.level];
  const t = TONE[lv.tone];
  const s = n.signals ?? { depth: { have: n.options, need: n.need_n } };
  const w = n.window;
  const cells = Math.max(s.depth.need, Math.ceil(s.depth.have));
  return (
    <div className="sn-detail" style={{ borderColor: t.c }}>
      <div className="sn-d-top">
        <b className="sn-d-role">{n.role}</b><span className="sn-d-label">{n.label}</span>
        <span className="sn-lv" style={{ color: t.c, background: t.bg }}>{lv.ko} {n.urgency}</span>
        <span className="sn-when" title="1월 창 = 지금 공백(장기 부상·대체 안 된 이탈·뎁스 부족) · 여름 창 = 노쇠·계약 같은 승계 과제">{n.when}</span>
      </div>

      <div className="sn-row" title={n.reasons.join("\n")}>
        <span className="sn-k">DEPTH</span>
        <span className="sn-cells">
          {Array.from({ length: cells }).map((_, i) => {
            const fill = Math.max(0, Math.min(1, s.depth.have - i));
            return <i key={i} className={i < s.depth.need ? "need" : "extra"}><b style={{ width: `${fill * 100}%`, background: fill ? (s.depth.have >= s.depth.need ? "#4fc27f" : t.c) : undefined }} /></i>;
          })}
        </span>
        <span className="sn-v">{s.depth.have}/{s.depth.need}</span>
      </div>

      {(w.out.length > 0 || w.in.length > 0) && (
        <div className="sn-row">
          <span className="sn-k">WINDOW</span>
          <span className="sn-moves">
            {w.out.map((x) => <Face key={"o" + x.player} name={x.player} photo={x.photo} mark="▼" tone="#e07070" />)}
            {w.out.length > 0 && w.in.length > 0 && <span className="sn-arrow">→</span>}
            {w.in.map((x) => <Face key={"i" + x.player} name={x.player} photo={x.photo} mark="▲" tone="#4fc27f" />)}
          </span>
          {w.verdict && <span className={`sn-chip ${w.verdict === "대체 안 됨" ? "bad" : "ok"}`}>{w.verdict}{s.unreplaced ? ` −${s.unreplaced}` : ""}</span>}
        </div>
      )}

      {s.injury && (
        <div className="sn-row">
          <span className="sn-k">INJURY</span>
          <span className="sn-moves">
            {s.injury.players.map((x) => <Face key={x.player} name={x.player} photo={x.photo} mark="✚" tone="#e07070" sub={`${Math.round(x.weeks)}주`} />)}
          </span>
          <span className="sn-chip bad" title="부상 때문에 이 자리 최선 조합의 평균 OVR 이 떨어진 정도">전력 −{Math.round(s.injury.drop)}</span>
        </div>
      )}

      {s.cold && (
        <div className="sn-row">
          <span className="sn-k">FORM</span>
          <span className="sn-moves">
            {s.cold.map((x) => <Face key={x.player} name={x.player} photo={x.photo} mark="↓" tone="#e0a53a" sub={`LAST 5 ${x.recent}`} />)}
          </span>
        </div>
      )}

      {(s.aging || s.contract) && (
        <div className="sn-row">
          <span className="sn-k">FUTURE</span>
          <span className="sn-tags">
            {s.aging?.map((x) => <span key={"a" + x.player} className="sn-chip">{last(x.player)} {x.age}세</span>)}
            {s.contract?.map((x) => <span key={"c" + x.player} className="sn-chip">{last(x.player)} 계약 ~{x.until}</span>)}
          </span>
        </div>
      )}

      <div className="sn-row sn-depth">
        <span className="sn-k">SQUAD</span>
        <span className="sn-tags">
          {n.depth.map((d) => (
            <button key={d.player} className={`sn-p${d.kind === "secondary" ? " sec" : ""}${d.injured ? " hurt" : ""} peekable`}
              title={`${d.player} · OVR ${d.ovr}${d.kind === "secondary" ? " · 2·3포지션" : ""}${d.injured ? ` · 부상 ${d.until || ""}` : ""}${d.recent != null ? ` · LAST 5 ${d.recent}` : ""}`}
              onClick={(e) => peek(e, { name: d.player, club: team, hint: { photo: d.photo, ovr: d.ovr } })}>
              {last(d.player)} <b style={{ color: tier(d.ovr).light }}>{d.ovr}</b>{d.injured ? <i>✚</i> : null}
            </button>
          ))}
          {n.depth.length === 0 && <span className="sn-none">이 자리 선수 없음</span>}
        </span>
      </div>
    </div>
  );
}

export default function ScoutNeeds({ needs, team, accent, onRole }: {
  needs: Needs; team: string; accent: string; onRole?: (role: string) => void;   // 고른 포지션 → 아래 스카우팅 풀 필터
}) {
  const roles = needs.positions ?? [];
  const byRole = Object.fromEntries(roles.map((r) => [r.role, r]));
  const top = roles[0]?.role ?? "";
  const [sel, setSelRaw] = useState(top);
  useEffect(() => { setSelRaw(top); }, [team, top]);
  const setSel = (r: string) => { setSelRaw(r); onRole?.(r); };
  const cur = byRole[sel] ?? roles[0];
  const hot = roles.filter((r) => r.urgency >= 15);
  const p = needs.policy;
  return (
    <div className="scout-desk">
      <div className="scout-hd">
        <span className="scout-tag" style={{ color: accent }}>SCOUT DESK</span>
        <b>POSITION NEEDS</b>
        <span className="scout-d">점을 누르면 근거 <Info label="POSITION NEEDS 설명">
          <p>포지션마다 시급도를 <b>매일 다시 계산</b>합니다.</p>
          <ul>
            <li>뎁스 — 이 자리에 쓸 수 있는 선수 수</li>
            <li>부상 — 결장 주 수와 이 자리 전력 하락</li>
            <li>이번 창 — 나간 선수가 영입으로 대체됐는지</li>
            <li>폼(LAST 5) · 나이 · 계약 만료</li>
          </ul>
          <p className="muted">1월 창 = 지금 공백(장기 부상·대체 안 된 이탈·뎁스 부족) · 여름 창 = 노쇠·계약 같은 승계 과제.</p>
        </Info></span>
        {needs.team_ovr != null && <span className="scout-cnt">팀 OVR {needs.team_ovr} · 영입 {needs.window.signings.length} · 방출 {needs.window.departures.length}</span>}
      </div>
      <div className="sn-grid">
        <div className="sn-pitch" role="list" aria-label="포지션별 시급도">
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="sn-lines" aria-hidden="true">
            <rect x="3" y="3" width="94" height="94" rx="2" /><line x1="3" y1="50" x2="97" y2="50" /><circle cx="50" cy="50" r="10" />
            <rect x="28" y="3" width="44" height="13" /><rect x="28" y="84" width="44" height="13" />
          </svg>
          {Object.entries(SPOT).map(([role, [x, y]]) => {
            const r = byRole[role];
            if (!r) return null;
            const t = TONE[LEVEL[r.level].tone];
            const size = 30 + Math.min(18, r.urgency / 5);
            return (
              <button key={role} role="listitem" className={`sn-dot${sel === role ? " on" : ""}${r.urgency < 15 ? " quiet" : ""}`}
                style={{ left: `${x}%`, top: `${y}%`, width: size, height: size, background: r.urgency >= 15 ? t.c : "rgba(79,194,127,0.18)", borderColor: t.c }}
                title={`${r.label} · ${LEVEL[r.level].ko} ${r.urgency}`} onClick={() => setSel(role)}>
                <b>{role}</b>{r.urgency >= 15 && <em>{r.urgency}</em>}
              </button>
            );
          })}
        </div>
        <div className="sn-side">
          {hot.length > 0 && (
            <div className="sn-rank">
              {hot.map((r) => {
                const t = TONE[LEVEL[r.level].tone];
                return (
                  <button key={r.role} className={sel === r.role ? "on" : ""} onClick={() => setSel(r.role)} style={sel === r.role ? { borderColor: t.c } : undefined}>
                    <i style={{ background: t.c }} />{r.role}<em>{LEVEL[r.level].ko}</em><b>{r.urgency}</b>
                  </button>
                );
              })}
            </div>
          )}
          {cur && <Detail n={cur} team={team} />}
        </div>
      </div>
      {p && (
        <div className="pn-policy">
          <div className="pn-policy-h"><b>TRANSFER POLICY</b><span>최근 2시즌 영입 {p.n}명 <Info label="TRANSFER POLICY 설명"><p>이 구단이 최근 두 시즌에 영입한 선수들의 나이·이적료·출신 리그입니다.</p><p className="muted">추천 후보를 이 기준과 대조해 '정책 부합/밖'을 표시합니다.</p></Info></span></div>
          <div className="pn-policy-row">
            {p.age_lo != null && <span><em>나이</em><b>{p.age_lo}~{p.age_hi}세</b><small>U23 {Math.round((p.u23_share ?? 0) * 100)}%</small></span>}
            {p.fee_med != null && <span><em>이적료</em><b>{fmtEur(p.fee_med)}</b><small>최고 {fmtEur(p.fee_max ?? 0)}</small></span>}
            <span><em>국내 영입</em><b>{Math.round(p.domestic_share * 100)}%</b><small>유료 {Math.round(p.paid_share * 100)}%</small></span>
            <span><em>출신 리그</em><b style={{ fontSize: 12.5 }}>{p.sources.slice(0, 3).map((s) => `${s.league} ${s.n}`).join(" · ")}</b></span>
          </div>
        </div>
      )}
    </div>
  );
}
