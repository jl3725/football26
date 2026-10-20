"use client";
import { useEffect, useState } from "react";
import { feeLabel, getTransfers, getRecommend, getNeeds, fmtEur, type Transfers, type TransferItem, type Recommend, type Needs } from "@/lib/api";
import { tier, roleClass, hexA } from "@/lib/ui";
import { TONE } from "@/lib/meaning";
import FitEvaluator from "./FitEvaluator";
import ManagerSimPanel from "./ManagerSimPanel";
import RecruitPool from "./RecruitPool";
import ScoutNeeds from "./ScoutNeeds";
import Bar from "./Bar";
import { usePeek } from "./PlayerPeek";
import { SkelTab } from "./Skeleton";

const MODE: Record<string, { t: string; d: string }> = {
  evaluate: { t: "영입 평가 모드", d: "이번 창 영입이 각 니즈를 얼마나 해소했는지 점검" },
  gap: { t: "공백 분석 모드", d: "방출로 생긴 공백·대체 필요 포지션 점검" },
  recruit: { t: "보강 후보 모드", d: "이번 창 영입 없음 · 니즈 기반 보강 방향" },
};

function Row({ x, dir, team }: { x: TransferItem; dir: "in" | "out"; team: string }) {
  const peek = usePeek();
  return (
    <div className={`tf2-row ${dir} peekable`}
      onClick={(e) => peek(e, { name: x.player, club: dir === "in" ? team : x.club, hint: { photo: x.photo, pos: x.pos, age: x.age, nationality: x.nat } })}>
      {x.photo ? <img className="tf2-photo" src={x.photo} alt="" /> : <span className="tf2-photo ph" />}
      <div className="tf2-info">
        <div className="tf2-name">{x.player}</div>
        <div className="tf2-meta">{x.pos || "-"} · {x.age || "?"}세 · {dir === "in" ? "from" : "to"} {x.club || "-"}</div>
      </div>
      <span className="tf2-fee">{feeLabel(x.fee_eur, x.fee_text)}</span>
    </div>
  );
}

export default function TransferTab({ team, accent }: { team: string; accent: string }) {
  const [data, setData] = useState<Transfers | null>(null);
  const [rec, setRec] = useState<Recommend | null>(null);
  const [needs, setNeeds] = useState<Needs | null>(null);
  const [view, setView] = useState<"scout" | "fit" | "sim">("scout");
  const [focusRole, setFocusRole] = useState<string | undefined>(undefined);   // 니즈 피치에서 고른 포지션(TM 표기)
  useEffect(() => {
    let a = true; setData(null); setRec(null); setNeeds(null);
    getTransfers(team).then((d) => a && setData(d)).catch(() => {});
    getRecommend(team).then((d) => a && setRec(d)).catch(() => {});
    getNeeds(team).then((d) => a && setNeeds(d)).catch(() => {});
    return () => { a = false; };
  }, [team]);
  const peek = usePeek();
  if (!data) return <SkelTab />;
  const s = data.summary;
  const net = s.net;

  const win = data.window;
  const mode = needs ? (MODE[needs.mode] || MODE.recruit) : null;
  const POSD: Record<string, string> = {
    CB: "Centre-Back", RB: "Right-Back", LB: "Left-Back", RWB: "Right-Back", LWB: "Left-Back",
    DM: "Defensive Midfield", CM: "Central Midfield", AM: "Attacking Midfield", RM: "Right Midfield",
    LM: "Left Midfield", RW: "Right Winger", LW: "Left Winger", CF: "Centre-Forward", SS: "Second Striker", GK: "Goalkeeper",
  };
  // 추천 후보의 평가 포지션 = 그 선수가 추천된 니즈 포지션(bucket). 예전엔 r.pos(대분류 'MF' 등)에서 뽑아 엇나갔다
  const BUCKET_TM: Record<string, string> = { GK: "Goalkeeper", LB: "Left-Back", CB: "Centre-Back", RB: "Right-Back",
    DM: "Defensive Midfield", CM: "Central Midfield", AM: "Attacking Midfield", LW: "Left Winger", RW: "Right Winger", ST: "Centre-Forward" };
  const suggestions = (rec?.recommendations || []).map((r) => ({
    player: r.player, role: BUCKET_TM[r.bucket || ""] || POSD[(r.pos || "").split(/[ ,/]/)[0]] || "",
  }));
  return (
    <div className="fade">
      {/* 서브탭 토글 */}
      <div style={{ display: "inline-flex", gap: 2, marginBottom: 16, padding: 3, borderRadius: 10,
        background: hexA("#ffffff", 0.05), border: `1px solid ${hexA(accent, 0.15)}` }}>
        {([["scout", "스카우트 데스크"], ["fit", "적합도 평가"], ["sim", "감독 시뮬레이션"]] as const).map(([v, label]) => (
          <button key={v} onClick={() => setView(v)}
            style={{ padding: "7px 16px", borderRadius: 7, fontSize: 12.5, fontWeight: 600, cursor: "pointer",
              border: "none", letterSpacing: 0.2, transition: "all .15s",
              background: view === v ? accent : "transparent",
              color: view === v ? "#0a0a0a" : "inherit", opacity: view === v ? 1 : 0.6 }}>{label}</button>
        ))}
      </div>

      {view === "fit" ? (
        <FitEvaluator team={team} accent={accent} suggestions={suggestions} />
      ) : view === "sim" ? (
        <ManagerSimPanel team={team} accent={accent} />
      ) : (<>
      {/* ── SCOUT DESK ── 포지션 니즈 v2(있으면) · 없으면 예전 라인 단위 */}
      {needs && (needs.positions?.length ?? 0) > 0 && <ScoutNeeds needs={needs} team={team} accent={accent}
        onRole={(r) => setFocusRole(BUCKET_TM[r] ?? "")} />}
      {needs && !(needs.positions?.length) && (
        <div className="scout-desk">
          <div className="scout-hd">
            <span className="scout-tag" style={{ color: accent }}>SCOUT DESK</span>
            <b>{mode?.t}</b>
            <span className="scout-d">{mode?.d}</span>
            <span className="scout-cnt">영입 {needs.window.signings.length} · 방출 {needs.window.departures.length}</span>
          </div>
          {needs.needs.length > 0 ? (
            <div className="need-grid">
              {needs.needs.map((n, i) => (
                <div className={`need-card st-${n.status}`} key={i}>
                  <div className="need-top">
                    <span className="need-line">{n.line_label}</span>
                    <span className="need-title">{n.title}</span>
                    <span className={`need-sev ${n.severity}`}>{n.severity === "high" ? "높음" : n.severity === "med" ? "중간" : "낮음"}</span>
                  </div>
                  <div className="need-reason">{n.reason}</div>
                  {n.status === "addressed" && <div className="need-status ok">✅ {n.player} 영입으로 보강</div>}
                  {n.status === "worsened" && <div className="need-status bad">⚠ {n.player} 방출로 공백</div>}
                </div>
              ))}
            </div>
          ) : <div className="mgr-meta">감지된 주요 니즈 없음 ✓</div>}
        </div>
      )}

      <div className="season-note" style={{ marginTop: 0, marginBottom: 14 }}>
        {win?.is_open
          ? <><b style={{ color: accent }}>{win.label} {win.kr} 이적시장 OPEN</b>{!data.window_has_data && " · 이번 창 이적 없음 (전체 표시)"}</>
          : <><b>{data.data_season} 시즌</b> · 현재 이적시장 마감</>}
      </div>
      {/* 순수지 = 지출 − 수입. 부호(+/−)만으로는 헷갈려서 '순지출'·'순수익' 단어로 쓴다 */}
      <div className="stat-strip" style={{ marginTop: 0 }}>
        <div className="stat"><div className="v" style={{ color: TONE.bad.c }}>{fmtEur(s.spend)}</div><div className="l">지출 (영입료)</div></div>
        <div className="stat"><div className="v" style={{ color: TONE.best.c }}>{fmtEur(s.income)}</div><div className="l">수입 (판매료)</div></div>
        <div className="stat" title={`지출 ${fmtEur(s.spend)} − 수입 ${fmtEur(s.income)} → ${net > 0 ? "쓴 돈이 번 돈보다 많음" : net < 0 ? "번 돈이 쓴 돈보다 많음" : "같음"}`}>
          <div className="v" style={{ color: net > 0 ? TONE.bad.c : net < 0 ? TONE.best.c : TONE.avg.c }}>{fmtEur(Math.abs(net))}</div>
          <div className="l">{net > 0 ? "순지출 · 지출 > 수입" : net < 0 ? "순수익 · 수입 > 지출" : "수지 균형"}</div>
        </div>
        <div className="stat"><div className="v" style={{ color: accent }}>{s.in_count}/{s.out_count}</div><div className="l">영입 / 방출 (명)</div></div>
      </div>

      <div className="grid" style={{ marginTop: 16 }}>
        <div className="card">
          <h3 style={{ color: TONE.best.c }}>▲ 영입 · IN ({data.in.length})</h3>
          <div className="tf2-list">
            {data.in.map((x, i) => <Row key={i} x={x} dir="in" team={team} />)}
            {data.in.length === 0 && <div className="mgr-meta">영입 없음</div>}
          </div>
        </div>
        <div className="card">
          <h3 style={{ color: TONE.bad.c }}>▼ 방출 · OUT ({data.out.length})</h3>
          <div className="tf2-list">
            {data.out.map((x, i) => <Row key={i} x={x} dir="out" team={team} />)}
            {data.out.length === 0 && <div className="mgr-meta">방출 없음</div>}
          </div>
        </div>
      </div>

      {/* 포지션별 보강 후보 — 벡터 스타일-핏 + 필터/KPI/정렬 (RecruitPool) */}
      <div className="card" style={{ marginTop: 16, scrollMarginTop: 12 }} id="recruit-pool">
        <h3><Bar c={accent} />SCOUTING POOL <span className="rating-note">· 스카우팅 풀 · 전 리그{focusRole ? ` · ${focusRole}` : ""}</span></h3>
        <RecruitPool team={team} accent={accent} focusRole={focusRole} />
      </div>

      {/* 드림 타깃 — 최상위급이나 티어·라이벌상 비현실 */}
      {rec && rec.longshots && rec.longshots.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3><Bar c={accent} />드림 타깃 <span className="rating-note">· 영입 가능성 낮음</span></h3>
          <div className="rec-grid">
            {rec.longshots.map((l, i) => {
              const t = tier(l.ovr);
              return (
                <div className="rec-card longshot hoverable" key={i} style={{ cursor: "pointer" }}
                  onClick={(e) => peek(e, { name: l.player, club: l.squad, hint: { photo: l.photo, ovr: l.ovr, pos: l.pos, role: l.role } })}>
                  {l.photo ? <img className="rec-photo" src={l.photo} alt="" /> : <span className="rec-photo ph" />}
                  <div className="rec-ovr" style={{ color: t.light }}
                    title={l.cross_league ? `현재 OVR ${l.current_ovr} (${l.source_league} 기준) → 우리 리그 기준 예상 ${l.ovr} · ${t.ko}` : `OVR ${l.ovr} · ${t.ko}`}>{l.ovr}</div>
                  <div className="rec-name">{l.player}</div>
                  <div className="rec-club">{l.logo && <img src={l.logo} alt="" />}{l.squad}</div>
                  <div style={{ fontSize: 9.5, fontWeight: 700, color: t.light }}>{t.ko}</div>
                  {l.cross_league && <div className="rec-cross" title="다른 리그 선수 — 우리 리그 수준으로 보정한 예상 OVR">{l.source_league} 현재 {l.current_ovr} → 우리 리그 예상 {l.ovr}</div>}
                  {l.bucket_label && <div className="rec-target" style={{ color: accent }}>◎ {l.bucket_label}</div>}
                  {l.style_fit != null && <div className="rec-style" title="이 팀이 그 자리에 쓰는 플레이 스타일(현재 선수들 평균)과의 유사도 0~100">스타일 적합 <b>{l.style_fit}</b></div>}
                  {l.role && <div className="rec-role"><span className={"role-tag " + roleClass(l.role)}>{l.role}</span></div>}
                  <div className="rec-why"><span className="why risk">✕ {l.reason}</span></div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Lost Target Review */}
      {rec && rec.lost_targets && rec.lost_targets.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3><Bar c={accent} />놓친 타깃 <span className="rating-note">· 타팀 이적</span></h3>
          <div className="tf2-list">
            {rec.lost_targets.map((l, i) => (
              <div className={`tf2-row${l.top_loss ? " top-loss" : ""} peekable`} key={i}
                onClick={(e) => peek(e, { name: l.player, club: l.to, hint: { photo: l.photo, ovr: l.ovr, pos: l.pos, role: l.role } })}>
                {l.photo ? <img className="tf2-photo" src={l.photo} alt="" /> : <span className="tf2-photo ph" />}
                <div className="tf2-info">
                  <div className="tf2-name">{l.top_loss && <span title="가장 아까운 이탈">⭐ </span>}{l.player} <span className="lt-ovr" title={`OVR ${l.ovr} · ${tier(l.ovr).ko}`}>OVR <b style={{ color: tier(l.ovr).light }}>{l.ovr}</b> · {tier(l.ovr).ko}</span>
                    {l.role && <span className={"role-tag sm " + roleClass(l.role)}>{l.role}</span>}</div>
                  <div className="tf2-meta">{l.pos} · {l.from} → <b style={{ color: "#e07070" }}>{l.to}</b></div>
                </div>
                <span className="tf2-fee" style={{ color: "#e07070" }}>{l.top_loss ? "최대 손실" : "이적 완료"}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      </>)}
    </div>
  );
}
