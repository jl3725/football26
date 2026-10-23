"use client";
import { useEffect, useState } from "react";
import { feeLabel, getTransfers, getRecommend, getNeeds, fmtEur, type Transfers, type TransferItem, type Recommend, type Needs } from "@/lib/api";
import { tier, roleClass, hexA } from "@/lib/ui";
import { TONE } from "@/lib/meaning";
import FitEvaluator from "./FitEvaluator";
import ManagerSimPanel from "./ManagerSimPanel";
import RecruitPool from "./RecruitPool";
import ScoutReport from "./ScoutReport";
import TransferWorkspace from "./TransferWorkspace";
import { useShortlist } from "@/lib/shortlist";
import ScoutNeeds from "./ScoutNeeds";
import Bar from "./Bar";
import { usePeek } from "./PlayerPeek";
import { SkelTab } from "./Skeleton";
import Info from "./Info";

const MODE: Record<string, { t: string; d: string }> = {
  evaluate: { t: "영입 평가 모드", d: "영입이 니즈를 메웠나" },
  gap: { t: "공백 분석 모드", d: "방출 공백 점검" },
  recruit: { t: "보강 후보 모드", d: "영입 없음 · 보강 방향" },
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
  const [fitInit, setFitInit] = useState<{ player: string; role: string } | null>(null);   // 작업대 FIT → 적합도 평가로
  const [report, setReport] = useState<{ player: string; club: string; league: string } | null>(null);
  const sl = useShortlist(team);
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
  const TM_BUCKET: Record<string, string> = Object.fromEntries(Object.entries(BUCKET_TM).map(([k, v]) => [v, k]));
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
        <FitEvaluator team={team} accent={accent} suggestions={suggestions} initial={fitInit} />
      ) : view === "sim" ? (
        <ManagerSimPanel team={team} accent={accent} />
      ) : (<>
      {/* ── SCOUT DESK ── 포지션 니즈 v2(있으면) · 없으면 예전 라인 단위 */}
      {needs && (needs.positions?.length ?? 0) > 0 && <ScoutNeeds needs={needs} team={team} accent={accent}
        onRole={(r) => setFocusRole(BUCKET_TM[r] ?? "")} />}
      {/* TRANSFER WORKSPACE — 니즈 바로 아래: 고정 후보 · 비교 · FIT · 리포트 · 예산 */}
      <TransferWorkspace team={team} accent={accent}
        onFit={(player, role) => { setFitInit({ player, role }); setView("fit"); }}
        onReport={(player, club, league) => setReport({ player, club, league })} />
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

      {/* 시즌·창 열림 여부는 상단 StatusBar 칩에 있다 — 여기는 아래 숫자의 범위만 짧게 */}
      <div className="season-note" style={{ marginTop: 0, marginBottom: 14 }}>
        {win?.is_open && data.window_has_data
          ? <b style={{ color: accent }}>{win.label} 창</b>
          : <><b>{data.data_season} 시즌</b>{win?.is_open ? " · 이번 창 이적 없음" : ""}</>}
      </div>
      {/* 순수지 = 지출 − 수입. 부호(+/−)만으로는 헷갈려서 '순지출'·'순수익' 단어로 쓴다 */}
      <div className="stat-strip" style={{ marginTop: 0 }}>
        <div className="stat"><div className="v" style={{ color: TONE.bad.c }}>{fmtEur(s.spend)}</div><div className="l">지출 (영입료)</div></div>
        <div className="stat"><div className="v" style={{ color: TONE.best.c }}>{fmtEur(s.income)}</div><div className="l">수입 (판매료)</div></div>
        <div className="stat" title={`지출 ${fmtEur(s.spend)} − 수입 ${fmtEur(s.income)} → ${net > 0 ? "쓴 돈이 번 돈보다 많음" : net < 0 ? "번 돈이 쓴 돈보다 많음" : "같음"}`}>
          <div className="v" style={{ color: net > 0 ? TONE.bad.c : net < 0 ? TONE.best.c : TONE.avg.c }}>{fmtEur(Math.abs(net))}</div>
          <div className="l">{net > 0 ? "순지출" : net < 0 ? "순수익" : "수지 균형"} <Info label="순지출 설명">
            <p><b>지출 − 수입</b> = {fmtEur(s.spend)} − {fmtEur(s.income)}</p>
            <p className="muted">순지출 = 쓴 돈이 번 돈보다 많음 · 순수익 = 번 돈이 쓴 돈보다 많음</p>
          </Info></div>
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
        <h3><Bar c={accent} />SCOUTING POOL <span className="rating-note">· 전 리그{focusRole ? ` · ${TM_BUCKET[focusRole] ?? focusRole}` : ""}</span>{" "}
          <Info label="SCOUTING POOL 설명" wide>
            <p>8개 리그에서 우리 팀 니즈 포지션에 맞는 후보를 찾습니다. 카드를 누르면 선수 요약, <b>☆</b>를 누르면 위 작업대에 고정됩니다.</p>
            <ul>
              <li><b>OVR</b> — 다른 리그 선수는 우리 리그 수준으로 보정한 예상값(아래 작은 숫자 = 현재 리그 OVR)</li>
              <li><b>스타일 유사도</b> — 우리 팀이 그 자리에 쓰는 플레이 스타일(현재 선수들 평균)과 닮은 정도 0~100</li>
              <li><b>정책 부합/밖</b> — 최근 두 시즌 영입 나이·이적료 기준과 대조</li>
              <li><b>라이벌</b> — 위키 라이벌·더비 구단 소속, 거래가 드뭅니다</li>
              <li><b>가능성 낮음</b> — 경쟁 팀·강팀의 핵심 주전</li>
              <li><b>계약 N개월</b> — 12개월 안 만료, 이적료가 싸거나 자유계약 가능</li>
              <li><b>링크</b> — 이 팀과 루머 연결 · <b>선례</b> — 그 리그에서 우리 리그로 온 이적 사례 수</li>
            </ul>
            <p className="muted">추천순 = 니즈 시급도·스타일·전력·가격 순, 가능성 낮음·정책 밖 후보는 뒤로.</p>
          </Info></h3>
        <RecruitPool team={team} accent={accent} focusRole={focusRole} />
      </div>

      {/* 드림 타깃 — 최상위급이나 티어·라이벌상 비현실 */}
      {rec && rec.longshots && rec.longshots.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3><Bar c={accent} />드림 타깃 <span className="rating-note">· 영입 가능성 낮음</span>{" "}
            <Info label="드림 타깃 설명">
              <p>최상위급이지만 구단 티어·라이벌 관계상 데려오기 어려운 후보입니다.</p>
              <p className="muted">현재 → 예상 = 다른 리그 선수의 지금 OVR을 우리 리그 수준으로 보정한 값. 스타일 적합 = 이 팀이 그 자리에 쓰는 스타일과의 유사도 0~100.</p>
            </Info></h3>
          <div className="rec-grid">
            {rec.longshots.map((l, i) => {
              const t = tier(l.ovr);
              return (
                <div className="rec-card longshot hoverable" key={i} style={{ cursor: "pointer" }}
                  onClick={(e) => peek(e, { name: l.player, club: l.squad, hint: { photo: l.photo, ovr: l.ovr, pos: l.pos, role: l.role } })}>
                  <button className={`sl-pin abs${sl.has(l.player, l.squad) ? " on" : ""}`} aria-pressed={sl.has(l.player, l.squad)}
                    title="이적 작업대 SHORTLIST 에 고정/빼기"
                    onClick={(e) => { e.stopPropagation(); sl.toggle({ player: l.player, club: l.squad, league: l.source_league || "" }); }}>{sl.has(l.player, l.squad) ? "★" : "☆"}</button>
                  {l.photo ? <img className="rec-photo" src={l.photo} alt="" /> : <span className="rec-photo ph" />}
                  <div className="rec-ovr" style={{ color: t.light }}
                    title={l.cross_league ? `현재 OVR ${l.current_ovr} (${l.source_league} 기준) → 우리 리그 기준 예상 ${l.ovr} · ${t.ko}` : `OVR ${l.ovr} · ${t.ko}`}>{l.ovr}</div>
                  <div className="rec-name">{l.player}</div>
                  <div className="rec-club">{l.logo && <img src={l.logo} alt="" />}{l.squad}</div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: t.light }}>{t.ko}</div>
                  {l.cross_league && l.current_ovr !== l.ovr && <div className="rec-cross" title={`${l.source_league} 현재 ${l.current_ovr} → 우리 리그 예상 ${l.ovr}`}>현재 {l.current_ovr} → {l.ovr}</div>}
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
      {report && <ScoutReport team={report.club} player={report.player} league={report.league || undefined} accent={accent} onClose={() => setReport(null)} />}
    </div>
  );
}
