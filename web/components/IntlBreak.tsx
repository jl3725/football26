"use client";
import { useEffect, useState } from "react";
import { getIntlTeam, type IntlFixture, type IntlTeam } from "@/lib/api";
import { TONE } from "@/lib/meaning";
import { usePeek } from "./PlayerPeek";
import Info from "./Info";

// INTERNATIONAL BREAK — 다음(진행 중) A매치 기간과 우리 팀 소집 선수·대표팀 경기(설계도 2단계).
// 원천: src/fetch_intl.py(ESPN 국가대표 경기 → 기간, 대표팀 위키 'Current squad' → 소집 명단) → /api/intl/team.
// 새 명단 발표 전에는 지난 기간 명단을 '예상'으로 보여 주고 그렇게 적는다. 유럽 밖 대표팀(FIFA 대륙)은 장거리 이동 표시.

const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const COMP: Record<string, string> = {
  "uefa.nations": "네이션스리그", "fifa.friendly": "친선", "concacaf.nations.league": "CONCACAF NL", "caf.nations_qual": "AFCON 예선",
  "afc.asian.cup": "아시안컵", "caf.nations": "AFCON", "uefa.euroq": "유로 예선", "conmebol.america": "코파",
};

function Fx({ f }: { f: IntlFixture }) {
  return (
    <span className="ib-fx" title={COMP[f.comp] ?? f.comp}>
      {md(f.date)} {f.home ? "vs" : "@"} {f.opp}{f.score && <b> {f.score}</b>}
    </span>
  );
}

export default function IntlBreak({ team }: { team: string }) {
  const [d, setD] = useState<IntlTeam | null>(null);
  const peek = usePeek();
  useEffect(() => { let a = true; setD(null); getIntlTeam(team).then((x) => a && setD(x)).catch(() => {}); return () => { a = false; }; }, [team]);
  if (!d || !d.window) return null;
  const w = d.window;
  const when = d.state === "now" ? "진행 중" : d.days_to != null ? `D-${d.days_to}` : "";
  return (
    <div className="card ib-card">
      <div className="ib-head">
        <h3>{w.kind === "tournament" ? "INTERNATIONAL TOURNAMENT" : "INTERNATIONAL BREAK"}<small>{w.label}</small></h3>
        <span className="ib-when">{md(w.start)} – {md(w.end)}{when && <em>{when}</em>}</span>
      </div>
      {d.players.length === 0 ? (
        <p className="ib-note">소집 기록이 있는 선수가 없습니다.</p>
      ) : (
        <>
          <p className="ib-note">
            {d.squad_state === "announced" ? "소집 명단" : "예상 명단"}
            {" · "}<b>{d.summary.n}명</b> · {d.summary.nations}개국
            {d.summary.far > 0 && <> · <b style={{ color: TONE.weak.c }}>유럽 밖 {d.summary.far}명</b></>}
            <Info label="소집 명단 기준">
              <p>{d.squad_state === "announced" ? "이번 기간 발표된 소집 명단입니다." : `새 명단 발표 전 — 지난 기간(${d.last_window ? `${md(d.last_window.first_match)}–${md(d.last_window.end)}` : ""}) 명단으로 예상합니다.`}</p>
              {d.summary.far > 0 && <p>유럽 밖 = 장거리 이동 — 복귀 후 첫 경기 체력 변수.</p>}
              {w.kind === "tournament" && <p>대회 기간 클럽 경기는 결장으로 예측에 반영합니다.</p>}
            </Info>
          </p>
          <div className="ib-list">
            {d.players.map((p) => (
              <div className="ib-row" key={p.player}>
                {p.flag ? <img className="ib-flag" src={p.flag} alt="" /> : <span className="ib-flag" />}
                <div className="ib-main">
                  <div className="ib-top">
                    <span className="ib-name peekable" onClick={(e) => peek(e, { name: p.player, club: team })}>{p.player}</span>
                    <span className="ib-nat">{p.nation}{p.caps != null && <> · A매치 {p.caps}경기{p.goals ? ` ${p.goals}골` : ""}</>}</span>
                    {p.far && <span className="ib-far" style={{ color: TONE.weak.c, background: TONE.weak.bg }}>유럽 밖</span>}
                  </div>
                  {p.fixtures.length > 0 && <div className="ib-fxs">{p.fixtures.map((f, i) => <Fx key={i} f={f} />)}</div>}
                  {p.last_results.length > 0 && (
                    <div className="ib-fxs ib-last"><span className="ib-k">지난</span>{p.last_results.map((f, i) => <Fx key={i} f={f} />)}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
