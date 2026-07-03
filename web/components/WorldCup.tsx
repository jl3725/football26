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

// "2026-06-28" → "6/28"
function fmtD(iso: string): string {
  const p = String(iso || "").split("-");
  return p.length === 3 ? `${+p[1]}/${+p[2]}` : iso || "";
}

export default function WorldCup({ accent, onPickTeam }: { accent: string; onPickTeam: (t: string, league?: string) => void }) {
  const [d, setD] = useState<WorldCupData | null>(null);
  const [nation, setNation] = useState<string | null>(null);
  const [squad, setSquad] = useState<WCSquad | null>(null);
  const [clubLeague, setClubLeague] = useState<string>("");   // "" = 전체
  const [clubPage, setClubPage] = useState(0);

  useEffect(() => { let a = true; getWC().then((x) => a && setD(x)).catch(() => {}); return () => { a = false; }; }, []);
  useEffect(() => {
    if (!nation) { setSquad(null); return; }
    let a = true; setSquad(null);
    getWCSquad(nation).then((x) => a && setSquad(x)).catch(() => {});
    return () => { a = false; };
  }, [nation]);

  if (!d) return <div className="loading">월드컵 데이터 불러오는 중…</div>;
  const knockout = d.matches.filter((r) => r.round !== "group-stage");
  const clubLeagues = Array.from(new Set(d.club_callups.map((c) => c.league).filter(Boolean)));
  // 전체: 알파벳순 / 특정 리그: 차출 수 순(백엔드 정렬 유지)
  const clubsF = clubLeague ? d.club_callups.filter((c) => c.league === clubLeague)
                            : [...d.club_callups].sort((a, b) => a.club.localeCompare(b.club));
  const CLUB_PER = 20;
  const clubPages = Math.ceil(clubsF.length / CLUB_PER);
  const cpage = Math.min(clubPage, Math.max(0, clubPages - 1));
  const pagedClubs = clubsF.slice(cpage * CLUB_PER, cpage * CLUB_PER + CLUB_PER);

  return (
    <div className="fade home">
      {/* HERO */}
      <div className="hx wc-hx" style={{ ["--tc" as any]: accent }}>
        <div className="hx-glow" style={{ background: "radial-gradient(60% 120% at 85% 0%, #d4af3755, transparent 70%)" }} />
        <div className="hx-kicker" style={{ color: "#e8c86a" }}>FIFA WORLD CUP · 2026</div>
        <h1 className="hx-title">WORLD CUP 2026</h1>
        <div className="hx-meta">북중미 공동 개최 · 48개국 · <span style={{ color: "#e8c86a" }}>녹아웃 스테이지 진행 중</span></div>
      </div>

      {/* FIFA 랭킹 TOP 30 — 월드컵 결과 실시간 반영 */}
      {d.fifa_ranking && d.fifa_ranking.length > 0 && (
        <>
          <WSec en="FIFA WORLD RANKING" kr={d.fifa_live ? "FIFA 랭킹 TOP 30 · 월드컵 실시간 반영" : "FIFA 랭킹 TOP 30"} accent={accent}
            right={<span className="wc-fifa-upd">{d.fifa_live ? "🔴 예상 " : ""}{d.fifa_updated ? `공식 ${d.fifa_updated} 기준` : ""}</span>} />
          <div className="card">
            {d.fifa_live && <div className="wc-fifa-note">공식 점수({d.fifa_updated})에 월드컵 경기 결과를 FIFA 공식 산식으로 반영한 <b>예상 순위</b>입니다. 변동(▲▼)은 공식 순위 대비.</div>}
            <div className="wc-fifa">
              {d.fifa_ranking.map((f) => {
                const tone = f.rank_change > 0 ? "up" : f.rank_change < 0 ? "down" : "same";
                return (
                  <div className="wc-fifa-row" key={f.code || f.rank}>
                    <span className="wc-fr-rk" style={f.rank === 1 ? { color: "#e8c86a" } : undefined}>{f.rank}</span>
                    <span className={`wc-fr-ch ${tone}`} title={`공식 ${f.official_rank}위`}>
                      {tone === "up" ? `▲${f.rank_change}` : tone === "down" ? `▼${-f.rank_change}` : "–"}
                    </span>
                    {f.flag && <img className="wc-fr-flag" src={f.flag} alt="" />}
                    <span className="wc-fr-team">{f.team}</span>
                    <span className="wc-fr-conf">{f.confederation}</span>
                    <span className="wc-fr-pts teko">{f.points.toFixed(0)}</span>
                    <span className={`wc-fr-dp ${f.points_change >= 0 ? "up" : "down"}`}>
                      {f.points_change >= 0 ? "+" : ""}{f.points_change.toFixed(1)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      {/* 클럽별 월드컵 차출 */}
      {d.club_callups.length > 0 && (
        <>
          <WSec en="CLUB CALL-UPS" kr="클럽별 월드컵 차출" accent={accent}
            right={
              clubLeagues.length > 1 ? (
                <div className="wc-lg-filter">
                  <button className={clubLeague === "" ? "active" : ""} onClick={() => { setClubLeague(""); setClubPage(0); }}
                    style={clubLeague === "" ? { background: accent, color: "#0b0f17" } : undefined}>전체</button>
                  {clubLeagues.map((lg) => (
                    <button key={lg} className={clubLeague === lg ? "active" : ""} onClick={() => { setClubLeague(lg); setClubPage(0); }}
                      style={clubLeague === lg ? { background: accent, color: "#0b0f17" } : undefined}>{lg}</button>
                  ))}
                </div>
              ) : <span className="sec-count">{clubsF.reduce((a, c) => a + c.count, 0)}</span>
            } />
          <div className="wc-clubs">
            {pagedClubs.map((c) => (
              <div className="wc-club" key={c.club}>
                <button className="wc-club-h" onClick={() => onPickTeam(c.club, c.league)}>
                  {c.logo && <img src={c.logo} alt="" />}
                  <span className="wc-club-name">{c.club}</span>
                  {c.league && <span className="wc-club-lg">{c.league}</span>}
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
          {clubPages > 1 && (
            <div className="wc-pager">
              <button disabled={cpage === 0} onClick={() => setClubPage(cpage - 1)}>‹</button>
              {Array.from({ length: clubPages }, (_, i) => (
                <button key={i} className={i === cpage ? "active" : ""} onClick={() => setClubPage(i)}
                  style={i === cpage ? { background: accent, color: "#0b0f17" } : undefined}>{i + 1}</button>
              ))}
              <button disabled={cpage >= clubPages - 1} onClick={() => setClubPage(cpage + 1)}>›</button>
            </div>
          )}
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

      {/* 도움왕 */}
      {d.assists && d.assists.length > 0 && (
        <>
          <WSec en="PLAYMAKERS" kr="도움왕" accent={accent} />
          <div className="card">
            <div className="wc-scorers">
              {d.assists.map((s, i) => (
                <div className="wc-scorer" key={i}>
                  <span className="wc-rk" style={i === 0 ? { color: "#7fb4f0" } : undefined}>{i + 1}</span>
                  {s.logo && <img src={s.logo} alt="" />}
                  <span className="wc-scorer-nm">{s.player}</span>
                  <span className="wc-scorer-nat">{s.nation}</span>
                  <span className="wc-scorer-g teko" style={{ color: "#7fb4f0" }}>{s.assists}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* 신예 · 노장 (득점+도움 임팩트) */}
      {((d.rising_stars?.length ?? 0) > 0 || (d.veterans?.length ?? 0) > 0) && (
        <>
          <WSec en="STANDOUTS" kr="신예 · 노장" accent={accent} />
          <div className="wc-two">
            <div className="card">
              <div className="card-h">🌱 떠오르는 신예 <span className="wc-sub">21세 이하</span></div>
              {d.rising_stars.map((c, i) => (
                <div className="wc-imp" key={i}>
                  {c.photo ? <img className="wc-imp-ph" src={c.photo} alt="" /> : (c.logo && <img className="wc-imp-flag" src={c.logo} alt="" />)}
                  <div className="wc-imp-mid"><b>{c.player}</b><span>{c.nation} · {c.age}세{c.club ? " · " + c.club : ""}</span></div>
                  <span className="wc-imp-ga" style={{ color: "#5fd08c" }}>{c.goals}G {c.assists}A</span>
                </div>
              ))}
              {d.rising_stars.length === 0 && <div className="mgr-meta">해당 없음</div>}
            </div>
            <div className="card">
              <div className="card-h">🔥 노장 투혼 <span className="wc-sub">33세 이상</span></div>
              {d.veterans.map((c, i) => (
                <div className="wc-imp" key={i}>
                  {c.photo ? <img className="wc-imp-ph" src={c.photo} alt="" /> : (c.logo && <img className="wc-imp-flag" src={c.logo} alt="" />)}
                  <div className="wc-imp-mid"><b>{c.player}</b><span>{c.nation} · {c.age}세{c.club ? " · " + c.club : ""}</span></div>
                  <span className="wc-imp-ga" style={{ color: "#e0a24d" }}>{c.goals}G {c.assists}A</span>
                </div>
              ))}
              {d.veterans.length === 0 && <div className="mgr-meta">해당 없음</div>}
            </div>
          </div>
        </>
      )}

      {/* 조별리그 영웅 — 아쉬운 탈락 */}
      {d.group_heroes && d.group_heroes.length > 0 && (
        <>
          <WSec en="GALLANT EXITS" kr="조별리그 영웅 · 아쉬운 탈락" accent={accent} />
          <div className="card">
            <div className="wc-heroes">
              {d.group_heroes.map((t, i) => (
                <div className="wc-hero" key={i}>
                  {t.logo && <img className="wc-hero-logo" src={t.logo} alt="" />}
                  <div className="wc-hero-nm">{t.team}<span className="wc-hero-grp">조 {t.group}</span></div>
                  <div className="wc-hero-rec">{t.W}승 {t.D}무 {t.L}패 · <b>{t.Pts}점</b> · GD {t.GD >= 0 ? "+" : ""}{t.GD}</div>
                  <div className="wc-hero-stars">{t.stars.map((s, j) => <span key={j}>{s.player} <em>{s.goals}G{s.assists}A</em></span>)}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* 대진표 */}
      <WSec en="KNOCKOUT" kr="대진표" accent={accent} />
      <div className="card">
        <div className="wc-bracket">
          {knockout.map((r) => (
            <div className="wc-round" key={r.round}>
              <div className="wc-round-h">{r.label}</div>
              {r.matches.map((m, i) => {
                const st = (m.status || "").toLowerCase();
                const live = !m.completed && st !== "" && st !== "scheduled";  // "32'", "HT" 등
                const label = live ? m.status : fmtD(m.date);   // 예정/종료=날짜, 진행중=분
                return (
                <div className={`wc-match${m.completed ? " done" : ""}${live ? " live" : ""}`} key={i}>
                  <div className="wc-match-date">{label}{m.completed && <span className="wc-md-ft"> · 종료</span>}</div>
                  <div className="wc-side">{m.home_logo && <img src={m.home_logo} alt="" />}<span className="wc-ab">{m.home_abbr || m.home}</span><Score s={m.home_score} /></div>
                  <div className="wc-side">{m.away_logo && <img src={m.away_logo} alt="" />}<span className="wc-ab">{m.away_abbr || m.away}</span><Score s={m.away_score} /></div>
                </div>
                );
              })}
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
              <button className="wc-sqp" key={i} onClick={() => p.club && onPickTeam(p.club, p.league)} disabled={!p.club}>
                <span className="wc-sqp-jsy">{p.jersey || "-"}</span>
                {p.photo ? <img src={p.photo} alt="" /> : <span className="wc-sqp-ph">{p.pos}</span>}
                <div className="wc-sqp-mid">
                  <b>{p.player}</b>
                  <span>{p.pos}{p.age ? ` · ${p.age}세` : ""}</span>
                </div>
                {p.club && <span className="wc-sqp-club">{p.club_logo && <img src={p.club_logo} alt="" />}{p.club}</span>}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
