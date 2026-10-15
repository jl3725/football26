"use client";
import type { LeagueLab } from "@/lib/api";
import SectionHead from "./SectionHead";
import { Skel } from "./Skeleton";
import { FormBoxes } from "./MatchCard";
import { TitleRace, GoldenBoot, TeamOfSeason, OverUnder, InjuryImpact } from "./HubPulse";
import { ExpectedBoard, Playmakers, BallWinners, TeamStyleMap } from "./LeagueLab";
import { lgEn } from "@/lib/match";
import { liveLabel, useLiveAll } from "@/lib/live";
import { liveTable, type LiveTableRow } from "@/lib/liveTable";
import { TONE, ovrMeaning } from "@/lib/meaning";

// 리그 집중 묶음 — 글로벌 대시보드(리그 선택)와 각 리그 탭(full: 전체 순위표·전력 대비·부상 타격 추가)이 함께 쓴다.
// 데이터는 /api/league-lab/{league} 하나(6시간 캐시).
type Pick = (team: string, league?: string) => void;

// 진행 중·방금 끝난 경기 표시 — 'LIVE 67' 2-1' / 'FT 2-1'(그 팀 기준 득실)
function LiveChip({ t }: { t: LiveTableRow }) {
  if (!t.live) return null;
  const { state, label, gf, ga, res } = t.live;
  return <span className={`lv5 ${state} ${res}`} title={state === "in" ? "진행 중 — 지금 끝나면 기준" : "종료 — 공식 반영 전"}>{state === "in" && <i className="live-dot" />}{label} {gf}-{ga}</span>;
}
function Move({ t }: { t: LiveTableRow }) {
  if (!t.move) return null;
  return <span className={`lv5-mv ${t.move > 0 ? "up" : "down"}`}>{t.move > 0 ? "▲" : "▼"}{Math.abs(t.move)}</span>;
}
function LiveNote({ inPlay }: { inPlay: boolean }) {
  return <p className="lv5-note"><i className="live-dot" />{inPlay ? "LIVE 순위 — 진행 중 경기를 지금 스코어로 반영" : "잠정 순위 — 방금 끝난 경기 반영"} · 공식 순위는 매일 08:15 갱신</p>;
}

function StandingsMini({ lab, league, onPick }: { lab: LeagueLab; league: string; onPick: Pick }) {
  const lt = liveTable(lab.table, lab.pending, useLiveAll(), liveLabel);
  const rows = lt.rows.slice(0, 6);
  const top = rows[0]?.points || 1;
  return (
    <div className="st5">
      {lt.on && <LiveNote inPlay={lt.inPlay} />}
      {rows.map((t) => (
        <button className={`st5-row${t.live ? " is-live" : ""}`} key={t.team} onClick={() => onPick(t.team, league)}>
          <span className="st5-rk">{t.rank}</span>
          {t.logo ? <img src={t.logo} alt="" /> : <span className="st5-ph" />}
          <span className={`st5-nm${t.live || t.move ? " has-live" : ""}`}><span className="st5-nm-t">{t.team}</span><Move t={t} /><LiveChip t={t} /></span>
          <span className="st5-bar"><span style={{ width: `${Math.max(4, (t.points / top) * 100)}%` }} /></span>
          <span className="st5-gap">{t.rank === 1 ? "—" : top - t.points ? `-${top - t.points}` : "0"}</span>
          <b className="st5-pts">{t.points}</b>
        </button>
      ))}
    </div>
  );
}

// 전체 순위표 — 경기·승무패·득실·승점·최근 5경기·경기당 xG·전력 순위(OVR)·감독
function StandingsFull({ lab, league, onPick }: { lab: LeagueLab; league: string; onPick: Pick }) {
  const lt = liveTable(lab.table, lab.pending, useLiveAll(), liveLabel);
  const rows = lt.rows;
  const n = rows.length;
  // 경기당 xG 리그 평균 — 숫자만으로는 1.42 가 많은지 적은지 안 읽혀 평균 대비 색(±10%)으로 보인다
  const xgs = rows.map((t) => t.xg_pg).filter((v): v is number => v != null);
  const xgAvg = xgs.length ? xgs.reduce((a, b) => a + b, 0) / xgs.length : null;
  const xgColor = (v: number | null | undefined) =>
    v == null || !xgAvg ? undefined : v >= xgAvg * 1.1 ? TONE.good.c : v <= xgAvg * 0.9 ? TONE.weak.c : undefined;
  return (
    <div className="tb5-wrap">
      {lt.on && <LiveNote inPlay={lt.inPlay} />}
      <table className="tb5">
        <thead>
          <tr>
            <th>#</th><th className="l">TEAM</th><th>P</th><th className="s">W</th><th className="s">D</th><th className="s">L</th><th className="m">GF</th><th className="m">GA</th>
            <th>GD</th><th>PTS</th><th className="m">FORM</th><th className="m" title={`경기당 기대 득점${xgAvg ? ` · 리그 평균 ${xgAvg.toFixed(2)}` : ""}`}>xG/G</th><th className="m" title="팀 전력(OVR) 순위">OVR</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => {
            const gap = t.str_rank ? t.str_rank - t.rank : 0;
            return (
              <tr key={t.team} onClick={() => onPick(t.team, league)} className={[t.rank === 1 ? "lead" : t.rank > n - 3 ? "rel" : "", t.live ? "is-live" : ""].join(" ").trim()}>
                <td className="rk">{t.rank}<Move t={t} /></td>
                <td className="l"><span className="tb5-team">{t.logo ? <img src={t.logo} alt="" /> : <i />}<b>{t.team}</b><LiveChip t={t} />{t.manager && <em>{t.manager}</em>}</span></td>
                <td>{t.played}</td><td className="s">{t.won}</td><td className="s">{t.drawn}</td><td className="s">{t.lost}</td>
                <td className="m">{t.gf}</td><td className="m">{t.ga}</td>
                <td className={t.gd > 0 ? "up" : t.gd < 0 ? "down" : ""}>{t.gd > 0 ? `+${t.gd}` : t.gd}</td>
                <td className="pts">{t.points}</td>
                <td className="m"><FormBoxes form={t.form} /></td>
                <td className="m" style={{ color: xgColor(t.xg_pg) }}
                  title={t.xg_pg != null && xgAvg ? `경기당 기대 득점 ${t.xg_pg.toFixed(2)} · 리그 평균 ${xgAvg.toFixed(2)}` : undefined}>
                  {t.xg_pg != null ? t.xg_pg.toFixed(2) : "—"}
                </td>
                <td className="m" title={[t.ovr != null ? `팀 OVR ${t.ovr} · ${ovrMeaning(t.ovr).label}` : "", t.str_rank ? `전력 ${t.str_rank}위 · 순위 ${t.rank}위` : ""].filter(Boolean).join(" · ")}>
                  {t.ovr ?? "—"}{gap ? <span className={`tb5-gap ${gap > 0 ? "up" : "down"}`}>{gap > 0 ? "▲" : "▼"}{Math.abs(gap)}</span> : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="tb5-note">
        OVR 옆 ▲▼ = 팀 전력 순위보다 실제 순위가 높음/낮음 · 아래 3팀 = 강등권 표시
        {xgAvg ? <> · xG/G 리그 평균 {xgAvg.toFixed(2)} — <span style={{ color: TONE.good.c }}>평균보다 높음</span> / <span style={{ color: TONE.weak.c }}>낮음</span>(±10%)</> : null}
      </p>
    </div>
  );
}

export default function LeagueFocus({ league, lab, onPick, full = false }: { league: string; lab: LeagueLab | null; onPick: Pick; full?: boolean }) {
  const L = lab;
  const wait = (h: number) => <Skel h={h} r={12} />;
  const race = L?.race ?? [];
  return (
    <div className="h5-stack">
      {full && (
        <section className="card h5-card">
          <SectionHead title="STANDINGS" kr="전체 순위표" meta={`${lgEn(league)} · 득실 · 최근 5경기 · 경기당 xG · 전력 순위`} />
          {L ? <StandingsFull lab={L} league={league} onPick={onPick} /> : wait(420)}
        </section>
      )}
      <div className="h5-row">
        <section className="card h5-card">
          <SectionHead title="TITLE RACE" kr="우승 경쟁" meta="상위 4팀 누적 승점" />
          {!L ? wait(220) : race.length ? <TitleRace teams={race} league={league} onPick={onPick} /> : <p className="empty5">경기 기록 없음</p>}
        </section>
        <section className="card h5-card h5-side">
          {full ? (
            <>
              <SectionHead title="OVER / UNDER" kr="전력 대비 성적" meta="팀 OVR 순위 vs 실제 순위" />
              {L ? <OverUnder over={L.over ?? []} under={L.under ?? []} onPick={onPick} /> : wait(260)}
            </>
          ) : (
            <>
              <SectionHead title="STANDINGS" kr="리그 순위" meta="1위와 승점 차" />
              {L ? <StandingsMini lab={L} league={league} onPick={onPick} /> : wait(260)}
            </>
          )}
        </section>
      </div>
      <div className="h5-row">
        <section className="card h5-card">
          <SectionHead title="TEAM OF THE SEASON" kr={`${lgEn(league)} 시즌 베스트 XI`} meta="자리별 시즌 평균 평점 1위 · 팀 경기 절반 이상 출전" />
          {!L ? wait(380) : (L.tots ?? []).length ? <TeamOfSeason players={L.tots!} league={league} /> : <p className="empty5">출전 기록이 아직 부족합니다</p>}
        </section>
        <section className="card h5-card h5-side">
          <SectionHead title="GOLDEN BOOT" kr="득점왕 레이스" meta="골 · xG · 골당 출전 시간" />
          {L ? <GoldenBoot rows={L.golden_boot ?? []} onPick={onPick} /> : wait(300)}
        </section>
      </div>
      <div className="h5-row">
        <section className="card h5-card">
          <SectionHead title="EXPECTED vs ACTUAL" kr="기대값 대비 결과" meta="골 vs xG · 도움 vs xA · 점을 누르면 선수" />
          {L ? <ExpectedBoard finishing={L.finishing} creating={L.creating} league={league} /> : wait(280)}
        </section>
        <section className="card h5-card h5-side">
          <SectionHead title="PLAYMAKERS" kr="도움왕 · 찬스 메이커" meta="도움 · xA · 빅찬스 · 키패스" />
          {L ? <Playmakers rows={L.playmakers} onPick={onPick} league={league} /> : wait(280)}
        </section>
      </div>
      <div className="h5-row">
        <section className="card h5-card">
          <SectionHead title="TEAM STYLE MAP" kr="팀 스타일 지도" meta="경기당 xG vs 경기당 실점 · 점선 = 리그 평균" />
          {L ? <TeamStyleMap teams={L.team_style} onPick={onPick} league={league} /> : wait(300)}
        </section>
        <section className="card h5-card h5-side">
          <SectionHead title="BALL WINNERS" kr="볼 위닝" meta="90분당 수비 액션" />
          {L ? <BallWinners rows={L.ball_winners} league={league} /> : wait(280)}
        </section>
      </div>
      {full && (L?.injury_impact ?? []).length > 0 && (
        <section className="card h5-card">
          <SectionHead title="INJURY IMPACT" kr="부상 타격" meta="부상자 때문에 줄어든 베스트 XI 평균 전력(팀 OVR)" />
          <InjuryImpact rows={L!.injury_impact!} onPick={onPick} />
        </section>
      )}
    </div>
  );
}
