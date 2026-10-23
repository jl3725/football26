"use client";
import { useEffect, useMemo, useState } from "react";
import { getInbox, type Fixture, type Inbox, type InboxMsg, type Signal } from "@/lib/api";
import { useMatchPreview } from "@/lib/matchPreview";
import { usePeek } from "./PlayerPeek";
import SectionHead from "./SectionHead";
import { SkelCards } from "./Skeleton";

// 팀 인박스 — /api/inbox/{team}: 자동 감지 신호 + 경기 브리핑(다음·지난 경기·일정 과밀) + 팀 폼(연승·연패·결정력·막판 실점)
// + 선수 폼(OVR 2주 변화) + 선발 제외 감지. 중요도 상위 3건 = BRIEFING, 나머지는 분류 필터·새 소식(읽음) 표시.
// 예전엔 6가지 신호를 분류 카드로만 보여 '지금 무엇이 중요한지'가 안 보였다(2026-10-15 사용자 요청).

const TONE: Record<string, string> = { good: "#3ecf8e", bad: "#ff6b7d", warn: "#f4cf5e", info: "#6aa6e0" };
const CATS: [string, string][] = [["all", "전체"], ["match", "경기"], ["form", "폼"], ["injury", "부상"], ["squad", "선수단"],
  ["contract", "계약"], ["value", "시장가치"], ["manager", "감독"]];
const CAT_EN: Record<string, string> = { match: "MATCH", form: "FORM", injury: "INJURY", squad: "SQUAD", contract: "CONTRACT", value: "VALUE", manager: "MANAGER" };

function useRead(team: string) {
  const key = `inbox_read_${team}`;
  const [read, setRead] = useState<Set<string>>(new Set());
  useEffect(() => {
    try { setRead(new Set(JSON.parse(localStorage.getItem(key) || "[]"))); } catch { setRead(new Set()); }
  }, [key]);
  const save = (s: Set<string>) => { setRead(new Set(s)); try { localStorage.setItem(key, JSON.stringify([...s].slice(-400))); } catch { /* 저장소 차단 */ } };
  return { read, mark: (id: string) => { if (!read.has(id)) save(new Set([...read, id])); }, markAll: (ids: string[]) => save(new Set([...read, ...ids])) };
}

const isRecent = (d: string, days = 4) => {
  if (!d) return false;
  const t = Date.parse(d);
  return !Number.isNaN(t) && Date.now() - t <= days * 86400000 && t - Date.now() <= 14 * 86400000;
};

function Msg({ m, team, unread, onOpen, big = false }: { m: InboxMsg; team: string; unread: boolean; onOpen: () => void; big?: boolean }) {
  const peek = usePeek();
  const preview = useMatchPreview();
  const c = TONE[m.tone] || "#8a94a8";
  const act = (e: React.MouseEvent) => {
    onOpen();
    if (m.action?.kind === "match" && m.action.fixture) preview?.(m.action.fixture as Fixture);
    else if (m.action?.kind === "player" && m.action.name) peek(e, { name: m.action.name, club: team, hint: { photo: m.photo } });
  };
  return (
    <button className={`ib5-msg${big ? " big" : ""}${unread ? " unread" : ""}`} style={{ ["--tc" as string]: c }} onClick={act}>
      <span className="ib5-ic">{m.photo ? <img src={m.photo} alt="" /> : m.icon}</span>
      <span className="ib5-body">
        <span className="ib5-top"><em>{CAT_EN[m.cat] ?? m.cat.toUpperCase()}</em>{unread && <i className="ib5-new">NEW</i>}{m.date && <small>{m.date.slice(5).replace("-", "/")}</small>}</span>
        <b>{m.title}{m.player ? <span> · {m.player}</span> : null}</b>
        <span className="ib5-d">{m.detail}</span>
      </span>
      {/* 경기 리뷰가 열리는 항목 — 예전엔 '— 눌러서 경기 리뷰' 문구였다 */}
      {m.action?.kind === "match" && <span className="ib5-go" aria-hidden>›</span>}
    </button>
  );
}

function LeagueRow({ s }: { s: Signal }) {
  const peek = usePeek();
  return (
    <button className="ib5-lg" onClick={(e) => s.player && peek(e, { name: s.player, club: s.team, hint: { photo: s.photo } })}>
      <span className="ib5-lg-i">{s.icon}</span>
      {s.logo && <img src={s.logo} alt="" />}
      <span className="ib5-lg-t"><b>{s.title}{s.player ? ` · ${s.player}` : ""}</b><em>{s.team} · {s.detail}</em></span>
      {s.date && <small>{s.date.slice(5)}</small>}
    </button>
  );
}

export default function SignalsTab({ team }: { team: string; accent?: string }) {
  const [d, setD] = useState<Inbox | null>(null);
  const [cat, setCat] = useState("all");
  const [more, setMore] = useState(false);
  const { read, mark, markAll } = useRead(team);
  useEffect(() => { let a = true; setD(null); getInbox(team).then((x) => a && setD(x)).catch(() => {}); return () => { a = false; }; }, [team]);
  // '전체'에선 위 BRIEFING 3건을 목록에서 빼 중복을 없앤다(분류를 고르면 그 분류 전부)
  const list = useMemo(() => {
    if (!d) return [];
    const top = new Set(d.briefing.map((m) => m.id));
    return d.messages.filter((m) => (cat === "all" ? !top.has(m.id) : m.cat === cat));
  }, [d, cat]);
  if (!d) return <div className="skel-wrap"><SkelCards n={6} cols="repeat(auto-fill, minmax(300px, 1fr))" face={false} /></div>;
  const unread = (m: InboxMsg) => !read.has(m.id) && (isRecent(m.date) || m.cat === "match");
  const nNew = d.messages.filter(unread).length;
  const shown = more ? list : list.slice(0, 14);

  return (
    <div className="fade">
      <SectionHead title="INBOX" kr="팀 소식함" meta={`${d.messages.length}건${nNew ? ` · 새 소식 ${nNew}` : ""}`}
        info={<>
          <p>경기 일정·팀 폼·선수 폼(OVR 2주 변화)·부상·선발 제외·계약·시장가치·감독 소식을 자동으로 감지합니다.</p>
          <p className="muted">맨 위 카드 = 중요도 상위 3건. NEW = 최근 4일 안의 읽지 않은 소식(이 브라우저 기준).</p>
        </>}
        right={nNew ? <button className="ib5-all" onClick={() => markAll(d.messages.map((m) => m.id))}>모두 읽음</button> : null} />
      {d.briefing.length > 0 && (
        <div className="ib5-brief">
          {d.briefing.map((m) => <Msg key={m.id} m={m} team={team} unread={unread(m)} onOpen={() => mark(m.id)} big />)}
        </div>
      )}
      <div className="ib5-grid">
        <section className="card ib5-main">
          <div className="comp-seg chips5 ib5-chips">
            {CATS.filter(([k]) => k === "all" || d.counts[k]).map(([k, l]) => (
              <button key={k} className={cat === k ? "active" : ""} onClick={() => { setCat(k); setMore(false); }}>
                {l}<em>{k === "all" ? d.messages.length : d.counts[k]}</em>
              </button>
            ))}
          </div>
          <div className="ib5-list">
            {shown.map((m) => <Msg key={m.id} m={m} team={team} unread={unread(m)} onOpen={() => mark(m.id)} />)}
            {list.length === 0 && <p className="pv-empty">소식 없음</p>}
          </div>
          {!more && list.length > 14 && <button className="sig-more" onClick={() => setMore(true)}>{list.length - 14}건 더 보기</button>}
        </section>
        <section className="card ib5-side">
          {d.opponents && d.opponents.length > 0
            ? <SectionHead title="OPPONENT WATCH" kr="다음 상대 소식" meta={`${d.opponents.join(" · ")} · 부상·감독 · 30일`} />
            : <SectionHead title="LEAGUE WIRE" kr="리그 소식" meta="우리 팀 제외 · 30일" />}
          <div className="ib5-lglist">
            {d.league_events.map((s, i) => <LeagueRow key={i} s={s} />)}
            {d.league_events.length === 0 && <p className="pv-empty">최근 리그 소식 없음</p>}
          </div>
        </section>
      </div>
    </div>
  );
}
