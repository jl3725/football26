"use client";
import { useEffect, useState, type ReactNode } from "react";
import { getWC, getWCSquad, type WorldCupData, type WCSquad } from "@/lib/api";

function WSec({ en, kr, accent, right }: { en: string; kr: string; accent: string; right?: ReactNode }) {
  return (
    <div className="sec-head">
      <span className="sec-bar" style={{ background: accent }} />
      <div className="sec-txt"><div className="sec-en">{en}</div><div className="sec-kr">{kr}</div></div>
      {right && <div className="sec-right">{right}</div>}
    </div>
  );
}

function Score({ s }: { s: number | null }) {
  return <span className="wc-sc">{s === null ? "-" : s}</span>;
}

export default function WorldCup({ accent, onPickTeam }: { accent: string; onPickTeam: (t: string) => void }) {
  const [d, setD] = useState<WorldCupData | null>(null);
  const [nation, setNation] = useState<string | null>(null);
  const [squad, setSquad] = useState<WCSquad | null>(null);

  useEffect(() => { let a = true; getWC().then((x) => a && setD(x)).catch(() => {}); return () => { a = false; }; }, []);
  useEffect(() => {
    if (!nation) { setSquad(null); return; }
    let a = true; setSquad(null);
    getWCSquad(nation).then((x) => a && setSquad(x)).catch(() => {});
    return () => { a = false; };
  }, [nation]);

  if (!d) return <div className="loading">월드컵 데이터 불러오는 중…</div>;
  const knockout = d.matches.filter((r) => r.round !== "group-stage");

  return (
    <div className="fade home">
      {/* HERO */}
      <div className="hx wc-hx" style={{ ["--tc" as any]: accent }}>
        <div className="hx-glow" style={{ background: "radial-gradient(60% 120% at 85% 0%, #d4af3755, transparent 70%)" }} />
        <div className="hx-kicker" style={{ color: "#e8c86a" }}>FIFA WORLD CUP · 2026</div>
        <h1 className="hx-title">WORLD CUP 2026</h1>
        <div className="hx-meta">북중미 공동 개최 · 48개국 · <span style={{ color: "#e8c86a" }}>녹아웃 스테이지 진행 중</span></div>
      </div>

      {/* 우리 클럽의 월드컵 — EPL 차출 */}
      {d.epl_clubs.length > 0 && (
        <>
          <WSec en="CLUB WATCH" kr="우리 클럽의 월드컵" accent={accent}
            right={<span className="sec-count">{d.epl_clubs.reduce((a, c) => a + c.count, 0)}</span>} />
          <div className="wc-clubs">
            {d.epl_clubs.map((c) => (
              <div className="wc-club" key={c.club}>
                <button className="wc-club-h" onClick={() => onPickTeam(c.club)}>
                  {c.logo && <img src={c.logo} alt="" />}
                  <span className="wc-club-name">{c.club}</span>
                  <span className="wc-club-n" style={{ color: accent }}>{c.count}</span>
                </button>
                <div className="wc-club-players">
                  {c.players.slice(0, 6).map((p, i) => (
                    <div className="wc-pl" key={i} title={`${p.player} · ${p.nation}`}>
                      {p.photo ? <img src={p.photo} alt="" /> : <span className="wc-pl-ph" />}
                      <span className="wc-pl-nm">{p.player.split(" ").slice(-1)[0]}</span>
                      {p.goals > 0 && <span className="wc-pl-g">⚽{p.goals}</span>}
                    </div>
                  ))}
                  {c.players.length > 6 && <span className="wc-pl-more">+{c.players.length - 6}</span>}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* 득점왕 */}
      <WSec en="GOLDEN BOOT" kr="득점왕" accent={accent} />
      <div className="card">
        <div className="wc-scorers">
          {d.scorers.map((s, i) => (
            <div className="wc-scorer" key={i}>
              <span className="wc-rk" style={i === 0 ? { color: "#e8c86a" } : undefined}>{i + 1}</span>
              {s.logo && <img src={s.logo} alt="" />}
              <span className="wc-scorer-nm">{s.player}</span>
              <span className="wc-scorer-nat">{s.nation}</span>
              <span className="wc-scorer-g teko">{s.goals}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 대진표 */}
      <WSec en="KNOCKOUT" kr="대진표" accent={accent} />
      <div className="card">
        <div className="wc-bracket">
          {knockout.map((r) => (
            <div className="wc-round" key={r.round}>
              <div className="wc-round-h">{r.label}</div>
              {r.matches.map((m, i) => (
                <div className={`wc-match${m.completed ? " done" : ""}`} key={i}>
                  <div className="wc-side">{m.home_logo && <img src={m.home_logo} alt="" />}<span className="wc-ab">{m.home_abbr || m.home}</span><Score s={m.home_score} /></div>
                  <div className="wc-side">{m.away_logo && <img src={m.away_logo} alt="" />}<span className="wc-ab">{m.away_abbr || m.away}</span><Score s={m.away_score} /></div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* 조별 최종순위 */}
      <WSec en="GROUP STAGE" kr="조별 최종순위" accent={accent} />
      <div className="wc-groups">
        {d.groups.map((g) => (
          <div className="card wc-grp" key={g.group}>
            <div className="wc-grp-h">Group {g.group}</div>
            {g.table.map((t, i) => (
              <div className={`wc-grp-row${i < 2 ? " adv" : ""}`} key={t.team}>
                <span className="wc-grp-pos">{i + 1}</span>
                {t.logo && <img src={t.logo} alt="" />}
                <span className="wc-grp-team">{t.team}</span>
                <span className="wc-grp-gd">{t.GD > 0 ? "+" : ""}{t.GD}</span>
                <span className="wc-grp-pts teko">{t.Pts}</span>
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* 스쿼드 브라우저 */}
      <WSec en="SQUADS" kr="국가대표 스쿼드" accent={accent}
        right={<span className="sec-count">{d.nations.length}</span>} />
      <div className="card">
        <div className="wc-nations">
          {d.nations.map((n) => (
            <button className={`wc-nat${nation === n.nation ? " active" : ""}`} key={n.nation}
              onClick={() => setNation(nation === n.nation ? null : n.nation)}
              style={nation === n.nation ? { ["--tc" as any]: accent, borderColor: accent } : undefined}>
              {n.logo && <img src={n.logo} alt="" />}
              <span>{n.nation}</span>
            </button>
          ))}
        </div>
        {nation && (
          <div className="wc-squad">
            {!squad && <div className="loading" style={{ padding: 20 }}>불러오는 중…</div>}
            {squad && squad.players.map((p, i) => (
              <button className="wc-sqp" key={i} onClick={() => p.epl_club && onPickTeam(p.epl_club)} disabled={!p.epl_club}>
                <span className="wc-sqp-jsy">{p.jersey || "-"}</span>
                {p.photo ? <img src={p.photo} alt="" /> : <span className="wc-sqp-ph">{p.pos}</span>}
                <div className="wc-sqp-mid">
                  <b>{p.player}</b>
                  <span>{p.pos}{p.age ? ` · ${p.age}세` : ""}</span>
                </div>
                {p.epl_club && <span className="wc-sqp-club">{p.club_logo && <img src={p.club_logo} alt="" />}{p.epl_club}</span>}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
