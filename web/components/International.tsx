"use client";
import { useEffect, useMemo, useState } from "react";
import {
  getIntlComp, getIntlHub, getIntlMatches, getIntlNation, getIntlNations,
  type IntlClubImpact, type IntlCompCard, type IntlCompDetail, type IntlGroup, type IntlHub, type IntlMatch,
  type IntlNation, type IntlNationItem, type IntlNationMatch, type IntlNationPlayers,
} from "@/lib/api";
import SectionHead from "./SectionHead";
import { Skel, SkelRows } from "./Skeleton";
import WorldCup from "./WorldCup";

// INTERNATIONAL — 국가대표 허브. 대회는 손으로 적지 않고 ESPN 리그 목록에서 자동 발견(src/intl_comps.py),
// 상태(예정·진행·종료·우승)는 일정·결과에서 계산한다. 지저분하지 않게:
//   NOW         지금 중요한 것만(진행·임박한 대회, 다음 A매치 기간, 오늘 경기)
//   MATCHES     기본 '주요 경기'(FIFA 30위 안·우리 리그 선수 4명+ 소집국) — 대륙·종류 칩으로 좁힘
//   TOURNAMENTS 대륙별(세계·유럽·아시아·아프리카·남미·북중미) — 본선 먼저, 끝난 예선은 접어 둠
//   MY NATION   고른 나라(기본 대한민국) — 다음 경기·폼·나가는 대회(조)·최근 소집 명단
// 대회 화면: 본선이면 조별 순위·토너먼트·출전국의 우리 리그 선수·클럽 영향(대회 중 클럽 경기 결장)
type Tab = "now" | "matches" | "tournaments" | "nation";
const STATUS: Record<string, { en: string; c: string }> = {
  live: { en: "LIVE", c: "#4fc27f" }, upcoming: { en: "UPCOMING", c: "#e0a53a" }, finished: { en: "FINISHED", c: "#8a94a8" },
};
const NATION_KEY = "intl-nation";            // 고른 나라(소집 명단 표기, 예: 'Korea, South')
const NATION_LABEL = "intl-nation-label";    // 탭 이름용 영어 표기(ESPN, 예: 'South Korea')
const DEFAULT_NATION = "Korea, South";
const md = (d: string) => (d ? `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}` : "");
const dday = (d: string, today: string) => Math.round((new Date(d).getTime() - new Date(today).getTime()) / 864e5);
const kst = (iso: string) => {
  if (!iso) return "";
  const t = new Date(iso);
  return Number.isNaN(t.getTime()) ? "" : t.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
};
const nm = (en: string, ko?: string) => (ko && ko !== en ? ko : en);
// 토너먼트 빈자리 이름(ESPN) → 한글 — 'Group F 2nd Place' → 'F조 2위', 'Quarterfinal 1 Winner' → '8강 1 승자'
const slotKo = (s: string) => s
  .replace(/^Group ([A-L]) Winner$/i, "$1조 1위").replace(/^Group ([A-L]) (\d)(?:st|nd|rd|th) Place$/i, "$1조 $2위")
  .replace(/^(\d)(?:st|nd|rd|th) Place Group ([A-L/]+)$/i, "$2조 중 $1위")
  .replace(/^Round of 32 (\d+) Winner$/i, "32강 $1 승자").replace(/^Round of 16 (\d+) Winner$/i, "16강 $1 승자")
  .replace(/^Quarterfinal (\d+) Winner$/i, "8강 $1 승자").replace(/^Semifinal (\d+) (Winner|Loser)$/i, (_, n, w) => `4강 ${n} ${w.toLowerCase() === "winner" ? "승자" : "패자"}`);
const lsGet = (k: string, d: string) => { try { return window.localStorage.getItem(k) || d; } catch { return d; } };
const lsSet = (k: string, v: string) => { try { window.localStorage.setItem(k, v); } catch { /* 저장 안 돼도 화면은 그대로 */ } };

function CompCard({ c, today, onOpen }: { c: IntlCompCard; today: string; onOpen: (c: IntlCompCard) => void }) {
  const e = c.edition;
  const st = STATUS[e.status];
  return (
    <button className="it-comp" onClick={() => onOpen(c)}>
      <div className="it-comp-top">
        <span className="it-kind">{c.kind_ko}</span>
        <span className="it-st" style={{ color: st.c, borderColor: st.c }}>
          {e.status === "upcoming" ? `D-${dday(e.start, today)}` : st.en}
        </span>
      </div>
      <b className="it-comp-name">{c.name_ko}</b>
      <span className="it-comp-sub">{e.season} · {md(e.start)}~{md(e.end)} · {e.played}/{e.matches}경기</span>
      {e.champion && <span className="it-champ">🏆 {e.champion}{e.runner_up ? <em> · 준우승 {e.runner_up}</em> : null}</span>}
    </button>
  );
}

function MatchRow({ m }: { m: IntlMatch }) {
  const done = m.state === "post" && m.hg != null && m.ag != null;
  return (
    <div className="it-m">
      <span className="it-m-when">{kst(m.kickoff) || md(m.date)}</span>
      <span className="it-m-comp">{m.comp}{m.stage ? ` · ${m.stage}` : ""}</span>
      <span className="it-m-h" title={m.home}>{nm(m.home, m.home_ko)}{m.home_logo ? <img src={m.home_logo} alt="" /> : null}</span>
      <b className="it-m-s">{done ? `${m.hg}-${m.ag}` : "vs"}</b>
      <span className="it-m-a" title={m.away}>{m.away_logo ? <img src={m.away_logo} alt="" /> : null}{nm(m.away, m.away_ko)}</span>
    </div>
  );
}

// 조 하나 — 순위표 + 그 조 경기
function GroupCard({ g, ms, me }: { g: IntlGroup; ms: IntlMatch[]; me: string }) {
  return (
    <div className="card it-group">
      <div className="it-group-h">{g.name.toUpperCase()}</div>
      <table className="it-gt">
        <thead><tr><th>#</th><th className="l">팀</th><th>경기</th><th>승</th><th>무</th><th>패</th><th>득실</th><th>승점</th></tr></thead>
        <tbody>
          {g.rows.map((r, i) => (
            <tr key={r.team} className={r.team === me ? "me" : ""}>
              <td>{r.rank || i + 1}</td>
              <td className="l" title={r.team}>{r.logo ? <img src={r.logo} alt="" /> : null}{nm(r.team, r.team_ko)}</td>
              <td>{r.p}</td><td>{r.w}</td><td>{r.d}</td><td>{r.l}</td><td>{r.gd > 0 ? `+${r.gd}` : r.gd}</td><td><b>{r.pts}</b></td>
            </tr>
          ))}
        </tbody>
      </table>
      {ms.length > 0 && (
        <div className="it-gm">
          {ms.map((m) => {
            const done = m.state === "post" && m.hg != null;
            return (
              <div key={m.event_id} className={m.home === me || m.away === me ? "me" : ""}>
                <span>{md(m.date)}</span>
                <span className="h">{nm(m.home, m.home_ko)}</span>
                <b>{done ? `${m.hg}-${m.ag}` : "vs"}</b>
                <span>{nm(m.away, m.away_ko)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// 토너먼트 — 단계별 열(16강 → 결승). 빈자리는 'F조 2위' 처럼
function Knockout({ rounds, matches }: { rounds: NonNullable<IntlCompDetail["rounds"]>; matches: IntlMatch[] }) {
  const ko = rounds.filter((r) => r.slug !== "group-stage");
  if (!ko.length) return null;
  return (
    <div className="it-ko-wrap">
      <div className="it-ko">
        {ko.map((r) => (
          <div className="it-ko-col" key={r.slug}>
            <div className="it-ko-h">{r.en}{r.ko ? <em>{r.ko}</em> : null}</div>
            {matches.filter((m) => m.round === r.slug).map((m) => {
              const done = m.state === "post" && m.hg != null;
              return (
                <div className="it-ko-m" key={m.event_id}>
                  <span className={m.winner === "home" ? "w" : ""}>{m.home_ko && m.home_ko !== m.home ? m.home_ko : slotKo(m.home)}</span>
                  <span className={m.winner === "away" ? "w" : ""}>{m.away_ko && m.away_ko !== m.away ? m.away_ko : slotKo(m.away)}</span>
                  <small>{md(m.date)}{done ? ` · ${m.hg}-${m.ag}` : ""}</small>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function NationPlayers({ ps, onPickTeam }: { ps: IntlNationPlayers[]; onPickTeam: (t: string, league?: string) => void }) {
  return (
    <div className="it-np">
      {ps.map((n) => (
        <div className="it-np-c" key={n.nation}>
          <div className="it-np-h">
            {n.flag ? <img src={n.flag} alt="" /> : null}<b>{n.nation_ko}</b><span>{n.players.length}명</span>
            <em title={`명단 기준일 ${n.squad_for}`}>{n.announced ? "대회 명단" : "지난 소집 기준"}</em>
          </div>
          <div className="it-np-l">
            {n.players.map((p) => (
              <button key={p.player} onClick={() => onPickTeam(p.club, p.league)} title={`${p.club} 팀 화면`}>
                {p.player}<span>{p.club}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ClubImpact({ items, onPickTeam }: { items: IntlClubImpact[]; onPickTeam: (t: string, league?: string) => void }) {
  return (
    <div className="it-ci">
      {items.map((c) => (
        <button className="it-ci-r" key={`${c.league}-${c.club}`} onClick={() => onPickTeam(c.club, c.league)}>
          {c.logo ? <img src={c.logo} alt="" /> : <span className="it-ci-noimg" />}
          <b>{c.club}</b>
          <span className="it-ci-n">{c.players.length}명</span>
          <span className="it-ci-p">{c.players.map((p) => `${p.player}(${p.nation_ko})`).join(", ")}</span>
          {c.club_matches != null && <span className="it-ci-m" title="대회 기간 이 클럽 경기 수(전 대회) — 소집 선수는 이 경기들을 빠진다">대회 중 클럽 {c.club_matches}경기</span>}
        </button>
      ))}
    </div>
  );
}

function CompDetail({ code, season, accent, me, onBack, onPickTeam }: {
  code: string; season: string; accent: string; me: string; onBack: () => void; onPickTeam: (t: string, league?: string) => void;
}) {
  const [d, setD] = useState<IntlCompDetail | null>(null);
  const [s, setS] = useState(season);
  useEffect(() => { let a = true; setD(null); getIntlComp(code, s).then((x) => a && setD(x)).catch(() => {}); return () => { a = false; }; }, [code, s]);
  // 월드컵은 조별 순위·득점왕·차출 클럽까지 있는 전용 화면(기록 보관)
  if (code === "fifa.world" && (!d || d.edition.season === "2026")) return (
    <div>
      <button className="it-back" onClick={onBack}>← INTERNATIONAL</button>
      <WorldCup accent={accent} onPickTeam={onPickTeam} />
    </div>
  );
  if (!d) return <div className="skel-wrap"><Skel h={60} r={14} /><SkelRows n={8} /></div>;
  const groups = d.groups ?? [];
  const rounds = d.rounds ?? [];
  const hero = (
    <div className="card it-hero">
      <span className="it-kind">{d.kind_ko}</span>
      <h2>{d.name_ko} {d.edition.season}</h2>
      <p>{d.edition.start} ~ {d.edition.end} · {d.edition.played}/{d.edition.matches}경기 · {STATUS[d.edition.status].en}
        {d.edition.status === "upcoming" ? ` · D-${dday(d.edition.start, new Date().toISOString().slice(0, 10))}` : ""}</p>
      {rounds.length > 1 && <p className="it-rounds">{rounds.map((r) => `${r.ko || r.en} ${r.n}`).join(" → ")}</p>}
      {d.edition.champion && <p className="it-champ big">🏆 우승 {d.edition.champion}{d.edition.runner_up ? ` · 준우승 ${d.edition.runner_up}` : ""}</p>}
      {d.editions.length > 1 && (
        <div className="it-chips">{d.editions.map((e) => (
          <button key={e.season} className={e.season === d.edition.season ? "on" : ""} onClick={() => setS(e.season)}>{e.season}</button>
        ))}</div>
      )}
    </div>
  );
  // 본선(조가 있는 대회) — 조별 순위 → 토너먼트 → 우리 리그 선수 → 클럽 영향
  if (groups.length) {
    const gm = (name: string) => d.matches.filter((m) => m.group === name);
    const ps = d.players ?? [];
    const nPlayers = ps.reduce((a, n) => a + n.players.length, 0);
    return (
      <div className="it-detail">
        <button className="it-back" onClick={onBack}>← INTERNATIONAL</button>
        {hero}
        <SectionHead title="GROUPS" kr="조별리그" meta={`${groups.length}개 조 · ${rounds.find((r) => r.slug === "group-stage")?.n ?? 0}경기`} />
        <div className="it-groups">{groups.map((g) => <GroupCard key={g.name} g={g} ms={gm(g.name)} me={me} />)}</div>
        {rounds.some((r) => r.slug !== "group-stage") && (
          <>
            <SectionHead title="KNOCKOUT" kr="토너먼트" meta="단계별 · 빈자리는 조 순위로 정해짐" />
            <Knockout rounds={rounds} matches={d.matches} />
          </>
        )}
        {ps.length > 0 && (
          <>
            <SectionHead title="OUR LEAGUE PLAYERS" kr="출전국의 우리 리그 선수" meta={`${ps.length}개국 · ${nPlayers}명 · 가장 최근 소집 명단 기준`} />
            <NationPlayers ps={ps} onPickTeam={onPickTeam} />
          </>
        )}
        {(d.club_impact ?? []).length > 0 && (
          <>
            <SectionHead title="CLUB IMPACT" kr="대회로 선수를 보내는 클럽" meta={d.edition.status === "finished" ? "선수 수 기준" : "선수 수 · 대회 기간 클럽 경기 수"} />
            <ClubImpact items={d.club_impact ?? []} onPickTeam={onPickTeam} />
          </>
        )}
      </div>
    );
  }
  const stages = new Map<string, IntlMatch[]>();
  for (const m of d.matches) {
    const k = m.stage || (m.state === "post" ? "결과" : "일정");
    stages.set(k, [...(stages.get(k) ?? []), m]);
  }
  return (
    <div className="it-detail">
      <button className="it-back" onClick={onBack}>← INTERNATIONAL</button>
      {hero}
      {[...stages.entries()].map(([k, ms]) => (
        <section className="card it-sec" key={k}>
          <SectionHead title={k.toUpperCase()} meta={`${ms.length}경기`} />
          <div className="it-list">{ms.map((m) => <MatchRow key={m.event_id} m={m} />)}</div>
        </section>
      ))}
      {d.matches.length === 0 && <p className="pv-empty">이 회차의 경기 정보가 아직 없습니다.</p>}
    </div>
  );
}

function NationMatch({ m }: { m: IntlNationMatch }) {
  return (
    <div className="it-m it-nm">
      <span className="it-m-when">{kst(m.kickoff) || md(m.date)}</span>
      <span className="it-m-comp">{m.comp}</span>
      <span className="it-nm-ha">{m.home ? "홈" : "원정"}</span>
      <span className="it-m-a" title={m.opp}>{m.opp_logo ? <img src={m.opp_logo} alt="" /> : null}{nm(m.opp, m.opp_ko)}</span>
      {m.score ? <b className={`it-res r-${m.result}`}>{m.result} {m.score}</b> : <b className="it-m-s">vs</b>}
    </div>
  );
}

// MY NATION — 고른 나라 대표팀(기본 대한민국). 고른 나라는 이 브라우저에 기억
function NationView({ nation, onNation, onOpen, onPickTeam }: {
  nation: string; onNation: (n: string, label: string) => void; onOpen: (code: string, season: string) => void;
  onPickTeam: (t: string, league?: string) => void;
}) {
  const [list, setList] = useState<IntlNationItem[]>([]);
  const [d, setD] = useState<IntlNation | null>(null);
  useEffect(() => { let a = true; getIntlNations().then((x) => a && setList(x.nations)).catch(() => {}); return () => { a = false; }; }, []);
  useEffect(() => {
    let a = true; setD(null);
    getIntlNation(nation).then((x) => { if (a) { setD(x); onNation(nation, x.display); } }).catch(() => {});
    return () => { a = false; };
  }, [nation]); // eslint-disable-line react-hooks/exhaustive-deps
  const byPos = useMemo(() => {
    const g: Record<string, IntlNation["squad"]> = {};
    for (const p of d?.squad ?? []) (g[p.pos || "-"] ??= []).push(p);
    return g;
  }, [d]);
  return (
    <div className="it-nation">
      <div className="it-nation-pick">
        <span className="nw-lbl">MY NATION</span>
        <select value={nation} onChange={(e) => onNation(e.target.value, "")} aria-label="대표팀 고르기">
          {(list.length ? list : [{ nation, nation_ko: d?.nation_ko ?? nation, fifa_rank: null, ours: 0 } as IntlNationItem]).map((n) => (
            <option key={n.nation} value={n.nation}>{n.nation_ko}{n.fifa_rank ? ` · FIFA ${n.fifa_rank}위` : ""}{n.ours ? ` · 우리 리그 ${n.ours}명` : ""}</option>
          ))}
        </select>
      </div>
      {!d ? <div className="skel-wrap"><Skel h={90} r={16} /><SkelRows n={6} /></div> : (
        <>
          <div className="card it-hero it-nation-hero">
            <div className="it-nation-top">
              {d.flag ? <img src={d.flag} alt="" /> : null}
              <div>
                <h2>{d.nation_ko} <small>{d.display}</small></h2>
                <p>{d.conf}{d.fifa_rank ? ` · FIFA ${d.fifa_rank}위` : ""}{d.ours ? ` · 최근 소집 중 우리 리그 선수 ${d.ours}명` : ""}</p>
              </div>
              {d.form.length > 0 && (
                <div className="it-form" title="최근 5경기(왼쪽이 오래된 경기)">
                  {d.form.map((r, i) => <span key={i} className={`r-${r}`}>{r}</span>)}
                </div>
              )}
            </div>
          </div>
          {d.tournaments.length > 0 && (
            <>
              <SectionHead title="TOURNAMENTS" kr="나가는 대회" meta="예정·진행 중 · 본선은 같은 조" />
              <div className="it-nt">
                {d.tournaments.map((t) => (
                  <button className="card it-nt-c" key={`${t.code}-${t.edition?.season}`} onClick={() => t.edition && onOpen(t.code, t.edition.season)}>
                    <div className="it-comp-top">
                      <span className="it-kind">{t.kind_ko}</span>
                      {t.edition && <span className="it-st" style={{ color: STATUS[t.edition.status].c, borderColor: STATUS[t.edition.status].c }}>
                        {t.edition.status === "upcoming" ? `D-${dday(t.edition.start, new Date().toISOString().slice(0, 10))}` : STATUS[t.edition.status].en}</span>}
                    </div>
                    <b className="it-comp-name">{t.name_ko} {t.edition?.season}</b>
                    <span className="it-comp-sub">{t.edition ? `${md(t.edition.start)}~${md(t.edition.end)} · ` : ""}이 나라 {t.matches}경기 예정</span>
                    {t.group && (
                      <span className="it-nt-g">{t.group.name.toUpperCase()} · {t.group.rows.map((r) => nm(r.team, r.team_ko)).join(" · ")}</span>
                    )}
                  </button>
                ))}
              </div>
            </>
          )}
          <section className="card it-sec">
            <SectionHead title="NEXT MATCHES" kr="다음 경기" meta={`${d.upcoming.length}경기`} />
            {d.upcoming.length ? <div className="it-list">{d.upcoming.map((m) => <NationMatch key={m.event_id} m={m} />)}</div>
              : <p className="pv-empty">예정된 경기가 아직 없습니다.</p>}
          </section>
          <section className="card it-sec">
            <SectionHead title="RECENT RESULTS" kr="최근 결과" meta={`${d.recent.length}경기`} />
            {d.recent.length ? <div className="it-list">{d.recent.map((m) => <NationMatch key={m.event_id} m={m} />)}</div>
              : <p className="pv-empty">최근 결과가 없습니다.</p>}
          </section>
          {d.squad.length > 0 && (
            <section className="card it-sec">
              <SectionHead title="LATEST SQUAD" kr="최근 소집 중 우리 리그 선수" meta={`${d.squad_for} 명단 기준 · 누르면 클럽 화면`} />
              {["GK", "DF", "MF", "FW", "-"].filter((p) => byPos[p]?.length).map((p) => (
                <div className="it-sq" key={p}>
                  <span className="it-sq-pos">{p}</span>
                  <div className="it-sq-l">
                    {byPos[p].map((x) => x.ours ? (
                      <button key={x.player} className="ours" onClick={() => onPickTeam(x.club, x.league)} title={`${x.club} 팀 화면`}>
                        {x.player}<span>{x.club}{x.caps != null ? ` · ${x.caps}경기` : ""}</span>
                      </button>
                    ) : (
                      <span key={x.player} className="it-sq-x">{x.player}<span>{x.club}{x.caps != null ? ` · ${x.caps}경기` : ""}</span></span>
                    ))}
                  </div>
                </div>
              ))}
            </section>
          )}
        </>
      )}
    </div>
  );
}

export default function International({ accent, onPickTeam, initialComp }: {
  accent: string; onPickTeam: (t: string, league?: string) => void; initialComp?: string;
}) {
  const [hub, setHub] = useState<IntlHub | null>(null);
  // 주소 #tournaments·#matches·#nation 으로 탭 바로 열기(공유·점검)
  const [tab, setTab] = useState<Tab>(() => {
    if (typeof window === "undefined") return "now";
    const h = window.location.hash.replace("#", "");
    return h === "matches" || h === "tournaments" || h === "nation" ? h : "now";
  });
  const [open, setOpen] = useState<{ code: string; season: string } | null>(initialComp ? { code: initialComp, season: "" } : null);
  const [when, setWhen] = useState<"upcoming" | "recent">("upcoming");
  const [scope, setScope] = useState<"key" | "all">("key");
  const [conf, setConf] = useState("");
  const [kind, setKind] = useState("");
  const [ms, setMs] = useState<IntlMatch[] | null>(null);
  const [showDone, setShowDone] = useState(false);
  const [nation, setNation] = useState(DEFAULT_NATION);
  const [nationLabel, setNationLabel] = useState("South Korea");
  useEffect(() => { setNation(lsGet(NATION_KEY, DEFAULT_NATION)); setNationLabel(lsGet(NATION_LABEL, "South Korea")); }, []);
  useEffect(() => { let a = true; getIntlHub().then((x) => a && setHub(x)).catch(() => {}); return () => { a = false; }; }, []);
  useEffect(() => {
    if (tab !== "matches" && tab !== "now") return;
    let a = true; setMs(null);
    getIntlMatches({ scope, when, conf, kind, limit: tab === "now" ? 12 : 120 }).then((x) => a && setMs(x.matches)).catch(() => a && setMs([]));
    return () => { a = false; };
  }, [tab, scope, when, conf, kind]);
  const today = hub?.today ?? new Date().toISOString().slice(0, 10);
  const confs = useMemo(() => (hub?.by_conf ?? []).map((c) => ({ k: c.conf, en: c.en, ko: c.ko })), [hub]);
  const pickNation = (n: string, label: string) => {
    setNation(n); lsSet(NATION_KEY, n);
    if (label) { setNationLabel(label); lsSet(NATION_LABEL, label); }
  };

  if (open) return <CompDetail code={open.code} season={open.season} accent={accent} me={nationLabel} onBack={() => setOpen(null)} onPickTeam={onPickTeam} />;
  if (!hub) return <div className="skel-wrap"><Skel h={90} r={16} /><SkelRows n={6} /></div>;
  const w = hub.window;
  const TABS: [Tab, string, string][] = [
    ["now", "NOW", "지금"], ["matches", "MATCHES", "A매치"], ["tournaments", "TOURNAMENTS", "대륙별 대회"],
    ["nation", nationLabel.toUpperCase(), "내 대표팀"],
  ];
  return (
    <div className="it">
      <div className="it-tabs">
        {TABS.map(([t, en, ko]) => (
          <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{en}<em>{ko}</em></button>
        ))}
      </div>

      {tab === "now" && (
        <>
          <div className="it-now">
            {hub.live.map((c) => (
              <div className="card it-now-c live" key={c.code} onClick={() => setOpen({ code: c.code, season: c.edition.season })}>
                <span className="it-st" style={{ color: STATUS.live.c, borderColor: STATUS.live.c }}>LIVE</span>
                <b>{c.name_ko}</b><span>{md(c.edition.start)}~{md(c.edition.end)} · {c.edition.played}/{c.edition.matches}경기</span>
              </div>
            ))}
            {w && (
              <div className="card it-now-c">
                <span className="it-st" style={{ color: hub.window_state === "now" ? STATUS.live.c : STATUS.upcoming.c, borderColor: hub.window_state === "now" ? STATUS.live.c : STATUS.upcoming.c }}>
                  {hub.window_state === "now" ? "NOW" : `D-${dday(w.start, today)}`}
                </span>
                <b>{w.label}</b>
                <span>{md(w.start)}~{md(w.end)} · {w.matches}경기 · 지난 소집 기준 우리 리그 선수 {hub.callups}명(명단 발표 뒤 갱신) · 팀 화면 일정 탭에서 클럽별 소집 선수</span>
              </div>
            )}
            {hub.next_tournament && (
              <div className="card it-now-c" onClick={() => setOpen({ code: hub.next_tournament!.code, season: hub.next_tournament!.edition.season })}>
                <span className="it-st" style={{ color: STATUS.upcoming.c, borderColor: STATUS.upcoming.c }}>D-{dday(hub.next_tournament.edition.start, today)}</span>
                <b>{hub.next_tournament.name_ko} {hub.next_tournament.edition.season}</b>
                <span>{md(hub.next_tournament.edition.start)}~{md(hub.next_tournament.edition.end)} · {hub.next_tournament.edition.matches}경기 · 리그가 계속돼 소집 선수는 클럽 경기를 빠짐 · 조 편성·차출 클럽 보기 →</span>
              </div>
            )}
          </div>
          <section className="card it-sec">
            <SectionHead title="NEXT KEY MATCHES" kr="다가오는 주요 A매치" meta="FIFA 30위 안 · 우리 리그 선수 4명+ 소집국" />
            {ms === null ? <SkelRows n={6} /> : ms.length ? <div className="it-list">{ms.map((m) => <MatchRow key={m.event_id} m={m} />)}</div>
              : <p className="pv-empty">예정된 주요 A매치가 없습니다.</p>}
            <button className="it-more" onClick={() => setTab("matches")}>전체 A매치 보기 →</button>
          </section>
        </>
      )}

      {tab === "matches" && (
        <section className="card it-sec">
          <div className="it-filters">
            <div className="it-chips">
              {(["upcoming", "recent"] as const).map((v) => <button key={v} className={when === v ? "on" : ""} onClick={() => setWhen(v)}>{v === "upcoming" ? "예정" : "결과"}</button>)}
              <span className="it-sep" />
              {(["key", "all"] as const).map((v) => <button key={v} className={scope === v ? "on" : ""} onClick={() => setScope(v)}>{v === "key" ? "주요 경기" : "전체"}</button>)}
            </div>
            <div className="it-chips">
              <button className={conf === "" ? "on" : ""} onClick={() => setConf("")}>전 대륙</button>
              {confs.map((c) => <button key={c.k} className={conf === c.k ? "on" : ""} onClick={() => setConf(c.k)}>{c.ko}</button>)}
              <span className="it-sep" />
              {([["", "전체"], ["tournament", "본선"], ["nations_league", "네이션스리그"], ["qualifier", "예선"], ["friendly", "친선"]] as const).map(([k, l]) => (
                <button key={k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>{l}</button>
              ))}
            </div>
          </div>
          {ms === null ? <SkelRows n={10} /> : ms.length ? <div className="it-list">{ms.map((m) => <MatchRow key={m.event_id} m={m} />)}</div>
            : <p className="pv-empty">조건에 맞는 경기가 없습니다.</p>}
        </section>
      )}

      {tab === "tournaments" && (
        <>
          {hub.by_conf.map((g) => {
            // 본선·네이션스리그·진행/예정 대회는 늘 보이고, 끝난 예선·친선은 '끝난 대회 보기'로 접는다
            const main = g.comps.filter((c) => c.kind === "tournament" || c.kind === "nations_league" || c.edition.status !== "finished");
            const rest = g.comps.filter((c) => !main.includes(c));
            return (
              <section className="it-conf" key={g.conf}>
                <SectionHead title={g.en} kr={g.ko} meta={`${g.comps.length}개 대회`} />
                <div className="it-grid">
                  {main.map((c) => <CompCard key={c.code} c={c} today={today} onOpen={(x) => setOpen({ code: x.code, season: x.edition.season })} />)}
                  {showDone && rest.map((c) => <CompCard key={c.code} c={c} today={today} onOpen={(x) => setOpen({ code: x.code, season: x.edition.season })} />)}
                </div>
                {!showDone && rest.length > 0 && <button className="it-more" onClick={() => setShowDone(true)}>끝난 예선·친선 {rest.length}개 보기</button>}
              </section>
            );
          })}
        </>
      )}

      {tab === "nation" && (
        <NationView nation={nation} onNation={pickNation} onOpen={(code, season) => setOpen({ code, season })} onPickTeam={onPickTeam} />
      )}
    </div>
  );
}
