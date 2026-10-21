"use client";
import { useEffect, useState } from "react";
import { getThisWeek, type ThisWeek as TW, type WeekAbsence } from "@/lib/api";
import MatchCard from "./MatchCard";
import Pitch from "./Pitch";
import SectionHead from "./SectionHead";
import Info from "./Info";
import { useOpenTeam, usePeek } from "./PlayerPeek";
import { Skel } from "./Skeleton";

// THIS WEEK — 감독용 한 블록(Overview 맨 위). 7일 안 경기(전 대회) · 양 팀 결장 · 결장 반영 예상 XI · 로테이션 부담 · A매치 차출.
// 예전 '다음 경기' 카드 자리. 예상 XI = 최근 3경기 최빈 선발에서 빠진 자리를 같은 세부 포지션 최고 OVR 로(src/this_week.py).
function AbsList({ items, team, empty }: { items: WeekAbsence[]; team: string; empty: string }) {
  const peek = usePeek();
  if (!items.length) return <p className="tw-empty">{empty}</p>;
  return (
    <ul className="tw-abs">
      {items.slice(0, 6).map((a) => (
        <li key={a.player} className="peekable" onClick={(e) => peek(e, { name: a.player, club: team })}>
          <b>{a.player}</b>{a.starter && <em className="tw-start" title="최근 3경기 최빈 선발">선발</em>}
          <span>{a.injury}{a.until ? ` · ${a.until.length === 10 ? a.until.slice(5).replace("-", "/") : a.until}` : ""}</span>
        </li>
      ))}
      {items.length > 6 && <li className="tw-more">외 {items.length - 6}명</li>}
    </ul>
  );
}

export default function ThisWeek({ team, accent }: { team: string; accent: string }) {
  const [d, setD] = useState<TW | null | undefined>(undefined);
  const openTeam = useOpenTeam();
  const peek = usePeek();
  useEffect(() => {
    let a = true; setD(undefined);
    getThisWeek(team).then((x) => a && setD(x)).catch(() => a && setD(null));
    return () => { a = false; };
  }, [team]);
  if (d === undefined) return <div className="card" style={{ marginTop: 16 }}><Skel h={26} w="30%" /><Skel h={180} r={12} /></div>;
  if (!d || (!d.week.length && !d.xi.placements.length)) return null;
  const go = (t: string, lg?: string | null) => { if (t !== team && lg && openTeam) openTeam(t, lg); };
  const n7 = d.week.filter((m) => (m.d_day ?? 99) <= 7).length;
  const opp = d.opponent;
  return (
    <div className="card tw" style={{ marginTop: 16 }}>
      <SectionHead title="THIS WEEK" kr="이번 주" meta={n7 ? `7일 ${n7}경기` : "다음 경기"}
        info={<>
          <p>7일 안 경기(리그·컵·유럽 전 대회). 경기를 누르면 프리뷰가 열립니다.</p>
          <p>7일 동안 3경기 이상이면 로테이션 경고를 띄웁니다.</p>
        </>} />
      {d.week.length > 0 && (
        <div className="next-match">
          <MatchCard m={d.week[0]} onPick={go} />
          {d.week.length > 1 && <div className="next-rest">{d.week.slice(1, 3).map((m, i) => <MatchCard key={i} m={m} onPick={go} compact />)}</div>}
        </div>
      )}
      {(n7 >= 3 || d.intl) && (
        <div className="tw-alerts">
          {n7 >= 3 && <span className="tw-alert warn">7일 동안 {n7}경기 — 로테이션 필요</span>}
          {d.intl && (
            <span className="tw-alert info" title={d.intl.players.join(", ")}>
              {d.intl.kind === "tournament" ? "대표팀 대회" : "A매치 기간"} D-{d.intl.days_to} · {d.intl.label} · 소집 {d.intl.n}명
              {d.intl.squad_state === "previous" ? "(지난 명단 기준)" : ""}
            </span>
          )}
        </div>
      )}
      <div className="tw-grid">
        <section className="tw-sec">
          <h3>ABSENCES <em>결장</em></h3>
          <div className="tw-abs-cols">
            <div><h4>{team} <span>{d.absences.length}명</span></h4><AbsList items={d.absences} team={team} empty="결장 없음" /></div>
            {opp && (
              <div>
                <h4>{opp.team} <span>{opp.covered ? `${opp.absences.length}명` : ""}</span></h4>
                {opp.covered ? <AbsList items={opp.absences} team={opp.team} empty="결장 없음" />
                  : <p className="tw-empty">결장 정보 없음
                    <Info label="결장 정보 없음 이유"><p>우리가 다루는 8개 리그 밖 팀이라 결장 정보를 모으지 않습니다.</p></Info></p>}
              </div>
            )}
          </div>
        </section>
        {d.xi.placements.length > 0 && (
          <section className="tw-sec tw-xi">
            <h3>PROJECTED XI <em>결장 반영 예상{d.xi.formation ? ` · ${d.xi.formation}` : ""}</em>
              <Info label="예상 XI 기준">
                <p><b>기준</b> = {d.xi.basis}.</p>
                <p>결장으로 빈 자리는 빠진 선수와 같은 세부 포지션 후보 중 OVR 이 가장 높은 선수로 채웁니다(없으면 같은 라인).</p>
              </Info></h3>
            <Pitch placements={d.xi.placements} accent={accent} team={team} />
            {d.xi.changes.length > 0 ? (
              <ul className="tw-changes">
                {d.xi.changes.map((c) => (
                  <li key={c.slot}><b>{c.slot}</b> {c.out} → {c.in ? <strong>{c.in}</strong> : <span className="tw-gap">대체 없음</span>}<em>{c.reason}</em></li>
                ))}
              </ul>
            ) : <p className="tw-note">결장 영향 없음</p>}
          </section>
        )}
        <section className="tw-sec">
          <h3>ROTATION LOAD <em>최근 14일 · {d.games14}경기</em>
            <Info label="로테이션 부담 기준">
              <p>최근 14일 출전 분(FotMob 경기별, 전 대회) 270′ 넘게 뛴 선수.</p>
              <p><b>빨강</b> = 360′ 초과 또는 4경기 연속 풀타임(85′+).</p>
            </Info></h3>
          {d.rotation.length ? (
            <ul className="tw-rot">
              {d.rotation.map((r) => (
                <li key={r.player} className={`peekable lv-${r.level}`} onClick={(e) => peek(e, { name: r.player, club: team })}
                  title={`최근 14일 ${r.minutes14}′ · 최근부터 연속 풀타임(85′+) ${r.full_streak}경기`}>
                  <b>{r.player}</b>
                  <span className="tw-bar"><i style={{ width: `${Math.min(100, (r.minutes14 / 450) * 100)}%` }} /></span>
                  <span>{r.minutes14}′{r.full_streak >= 2 ? ` · ${r.full_streak}연속 풀타임` : ""}</span>
                </li>
              ))}
            </ul>
          ) : <p className="tw-empty">270′ 넘게 뛴 선수 없음</p>}
        </section>
      </div>
    </div>
  );
}
