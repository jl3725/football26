"use client";
import { Fragment, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { fmtEur, getScoutReport, type ScoutMetric, type ScoutReport as Report } from "@/lib/api";
import { tier } from "@/lib/ui";
import { pctMeaning } from "@/lib/meaning";
import { RecentStrip } from "./FormPair";
import Radar from "./Radar";
import { Skel, SkelRows } from "./Skeleton";

// SCOUT REPORT — 선수 한 명을 한 장으로(판단 문장·강약점·폼·가용성·계약·가치·이적설·대안). 인쇄 → PDF 로 저장.
// 판단 문장은 서버 규칙(src/scout_report.py)이 원자료 숫자로 만든다 — 손으로 쓴 평 없음.
const RISK: Record<string, [string, string, string]> = {
  low: ["LOW", "양호", "#4fc27f"], mid: ["MID", "보통", "#e0a53a"], high: ["HIGH", "주의", "#ff6b6b"],
};
const STAGE: Record<string, [string, string]> = {
  interest: ["INTEREST", "관심"], talks: ["TALKS", "협상"], agreed: ["AGREED", "합의"], done: ["DONE", "확정"], denied: ["DENIED", "부인"],
};
const CONTRACT: Record<string, string> = { expiring: "만료 임박", short: "2년 안 만료", long: "장기 계약", unknown: "정보 없음" };
const pctTxt = (x: number) => `${Math.round(x * 100)}%`;
const ym = (d?: string | null) => (d ? d.slice(0, 7).replace("-", ".") : "-");

function MetricRows({ items, tone }: { items: ScoutMetric[]; tone: "up" | "down" }) {
  if (!items.length) return <p className="sr-empty">{tone === "up" ? "상위 30% 안에 드는 지표가 없습니다." : "하위 30% 안에 드는 지표가 없습니다."}</p>;
  return (
    <div className="sr-metrics">
      {items.map((m) => {
        const mm = pctMeaning(m.pct);
        return (
          <div className="sr-metric" key={`${m.cat}-${m.label}`} title={`${m.cat} · ${m.label} — 같은 포지션 백분위 ${Math.round(m.pct)}`}>
            <span className="sr-metric-l">{m.label}<em>{m.cat}</em></span>
            <span className="sr-metric-bar"><i style={{ width: `${Math.max(3, m.pct)}%`, background: mm.c }} /></span>
            <b style={{ color: mm.c }}>{Math.round(m.pct)}</b>
            <span className="sr-metric-raw">{m.raw != null ? (Math.abs(m.raw) < 10 ? m.raw.toFixed(2) : Math.round(m.raw)) : ""}</span>
          </div>
        );
      })}
    </div>
  );
}

function ValueSpark({ pts, color }: { pts: { date: string; value_eur: number }[]; color: string }) {
  const vals = pts.map((p) => p.value_eur), mn = Math.min(...vals), mx = Math.max(...vals), rng = mx - mn || 1;
  if (pts.length < 2 || mx === mn) return null;          // 값이 하나뿐이면 평평한 줄만 남는다
  const w = 160, h = 36;
  const line = pts.map((p, i) => `${(i / (pts.length - 1)) * w},${h - ((p.value_eur - mn) / rng) * (h - 6) - 3}`).join(" ");
  return (
    <svg className="sr-spark" viewBox={`0 0 ${w} ${h}`} width={w} height={h} role="img" aria-label="시장가치 추이">
      <polyline points={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function ScoutReport({ team, player, accent, onClose, league }: { team: string; player: string; accent: string; onClose: () => void;
  league?: string }) {   // league — 다른 리그 선수(이적 작업대 후보)면 그 리그
  const [r, setR] = useState<Report | null>(null);
  const [err, setErr] = useState(false);
  const [host, setHost] = useState<HTMLElement | null>(null);
  useEffect(() => { setHost(document.body); }, []);     // body 바로 아래에 — 사이드바 위로, 인쇄 때 앱 화면만 숨기기 쉽게
  useEffect(() => {
    let a = true; setR(null); setErr(false);
    (league ? getScoutReport(team, player, league) : getScoutReport(team, player)).then((x) => a && setR(x)).catch(() => a && setErr(true));
    return () => { a = false; };
  }, [team, player, league]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [onClose]);

  const d = r?.player;
  const t = d ? tier(d.ovr) : null;
  const risk = r ? RISK[r.availability.risk] : null;
  if (!host) return null;
  return createPortal(
    <div className="sr-overlay" role="dialog" aria-modal="true" aria-label={`${player} 스카우팅 리포트`}>
      <div className="sr-bar">
        <span className="sr-bar-t">SCOUT REPORT <em>스카우팅 리포트</em></span>
        <span className="sr-bar-a">
          <button onClick={() => window.print()} disabled={!r} title="브라우저 인쇄 창에서 'PDF로 저장'을 고르면 파일로 남습니다">인쇄 · PDF</button>
          <button onClick={onClose} aria-label="닫기">닫기 ✕</button>
        </span>
      </div>
      {err && <p className="sr-empty" style={{ padding: 24 }}>리포트를 만들지 못했습니다. 잠시 뒤 다시 열어 주세요.</p>}
      {!r && !err && <div className="sr-page"><Skel h={110} r={14} /><SkelRows n={8} /></div>}
      {r && d && t && risk && (
        <article className="sr-page">
          <header className="sr-head" style={{ borderColor: accent }}>
            {d.photo ? <img className="sr-photo" src={d.photo} alt="" /> : <span className="sr-photo ph" />}
            <div className="sr-id">
              <h1>{d.player}</h1>
              <p>{[d.team, d.pos, d.age > 0 ? `${d.age}세` : "", d.nationality].filter(Boolean).join(" · ")}</p>
              <p>{[d.comp_usage?.role, d.joined ? `입단 ${ym(d.joined)}` : "", r.contract.until ? `계약 ~${ym(r.contract.until)}` : ""].filter(Boolean).join(" · ")}</p>
            </div>
            <div className="sr-ovr" style={{ color: t.light, borderColor: t.light }}>
              <b>{d.ovr}</b><span>OVR</span><em>{t.ko}</em>
            </div>
          </header>

          <section className="sr-sec sr-verdict">
            <h2>VERDICT <em>판단 요약</em></h2>
            <ul>{r.verdict.map((v, i) => <li key={i}>{v}</li>)}</ul>
          </section>

          {r.enough ? (
            <div className="sr-cols">
              <section className="sr-sec"><h2>STRENGTHS <em>강점 · 같은 포지션 백분위</em></h2><MetricRows items={r.strengths} tone="up" /></section>
              <section className="sr-sec"><h2>WEAKNESSES <em>약점</em></h2><MetricRows items={r.weaknesses} tone="down" /></section>
            </div>
          ) : (
            <p className="sr-note">리그 출전 {d.minutes.toLocaleString()}′ — 백분위 강약점은 {d.is_gk ? 300 : 450}′ 넘게 뛴 뒤 나옵니다.</p>
          )}

          <div className="sr-cols three">
            {r.enough && d.radar?.length > 0 && (
              <section className="sr-sec sr-radar"><h2>PROFILE <em>{d.template ? `${d.template.ko} 템플릿 · ${d.template.scope === "리그" ? "같은 리그" : "8개 리그"} ${d.template.n}명` : "능력 모양"}</em></h2><Radar data={d.radar} color={accent} scale="pct" /></section>
            )}
            <section className="sr-sec">
              <h2>SEASON <em>이번 시즌</em></h2>
              <dl className="sr-kv">
                <dt>리그</dt><dd>{d.minutes.toLocaleString()}′ · {d.goals}골 {d.assists}도움</dd>
                {d.season_log?.available && d.season_log.by_comp.length > 1 && (
                  <><dt>전 대회</dt><dd>{d.season_log.total.minutes.toLocaleString()}′ · {d.season_log.total.goals}골 {d.season_log.total.assists}도움</dd></>
                )}
                {d.ratings && d.ss_rating > 0 && <><dt>평점</dt><dd>{d.ss_rating.toFixed(2)}</dd></>}
                {d.badges?.slice(0, 2).map((b, i) => <Fragment key={i}><dt>순위</dt><dd>{b.label} {b.scope ?? "리그"} #{b.rank}</dd></Fragment>)}
              </dl>
            </section>
            <section className="sr-sec">
              <h2>FORM <em>최근 폼</em></h2>
              {d.recent && d.recent.matches.length > 0 ? (
                <>
                  <RecentStrip matches={d.recent.matches} />
                  <p className="sr-cap">최근 {d.recent.n}경기 평점 평균 <b>{d.recent.avg5.toFixed(2)}</b>{d.form != null && d.recent.score != null ? ` · 폼 ${Math.round(d.recent.score)} (시즌 ${Math.round(d.form)})` : ""}</p>
                </>
              ) : <p className="sr-empty">최근 경기 평점이 없습니다.</p>}
            </section>
          </div>

          <div className="sr-cols">
            <section className="sr-sec">
              <h2>AVAILABILITY <em>가용성</em> <span className="sr-pill" style={{ color: risk[2], borderColor: risk[2] }}>{risk[0]} {risk[1]}</span></h2>
              {r.availability.current && (
                <p className="sr-alert">지금 결장 — {r.availability.current.injury}{r.availability.current.until ? ` · 복귀 예상 ${r.availability.current.until}` : ""}</p>
              )}
              {r.availability.seasons.length ? (
                <table className="sr-table">
                  <thead><tr><th>시즌</th><th>결장</th><th>일수</th><th>부상</th></tr></thead>
                  <tbody>{r.availability.seasons.map((s) => (
                    <tr key={s.season}><td>{s.season}</td><td>{s.games_missed}경기</td><td>{s.days_out}일</td>
                      <td className="l">{s.spells ? `${s.spells}회 · ${s.injuries.slice(0, 2).join(", ")}` : "없음"}</td></tr>
                  ))}</tbody>
                </table>
              ) : <p className="sr-empty">부상 기록이 없습니다.</p>}
            </section>
            <section className="sr-sec">
              <h2>CONTRACT · VALUE <em>계약·시장가치</em></h2>
              <dl className="sr-kv">
                <dt>계약</dt><dd>{r.contract.until ? `${ym(r.contract.until)}까지 · ${r.contract.months_left}개월` : "정보 없음"} <span className={`sr-tag c-${r.contract.status}`}>{CONTRACT[r.contract.status]}</span></dd>
                <dt>가치</dt><dd>{fmtEur(r.market.value_eur)}{r.market.change_12m_pct ? <span className={r.market.change_12m_pct > 0 ? "up" : "down"}> {r.market.change_12m_pct > 0 ? "▲" : "▼"}{Math.abs(r.market.change_12m_pct)}% (1년)</span> : null}</dd>
                {r.market.peak_eur > r.market.value_eur && <><dt>최고</dt><dd>{fmtEur(r.market.peak_eur)}</dd></>}
              </dl>
              <ValueSpark pts={d.value_history ?? []} color={accent} />
            </section>
          </div>

          <section className="sr-sec">
            <h2>TRANSFER TALK <em>이적설 · TM 루머 + 뉴스 단계</em></h2>
            {r.talk.length ? (
              <table className="sr-table">
                <thead><tr><th>날짜</th><th className="l">행선지</th><th>단계</th><th className="l">출처</th></tr></thead>
                <tbody>{r.talk.map((x, i) => {
                  const sr = x.stage ? r.stage_rates[x.stage] : undefined;
                  return (
                    <tr key={i} title={x.headline || undefined}>
                      <td>{x.date.slice(5).replace("-", "/")}</td>
                      <td className="l"><b>{x.to_club}</b></td>
                      <td>{x.stage ? <span title={sr ? `지난 시장에서 이 단계 보도의 ${pctTxt(sr.rate)}가 실제 성사(${sr.hits}/${sr.n})` : undefined}>{STAGE[x.stage]?.[1] ?? x.stage}{sr && x.stage !== "denied" ? ` · 성사 ${pctTxt(sr.rate)}` : ""}</span> : x.probability ? `${x.probability}%` : "루머"}</td>
                      <td className="l">{x.source}{x.outlet_rate != null ? <em> · 적중 {pctTxt(x.outlet_rate)}</em> : null}</td>
                    </tr>
                  );
                })}</tbody>
              </table>
            ) : <p className="sr-empty">최근 120일 이적설이 없습니다.</p>}
          </section>

          {r.similar.length > 0 && (
            <section className="sr-sec">
              <h2>ALTERNATIVES <em>스타일 유사 선수 · 가치가 70% 미만이면 '더 쌈'</em></h2>
              <table className="sr-table">
                <thead><tr><th className="l">선수</th><th className="l">클럽</th><th>나이</th><th>가치</th><th>유사도</th></tr></thead>
                <tbody>{r.similar.map((s) => (
                  <tr key={`${s.player}-${s.squad}`}>
                    <td className="l"><b>{s.player}</b>{s.cheaper && <span className="sr-tag c-cheap">더 쌈</span>}</td>
                    <td className="l">{s.squad}</td><td>{s.age || "-"}</td><td>{fmtEur(s.value_eur)}</td><td>{s.score}%</td>
                  </tr>
                ))}</tbody>
              </table>
            </section>
          )}

          {r.news.length > 0 && (
            <section className="sr-sec">
              <h2>IN THE NEWS <em>최근 기사</em></h2>
              <ul className="sr-news">{r.news.map((n) => (
                <li key={n.link}><a href={n.link} target="_blank" rel="noreferrer">{n.headline}</a><span>{n.source} · {n.published?.slice(0, 10)}</span></li>
              ))}</ul>
            </section>
          )}

          <footer className="sr-foot">
            {r.generated} 생성 · 백분위 = 리그 경기, 같은 포지션 비교 · 출처: FBref·Sofascore·FotMob·Transfermarkt·뉴스(Google News 포함) · SCOUT.AI
          </footer>
        </article>
      )}
    </div>
  , host);
}
