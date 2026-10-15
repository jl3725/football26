"use client";
import type { Fixture, FixtureSide } from "@/lib/api";
import { BIG, colorsClose, compLabel, compTone, ddayLabel, liftHex, powerShare, rankLabel, splitKst, whyBig } from "@/lib/match";
import { useMatchPreview } from "@/lib/matchPreview";
import { hexA } from "@/lib/ui";
import { Chevron } from "./SectionHead";
import { useLive, liveLabel, type LiveEvent } from "@/lib/live";

// 라이브 상태 배지·가운데 스코어 — 진행 중이면 빨간 LIVE·경기 시간, 끝났으면 FT(일정은 하루 갱신이라 화면이 먼저 안다)
function StateBadge({ m, lv }: { m: Fixture; lv?: LiveEvent }) {
  if (lv?.state === "in") return <span className="bdg live"><i />LIVE {liveLabel(lv)}</span>;
  if (lv?.state === "post") return <span className="bdg ft">{liveLabel(lv)}</span>;
  return <span className={`bdg ${m.d_day <= 1 ? "hot" : "neutral"}`}>{ddayLabel(m.d_day)}</span>;
}
function Center({ lv, time, date, cls, sub }: { lv?: LiveEvent; time: string; date: string; cls: string; sub?: string }) {
  if (lv && lv.state !== "pre") {
    const h = lv.home.score ?? "0", a = lv.away.score ?? "0";
    return (
      <div className={`${cls} score${lv.state === "in" ? " in" : ""}`}>
        <b><span className={lv.home.winner ? "w" : ""}>{h}</span><em>:</em><span className={lv.away.winner ? "w" : ""}>{a}</span></b>
        <span>{lv.state === "in" ? <><i className="live-dot" />{liveLabel(lv)}</> : `${liveLabel(lv)} · ${date}`}</span>
      </div>
    );
  }
  return <div className={cls}><b>{time}</b><span>{sub ?? date}</span></div>;
}

// 경기 카드(디자인 v5) — 글로벌 빅매치·리그 '이번 주 경기'·팀 '다음 경기' 공용.
// 가운데는 'vs' 대신 킥오프(한국 시간)를 크게, 최근 결과는 색 + 글자(W/D/L), 빅매치면 '왜?' 한 줄.
// 카드를 누르면 매치 프리뷰 서랍(components/MatchPreview.tsx). 일정은 daily_data 가 매일 갱신.

export function FormBoxes({ form }: { form: string[] }) {
  if (!form.length) return null;
  return <span className="fbx" aria-label={`최근 ${form.length}경기 ${form.join(" ")}`}>{form.map((r, i) => <i key={i} className={`fbx-${r}`}>{r}</i>)}</span>;
}

export function Crest({ s, size }: { s: Pick<FixtureSide, "logo" | "color">; size: number }) {
  return s.logo
    ? <img className="crest" src={s.logo} alt="" style={{ width: size, height: size }} />
    : <span className="crest ph" style={{ width: size, height: size, background: s.color }} />;
}

type Pick_ = (team: string, league?: string | null) => void;

function Side({ s, other, onPick, align, size = 52 }: { s: FixtureSide; other: FixtureSide; onPick?: Pick_; align: "l" | "r"; size?: number }) {
  return (
    <button className={`mc5-side ${align}`} disabled={!onPick || !s.league} title={s.league ? `${s.team} 팀 화면` : s.team}
      onClick={(e) => { e.stopPropagation(); if (onPick && s.league) onPick(s.team, s.league); }}>
      <Crest s={s} size={size} />
      <span className="mc5-team">{s.team}</span>
      {s.rank ? <span className="mc5-rank">{rankLabel(s, other)}</span> : null}
      <FormBoxes form={s.form} />
    </button>
  );
}

export function PowerBar({ m }: { m: Fixture }) {
  const share = powerShare(m);
  if (share === null) return null;
  const hc = liftHex(m.home.color), ac0 = liftHex(m.away.color);
  const ac = colorsClose(hc, ac0) ? "#8a94a8" : ac0;
  return (
    <div className="mc5-power" title={`팀 OVR ${m.home.ovr} : ${m.away.ovr}`}>
      <div className="mc5-power-l"><b>{m.home.ovr}</b><span>TEAM OVR</span><b>{m.away.ovr}</b></div>
      <div className="mc5-bar"><span style={{ flexBasis: `${share}%`, background: hc }} /><span style={{ flexBasis: `${100 - share}%`, background: ac }} /></div>
    </div>
  );
}

// 승리 확률(모델) — 홈 · 무 · 원정. 확률이 없으면(전력 모름) 전력 막대로
// 승부 예측 — 팬 투표(Sofascore 사용자 '누가 이길까?') 우선, 없으면 ClubElo(독립 Elo 모델).
// 둘 다 없으면(챔스 일부·수집 전) 팀 OVR 전력 막대로. 우리 자체 계산 확률은 보여 주지 않는다(사용자 피드백).
type Probs = { h: number; d: number; a: number };
const favOf = (v: Probs) => (v.h >= v.d && v.h >= v.a ? "h" : v.a >= v.d ? "a" : "d");

// 승부 예측 — 팬 투표(Sofascore) ↔ 우리 모델 두 줄 비교. 하나만 있으면 한 줄, 둘 다 없으면 ClubElo, 그것도 없으면 전력 막대.
// 두 예측의 가장 높은 결과가 다르면 '의견 갈림'(팬과 데이터가 다르게 본 경기).
export function PredictBar({ m, detail = false, slim = false, only }: { m: Fixture; detail?: boolean; slim?: boolean; only?: "fans" | "model" | "elo" }) {
  const hc = liftHex(m.home.color), ac0 = liftHex(m.away.color);
  const ac = colorsClose(hc, ac0) ? "#8a94a8" : ac0;
  const pc = (x: number) => `${Math.round(x * 100)}%`;
  type Row = { key: "fans" | "model" | "elo"; label: string; v: Probs; tip: string };
  const all: (Row | null)[] = [
    m.fans ? { key: "fans", label: "FANS", v: m.fans, tip: `팬 투표 — Sofascore 사용자 ${m.fans.n.toLocaleString()}표` } : null,
    m.model ? { key: "model", label: "MODEL", v: m.model, tip: "우리 예측 모델 — 경기 내용(xG·득실)과 선수 평점 기반 통계 모델" } : null,
  ];
  let rows = all.filter((r): r is Row => !!r && (!only || r.key === only));
  if (!rows.length && m.elo && (!only || only === "elo")) rows = [{ key: "elo", label: "CLUBELO", v: m.elo, tip: "ClubElo — 유럽 클럽 Elo 레이팅 기반 독립 예측" }];
  if (!rows.length) return slim || only ? null : <PowerBar m={m} />;
  const split = rows.length === 2 && favOf(rows[0].v) !== favOf(rows[1].v);
  return (
    <div className={`pb5 duo${slim ? " slim" : ""}`}>
      {rows.map((r) => {
        const fav = favOf(r.v);
        return (
          <div className={`pb5-row ${r.key}`} key={r.key}
            title={`${r.tip} — ${m.home.team} ${pc(r.v.h)} · 무 ${pc(r.v.d)} · ${m.away.team} ${pc(r.v.a)}`}>
            <span className="pb5-who">{r.label}</span>
            <b className={fav === "h" ? "fav" : ""}>{pc(r.v.h)}</b>
            <div className="pb5-bar">
              <span style={{ flexBasis: `${r.v.h * 100}%`, background: hc }} />
              <span className={`draw${fav === "d" ? " fav" : ""}`} style={{ flexBasis: `${r.v.d * 100}%` }} />
              <span style={{ flexBasis: `${r.v.a * 100}%`, background: ac }} />
            </div>
            <b className={fav === "a" ? "fav" : ""}>{pc(r.v.a)}</b>
          </div>
        );
      })}
      {!slim && (
        <div className="pb5-foot">
          {split && <span className="pb5-split">의견 갈림</span>}
          <span>무승부 {rows.map((r) => `${r.label === "FANS" ? "팬" : r.label === "MODEL" ? "모델" : "Elo"} ${pc(r.v.d)}`).join(" · ")}</span>
          {m.model && rows.some((r) => r.key === "model") && <span>모델 예상 스코어 <b>{m.model.score}</b></span>}
          {detail && m.fans && <span className="pb5-n">팬 {m.fans.n.toLocaleString()}표</span>}
        </div>
      )}
    </div>
  );
}

export default function MatchCard({ m, onPick, compact = false }: { m: Fixture; onPick?: Pick_; compact?: boolean }) {
  const preview = useMatchPreview();
  const { date, time } = splitKst(m.kst);
  const tone = compTone(m.comp_code);
  const big = m.big >= BIG;
  const open = () => preview?.(m);
  const lv = useLive(m.event_id);
  const played = lv && lv.state !== "pre";

  if (compact) return (
    <button className={`mc5 compact${tone === "ucl" ? " ucl" : ""}${lv?.state === "in" ? " is-live" : ""}`} onClick={open} disabled={!preview}>
      {played
        ? <span className="mc5-ko-s score"><b>{lv!.home.score ?? 0}:{lv!.away.score ?? 0}</b><span className={lv!.state === "in" ? "in" : ""}>{liveLabel(lv!)}</span></span>
        : <span className="mc5-ko-s"><b>{time}</b><span>{date}</span></span>}
      <span className="mc5-rows">
        {([[m.home, m.away], [m.away, m.home]] as const).map(([s, o], i) => (
          <span className="mc5-row" key={i}><Crest s={s} size={20} /><b>{s.team}</b>{s.rank ? <em>{rankLabel(s, o)}</em> : null}</span>
        ))}
      </span>
      <span className="mc5-right">
        <span className={`bdg ${tone}`}>{compLabel(m)}</span>
        {m.home.ovr && m.away.ovr ? <span className="mc5-pair">{m.home.ovr} : {m.away.ovr}</span> : null}
      </span>
    </button>
  );

  const why = big ? whyBig(m, true) : "";
  return (
    <div className={`mc5${tone === "ucl" ? " ucl" : ""}${big ? " big" : ""}${lv?.state === "in" ? " is-live" : ""}`} role={preview ? "button" : undefined} tabIndex={preview ? 0 : undefined}
      onClick={open} onKeyDown={(e) => { if (e.key === "Enter") open(); }}>
      <div className="mc5-top">
        <span className={`bdg ${tone}`}>{compLabel(m)}</span>
        <StateBadge m={m} lv={lv} />
      </div>
      <div className="mc5-teams">
        <Side s={m.home} other={m.away} onPick={onPick} align="l" />
        <Center lv={lv} time={time} date={date} cls="mc5-ko" />
        <Side s={m.away} other={m.home} onPick={onPick} align="r" />
      </div>
      <PredictBar m={m} />
      <div className="mc5-foot">
        {why ? <span className="mc5-why"><em>WHY</em>{why}</span> : <span />}
        {preview && <span className="mc5-cta">PREVIEW<Chevron /></span>}
      </div>
    </div>
  );
}

// 홈 맨 위 — 이번 주 최대 빅매치 하나를 크게(양 팀 색 그라데이션)
export function MatchHero({ m, onPick }: { m: Fixture; onPick?: Pick_ }) {
  const preview = useMatchPreview();
  const { date, time } = splitKst(m.kst);
  const tone = compTone(m.comp_code);
  const hc = liftHex(m.home.color), ac = liftHex(m.away.color);
  const why = whyBig(m);
  const lv = useLive(m.event_id);
  const side = (s: FixtureSide, o: FixtureSide, r: boolean) => (
    <button className={`mh5-side${r ? " r" : ""}`} disabled={!onPick || !s.league}
      onClick={() => { if (onPick && s.league) onPick(s.team, s.league); }} title={s.league ? `${s.team} 팀 화면` : s.team}>
      <Crest s={s} size={88} />
      <span className="mh5-info">
        <span className="mh5-team">{s.team}</span>
        <span className="mh5-meta">{[rankLabel(s, o), s.points != null ? `${s.points}점` : ""].filter(Boolean).join(" · ")}</span>
        <FormBoxes form={s.form} />
      </span>
    </button>
  );
  return (
    <div className={`mh5${lv?.state === "in" ? " is-live" : ""}`} style={{ ["--hc" as any]: hexA(hc, 0.34), ["--ac" as any]: hexA(ac, 0.42) }}>
      <div className="mh5-top">
        <span className={`bdg ${tone}`}>{compLabel(m)}</span>
        <StateBadge m={m} lv={lv} />
        <span className="mh5-kicker">MATCH OF THE WEEK{lv?.state === "post" ? " · FULL TIME" : lv?.state === "in" ? " · LIVE" : ""}</span>
        <span className="mh5-score">BIG SCORE {m.big}</span>
      </div>
      <div className="mh5-teams">
        {side(m.home, m.away, false)}
        <Center lv={lv} time={time} date={date} cls="mh5-ko" sub={`${date} · KST`} />
        {side(m.away, m.home, true)}
      </div>
      <PredictBar m={m} detail />
      <div className="mh5-foot">
        <span className="mc5-why"><span className="bdg neutral">WHY</span>{why}</span>
        {preview && <button className="btn5" onClick={() => preview(m)}>MATCH PREVIEW<Chevron /></button>}
      </div>
    </div>
  );
}
