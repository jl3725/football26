"use client";
import { useEffect, useMemo, useState } from "react";
import { fmtEur, fmtEurRange, getWorkspace, type Workspace, type WorkspacePick } from "@/lib/api";
import { tier } from "@/lib/ui";
import { useShortlist } from "@/lib/shortlist";
import { TrackLine } from "./Tracking";
import SectionHead from "./SectionHead";
import Info from "./Info";
import { usePeek } from "./PlayerPeek";
import { Skel } from "./Skeleton";

// TRANSFER WORKSPACE — 니즈 → 후보(스카우팅 풀 ☆) → SHORTLIST → 2~3명 비교·FIT·리포트 → 예산 시나리오.
// 고정 목록은 이 브라우저에(팀별), 숫자는 열 때마다 서버가 다시 계산(/api/workspace) — 옛 숫자가 남지 않게.
const PRICE: Record<string, [string, string]> = {
  within: ["예산 안", "#4fc27f"], stretch: ["무리", "#e0a53a"], "over-budget": ["예산 초과", "#ff6b6b"], unknown: ["-", "var(--muted)"],
};
const CONTRACT: Record<string, string> = { expiring: "만료 임박", short: "2년 안", long: "장기", unknown: "-" };
const MAX_CMP = 3;

type Row = { label: string; get: (p: WorkspacePick) => string; num?: (p: WorkspacePick) => number | null; best?: "max" | "min" };
const ROWS: Row[] = [
  { label: "예상 OVR", get: (p) => `${p.ovr ?? "-"}${p.cross_league && p.current_ovr ? ` (현재 ${p.current_ovr})` : ""}`, num: (p) => p.ovr ?? null, best: "max" },
  { label: "나이", get: (p) => (p.age ? `${p.age}세` : "-"), num: (p) => p.age ?? null, best: "min" },
  { label: "포지션", get: (p) => p.tm_position || p.pos || "-" },
  { label: "시장가", get: (p) => (p.value_eur ? fmtEur(p.value_eur) : "-") },
  { label: "적정 이적료", get: (p) => (p.fair ? fmtEurRange(p.fair.lo, p.fair.hi) : p.likely_fee_eur ? fmtEur(p.likely_fee_eur) : "-"), num: (p) => p.likely_fee_eur ?? null, best: "min" },
  { label: "가격", get: (p) => PRICE[p.price_verdict ?? "unknown"]?.[0] ?? "-" },
  { label: "계약", get: (p) => (p.contract_until ? `${p.contract_until.slice(0, 7)} · ${p.months_left}개월` : "-"), num: (p) => p.months_left ?? null, best: "min" },
  { label: "리그 출전", get: (p) => `${(p.minutes ?? 0).toLocaleString()}′`, num: (p) => p.minutes ?? null, best: "max" },
  { label: "골·도움", get: (p) => `${p.goals ?? 0} · ${p.assists ?? 0}`, num: (p) => (p.goals ?? 0) + (p.assists ?? 0), best: "max" },
  { label: "평점", get: (p) => (p.rating ? p.rating.toFixed(2) : "-"), num: (p) => p.rating ?? null, best: "max" },
  { label: "구단 정책", get: (p) => (p.policy_ok === true ? "부합" : p.policy_ok === false ? `밖 · ${(p.policy_notes ?? []).join(", ")}` : "-") },
  { label: "영입 가능성", get: (p) => (p.rival ? "낮음 · 라이벌" : p.realistic === false ? "낮음 · 핵심 주전" : "보통") },
];

export default function TransferWorkspace({ team, accent, onFit, onReport }: {
  team: string; accent: string;
  onFit: (player: string, role: string) => void;
  onReport: (player: string, club: string, league: string) => void;
}) {
  const sl = useShortlist(team);
  const [w, setW] = useState<Workspace | null>(null);
  const [cmp, setCmp] = useState<string[]>([]);
  const peek = usePeek();
  const sig = sl.items.map((x) => `${x.player}|${x.club}`).join(";");
  useEffect(() => {
    let a = true;
    getWorkspace(team, sl.items.map(({ player, club, league }) => ({ player, club, league })))
      .then((x) => a && setW(x)).catch(() => a && setW(null));
    return () => { a = false; };
  }, [team, sig]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setCmp((c) => c.filter((k) => sl.items.some((x) => `${x.player}|${x.club}` === k))); }, [sig]); // eslint-disable-line react-hooks/exhaustive-deps

  const picks = w?.shortlist ?? [];
  const keyOf = (p: WorkspacePick) => `${p.player}|${p.club}`;
  // 고정할 때의 클럽 표기로 찾는다 — 서버가 최신 소속으로 바꿔 줄 수 있어(이적) 순서로 짝짓는다
  const rows = sl.items.map((it, i) => ({ it, p: picks[i] }));
  const chosen = rows.filter((r) => cmp.includes(`${r.it.player}|${r.it.club}`) && r.p?.found).map((r) => r.p!);
  const pool = chosen.length ? chosen : picks.filter((p) => p.found);
  const fees = pool.reduce((s, p) => s + (p.likely_fee_eur ?? 0), 0);
  const ratio = w?.avg_spend ? fees / w.avg_spend : null;
  const bestOf = useMemo(() => {
    const out: Record<string, string> = {};
    for (const r of ROWS) {
      if (!r.num || !r.best || chosen.length < 2) continue;
      const vals = chosen.map((p) => ({ k: keyOf(p), v: r.num!(p) })).filter((x) => x.v != null) as { k: string; v: number }[];
      if (vals.length < 2) continue;
      const b = r.best === "max" ? Math.max(...vals.map((x) => x.v)) : Math.min(...vals.map((x) => x.v));
      out[r.label] = vals.filter((x) => x.v === b).map((x) => x.k).join(";");
    }
    return out;
  }, [chosen]);

  const toggleCmp = (k: string) => setCmp((c) => (c.includes(k) ? c.filter((x) => x !== k) : c.length >= MAX_CMP ? c : [...c, k]));
  return (
    <div className="card tws">
      <SectionHead title="TRANSFER WORKSPACE" kr="이적 작업대"
        info={<>
          <p><b>쓰는 순서</b></p>
          <ul>
            <li>니즈 확인 → 아래 스카우팅 풀에서 ☆로 후보 고정</li>
            <li>2~3명을 '비교'로 골라 나란히 보기 · FIT 평가 · 리포트</li>
            <li>적정 이적료(가운데) 합을 창 평균 지출과 비교(예산 시나리오) — 적정 이적료 = 시장가치 × 사는 리그·나이 배수(지난 이적에서 배움)</li>
          </ul>
          <p className="muted">고정 목록은 이 브라우저에 팀별로 저장되고, 숫자는 열 때마다 새로 계산합니다.</p>
        </>} />
      {/* 예산 시나리오 */}
      {w ? (
        <div className="tws-budget">
          {w.windows.map((x) => (
            <span key={x.label} className="tws-chip" title={`영입 ${x.n_in}명 · 방출 ${x.n_out}명 · 수입 ${fmtEur(x.income)}`}>{x.label} 지출 <b>{x.spend ? fmtEur(x.spend) : "€0"}</b></span>
          ))}
          {w.avg_spend != null && <span className="tws-chip">창 평균 <b>{fmtEur(w.avg_spend)}</b></span>}
          {w.ceiling_eur ? <span className="tws-chip" title="구단 지출 규모로 본 한 선수 이적료 상한(근사)">한 명 상한 <b>{fmtEur(w.ceiling_eur)}</b></span> : null}
          {w.policy?.age_med != null && <span className="tws-chip" title="최근 두 시즌 영입 기준">영입 나이 중앙 <b>{w.policy.age_med}세</b>{w.policy.fee_med ? <> · 이적료 중앙 <b>{fmtEur(w.policy.fee_med)}</b></> : null}</span>}
          {w.rivals.length > 0 && <span className="tws-chip muted" title="위키 라이벌·더비(같은 리그) — 이 구단 선수는 거래가 드물다">라이벌 {w.rivals.join(" · ")}</span>}
        </div>
      ) : <Skel h={30} r={8} />}
      {sl.items.length === 0 ? (
        <p className="tws-empty">아래 후보의 <b>☆</b>로 고정하세요</p>
      ) : (
        <>
          {pool.length > 0 && w?.avg_spend ? (
            <div className="tws-sum">
              <span>{chosen.length ? `비교 중 ${chosen.length}명` : `고정 ${pool.length}명`} 적정 이적료 합 <b>{fmtEur(fees)}</b> · 창 평균 지출의 <b style={{ color: ratio! > 1.2 ? "#ff6b6b" : ratio! > 0.8 ? "#e0a53a" : "#4fc27f" }}>{Math.round(ratio! * 100)}%</b></span>
              <span className="tws-bar"><i style={{ width: `${Math.min(100, (ratio ?? 0) * 100)}%`, background: ratio! > 1.2 ? "#ff6b6b" : ratio! > 0.8 ? "#e0a53a" : "#4fc27f" }} /></span>
            </div>
          ) : null}
          <div className="tws-list">
            {rows.map(({ it, p }) => {
              const k = `${it.player}|${it.club}`;
              if (!p) return <div key={k} className="tws-card"><Skel h={70} r={10} /></div>;
              if (!p.found) return (
                <div key={k} className="tws-card miss">
                  <b>{it.player}</b><span title="리그 밖 이적·이름 변경 등으로 지금 데이터에서 찾지 못함">{it.club} · 데이터 없음</span>
                  {/* 리그 밖으로 이적한 후보(Martinelli → Al-Hilal)는 TRACKING 이 '이적 완료'로 알려 준다 */}
                  <TrackLine team={team} player={it.player} club={it.club} accent={accent} />
                  <button className="tws-x" onClick={() => sl.remove(it.player, it.club)} aria-label="빼기">✕</button>
                </div>
              );
              const t = tier(p.ovr ?? 0);
              const on = cmp.includes(k);
              return (
                <div key={k} className={`tws-card${on ? " on" : ""}`} style={on ? { borderColor: accent } : undefined}>
                  <div className="tws-top peekable" onClick={(e) => peek(e, { name: p.player, club: p.club, league: p.league, hint: { photo: p.photo, ovr: p.current_ovr, age: p.age ?? undefined } })}>
                    {p.photo ? <img src={p.photo} alt="" /> : <span className="tws-ph" />}
                    <div className="tws-id">
                      <b>{p.player}</b>
                      <span>{p.logo ? <img src={p.logo} alt="" /> : null}{p.club} · {p.age ?? "?"}세 · {p.tm_position || p.pos}</span>
                    </div>
                    <div className="tws-ovr" style={{ color: t.light }} title={p.cross_league ? `현재 ${p.current_ovr} → 우리 리그 예상 ${p.ovr}` : `OVR ${p.ovr}`}>{p.ovr}</div>
                  </div>
                  <div className="tws-facts">
                    <span title={p.fair ? `적정 이적료 가운데 ${fmtEur(p.fair.mid)} — 시장가치 × 사는 리그·나이 배수` : undefined}>적정 <b>{p.fair ? fmtEurRange(p.fair.lo, p.fair.hi) : p.likely_fee_eur ? fmtEur(p.likely_fee_eur) : "-"}</b> <em style={{ color: PRICE[p.price_verdict ?? "unknown"]?.[1] }}>{PRICE[p.price_verdict ?? "unknown"]?.[0]}</em></span>
                    <span>계약 <b className={p.contract_status === "expiring" ? "good" : ""}>{p.months_left != null ? `${p.months_left}개월` : "-"}</b> <em>{CONTRACT[p.contract_status ?? "unknown"]}</em></span>
                  </div>
                  <TrackLine team={team} player={p.player} club={p.club} accent={accent} />
                  <div className="tws-tags">
                    {p.rival && <span className="bad">라이벌</span>}
                    {!p.rival && p.realistic === false && <span className="bad">가능성 낮음</span>}
                    {p.policy_ok === true && <span className="good">정책 부합</span>}
                    {p.policy_ok === false && <span className="warn" title={(p.policy_notes ?? []).join(" · ")}>정책 밖</span>}
                    {p.cross_league && <span>{p.league}</span>}
                  </div>
                  <div className="tws-actions">
                    <label><input type="checkbox" checked={on} disabled={!on && cmp.length >= MAX_CMP} onChange={() => toggleCmp(k)} />비교</label>
                    <button onClick={() => onFit(p.player, p.tm_position || "")} title="이 선수의 우리 팀 적합도(FIT) 평가로">FIT</button>
                    <button onClick={() => onReport(p.player, p.club, p.league)} title="스카우팅 리포트 한 장">리포트</button>
                    <button className="tws-x" onClick={() => sl.remove(it.player, it.club)} aria-label="빼기" title="SHORTLIST 에서 빼기">✕</button>
                  </div>
                </div>
              );
            })}
          </div>
          {chosen.length >= 2 && (
            <div className="tws-cmp-wrap">
              <table className="tws-cmp">
                <thead><tr><th>COMPARE</th>{chosen.map((p) => <th key={keyOf(p)}>{p.player}<em>{p.club}</em></th>)}</tr></thead>
                <tbody>
                  {ROWS.map((r) => (
                    <tr key={r.label}><td>{r.label}</td>{chosen.map((p) => (
                      <td key={keyOf(p)} className={(bestOf[r.label] ?? "").split(";").includes(keyOf(p)) ? "best" : ""}>{r.get(p)}</td>
                    ))}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {chosen.length >= 2 && <p className="tws-note">초록 = 가장 좋은 값 <Info label="비교표 색 설명">
            <p>초록은 그 줄에서 가장 좋은 값입니다.</p>
            <p className="muted">이적료·나이·계약은 낮을수록 좋게 봅니다 — 계약이 짧으면 살 때 협상이 유리합니다.</p>
          </Info></p>}
          {chosen.length < 2 && sl.items.length >= 2 && <p className="tws-note">2~3명 '비교' 선택</p>}
        </>
      )}
    </div>
  );
}
