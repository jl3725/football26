"use client";
import { useMemo, useState } from "react";
import type { TrackAlert, TrackType } from "@/lib/api";
import { trackKey, useTracking } from "@/lib/tracking";
import { useShortlistCounts } from "@/lib/shortlist";
import type { Pin } from "@/lib/pins";
import { usePeek } from "./PlayerPeek";
import SectionHead from "./SectionHead";
import Icon from "./Icon";
import { Skel } from "./Skeleton";
import { surname } from "@/lib/names";

// TRACKING — SHORTLIST(영입 후보)의 최근 14일 변화를 Signals 맨 위에(2026-10-23 사용자 '관심 선수 알림').
// 위 줄 = 후보 얼굴(테 색 = 가장 중요한 새 소식, 이름 아래 상태 칩), 누르면 그 후보 소식만. 아래 = 소식(종류 색·아이콘·NEW).
// 내 팀 선수 소식은 아래 INBOX 가 그대로 잡는다. 원천은 /api/tracking(이적 기록·TM 루머·뉴스 이적 단계·FotMob 경기 평점·부상·평점 추이).
type Look = { en: string; ko: string; icon: string; c: string };
const LOOK: Record<TrackType, Look> = {
  moved: { en: "MOVED", ko: "이적 완료", icon: "swap", c: "#b58cff" },
  linked: { en: "LINKED", ko: "우리 팀 연결", icon: "link", c: "" },            // 팀 색
  injury: { en: "INJURY", ko: "부상", icon: "medic", c: "#ff7285" },
  return: { en: "BACK", ko: "복귀", icon: "check", c: "#68e0a5" },
  rivals: { en: "RIVALS", ko: "다른 구단 관심", icon: "eye", c: "#f4cf5e" },
  value: { en: "VALUE", ko: "시장가치", icon: "tag", c: "#5fd3e6" },              // TM 값 변동 + 적정 이적료 범위
  match: { en: "MATCH", ko: "경기", icon: "zap", c: "#68e0a5" },
  form: { en: "FORM", ko: "폼", icon: "trend", c: "#7f9cff" },
  absent: { en: "BENCHED", ko: "출전 없음", icon: "clock", c: "#9aa3b5" },
};
const md = (d: string) => (d ? `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}` : "이번 창");
const lastName = surname;
const initials = (n: string) => n.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();

export default function Tracking({ team, accent }: { team: string; accent?: string }) {
  const t = useTracking(team);
  const peek = usePeek();
  const [sel, setSel] = useState<string | null>(null);
  const tone = (ty: TrackType) => LOOK[ty].c || accent || "var(--accent)";
  // 후보마다 가장 중요한 새 소식(테 색)
  const ring = useMemo(() => {
    const m: Record<string, TrackAlert> = {};
    for (const a of t.data?.alerts ?? []) {
      if (!t.isNew(a)) continue;
      const k = trackKey(a.player, a.club);
      if (!m[k] || a.prio > m[k].prio) m[k] = a;
    }
    return m;
  }, [t]);
  if (!t.items.length) return null;
  if (!t.data) return t.loading ? <section className="card trk"><Skel h={22} w={220} r={6} /><Skel h={78} r={14} style={{ marginTop: 14 }} /></section> : null;

  const players = t.data.players;
  const alerts = sel ? t.data.alerts.filter((a) => trackKey(a.player, a.club) === sel) : t.data.alerts;
  const open = (a: TrackAlert, e: React.MouseEvent) => {
    t.mark(a.id);
    peek(e, { name: a.player, club: a.club, league: a.league, hint: { photo: a.photo } });
  };

  return (
    <section className="card trk" style={{ ["--trk-ac" as string]: accent || "var(--accent)" }}>
      <SectionHead title="TRACKING" kr="영입 후보 소식"
        meta={`SHORTLIST ${players.length}명${t.nNew ? ` · 새 소식 ${t.nNew}` : ""}`}
        info={<>
          <p>Recruit 작업대에 고정한 후보의 최근 14일 변화 — 이적 완료 · 우리 팀 연결 · 부상·복귀 · 다른 구단 관심 · 시장가치(적정 이적료 범위) · 경기(평점 8.0+ 또는 공격포인트 2+, 부상 아닌 결장 2경기+) · 폼(OVR 2주 ±3).</p>
          <p className="muted">테 색 = 가장 중요한 새 소식. NEW = 최근 7일 안의 읽지 않은 소식(이 브라우저 기준).</p>
        </>}
        right={t.nNew ? <button className="ib5-all" onClick={() => t.markAll(t.data!.alerts.map((a) => a.id))}>모두 읽음</button> : null} />

      <div className="trk-rail" role="tablist" aria-label="후보 고르기">
        {players.map((p) => {
          const k = trackKey(p.player, p.club);
          const r = ring[k];
          return (
            <button key={k} role="tab" aria-selected={sel === k} className={`trk-p${sel === k ? " on" : ""}${r ? " hot" : ""}`}
              style={{ ["--rc" as string]: r ? tone(r.type) : "transparent" }} onClick={() => setSel(sel === k ? null : k)}
              title={`${p.player} · ${p.club}`}>
              <span className="trk-av">
                {p.photo ? <img src={p.photo} alt="" /> : <span className="trk-ini">{initials(p.player)}</span>}
                {p.logo && <img className="trk-crest" src={p.logo} alt="" />}
              </span>
              <b>{lastName(p.player)}</b>
              {p.status[0]
                ? <em className={`trk-st ${p.status[0].k}`} title={p.status[0].tip}>{p.status[0].label}</em>
                : <em className="trk-n">{p.n ? `소식 ${p.n}` : "조용함"}</em>}
            </button>
          );
        })}
      </div>

      <div className="trk-feed">
        {alerts.map((a) => {
          const L = LOOK[a.type];
          const nw = t.isNew(a);
          return (
            <button key={a.id} className={`trk-a${nw ? " new" : ""}`} style={{ ["--tc" as string]: tone(a.type) }} onClick={(e) => open(a, e)}>
              <span className="trk-ic"><Icon name={L.icon} size={18} color={tone(a.type)} /></span>
              <span className="trk-body">
                <span className="trk-top">
                  <em>{L.en}</em><span className="trk-ko">{L.ko}</span>
                  {nw && <i className="trk-new">NEW</i>}
                  <span className="trk-date">{md(a.date)}</span>
                </span>
                <span className="trk-main"><b>{a.player}</b><span>{a.title}</span></span>
                <span className="trk-sub">
                  {a.logo && <img src={a.logo} alt="" />}{a.club}{a.detail ? <> · {a.detail}</> : null}
                </span>
              </span>
            </button>
          );
        })}
        {alerts.length === 0 && <p className="trk-empty">최근 14일 소식 없음</p>}
      </div>
    </section>
  );
}

// 작업대 카드 한 줄 — 그 후보의 가장 중요한 소식
export function TrackLine({ team, player, club, accent }: { team: string; player: string; club: string; accent?: string }) {
  const t = useTracking(team);
  const p = t.data?.players.find((x) => x.requested.player === player && x.requested.club === club);
  const a = p?.top ? t.data?.alerts.find((x) => x.id === p.top) : undefined;
  if (!a) return null;
  const L = LOOK[a.type];
  const c = L.c || accent || "var(--accent)";
  return (
    <div className={`trk-line${t.isNew(a) ? " new" : ""}`} style={{ ["--tc" as string]: c }} title={`${L.ko} · ${a.title}${a.detail ? ` · ${a.detail}` : ""}`}>
      <Icon name={L.icon} size={13} color={c} />
      <em>{L.en}</em><span>{a.title}</span><small>{md(a.date)}</small>
    </div>
  );
}

// 전체 홈 요약 — ★ 내 팀 중 SHORTLIST 가 있는 팀만, 팀마다 새 소식 수 + 중요한 소식 3줄. 머리를 누르면 그 팀 Inbox(2026-10-23)
export function HomeTracking({ pins, onOpen }: { pins: Pin[]; onOpen: (team: string, league: string) => void }) {
  const counts = useShortlistCounts(pins.map((p) => p.team));
  const mine = pins.filter((_, i) => counts[i] > 0);
  if (!mine.length) return null;
  return (
    <section className="h5-sec">
      <SectionHead title="TRACKING" kr="내 팀 영입 후보 소식" meta={`★ 내 팀 ${mine.length}`}
        info={<>
          <p>팀 화면 Inbox 맨 위 TRACKING 의 요약 — ★ 고정한 팀 중 Recruit 작업대에 후보를 둔 팀만.</p>
          <p className="muted">팀마다 읽지 않은 새 소식 먼저, 중요한 순 3건. NEW = 최근 7일 안의 읽지 않은 소식(이 브라우저 기준).</p>
        </>} />
      <div className="trkh-grid">{mine.map((p) => <PinTrack key={p.team} pin={p} onOpen={onOpen} />)}</div>
    </section>
  );
}

function PinTrack({ pin, onOpen }: { pin: Pin; onOpen: (team: string, league: string) => void }) {
  const t = useTracking(pin.team, pin.league);
  const peek = usePeek();
  if (!t.items.length) return null;
  const top = t.data
    ? [...t.data.alerts].sort((a, b) => Number(t.isNew(b)) - Number(t.isNew(a)) || b.prio - a.prio || b.date.localeCompare(a.date)).slice(0, 3)
    : [];
  return (
    <div className="trkh-card">
      <button className="trkh-head" onClick={() => onOpen(pin.team, pin.league)} title={`${pin.team} Inbox 열기`}>
        {pin.logo ? <img src={pin.logo} alt="" /> : null}
        <b>{pin.team}</b>
        <span className="trkh-n">SHORTLIST {t.items.length}</span>
        {t.nNew > 0 && <i className="trk-new">NEW {t.nNew}</i>}
        <span className="trkh-go">INBOX ›</span>
      </button>
      {!t.data
        ? (t.loading ? <Skel h={96} r={10} /> : <p className="trkh-quiet">소식을 못 불러왔어요</p>)
        : top.length === 0
          ? <p className="trkh-quiet">최근 14일 조용함</p>
          : top.map((a) => {
            const L = LOOK[a.type];
            const c = L.c || "var(--accent)";
            return (
              <button key={a.id} className={`trkh-a${t.isNew(a) ? " new" : ""}`} style={{ ["--tc" as string]: c }}
                onClick={(e) => { t.mark(a.id); peek(e, { name: a.player, club: a.club, league: a.league, hint: { photo: a.photo } }); }}
                title={`${L.ko} · ${a.player} · ${a.title}${a.detail ? ` · ${a.detail}` : ""}`}>
                <Icon name={L.icon} size={14} color={c} />
                <em>{L.en}</em>
                <b>{lastName(a.player)}</b>
                <span>{a.title}</span>
                <small>{md(a.date)}</small>
              </button>
            );
          })}
    </div>
  );
}
