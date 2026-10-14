"use client";
import type { Fixture, FixtureSide } from "@/lib/api";
import { BIG, colorsClose, compLabel, compTone, ddayLabel, liftHex, powerShare, rankLabel, splitKst, whyBig } from "@/lib/match";
import { useMatchPreview } from "@/lib/matchPreview";
import { hexA } from "@/lib/ui";
import { Chevron } from "./SectionHead";

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

export default function MatchCard({ m, onPick, compact = false }: { m: Fixture; onPick?: Pick_; compact?: boolean }) {
  const preview = useMatchPreview();
  const { date, time } = splitKst(m.kst);
  const tone = compTone(m.comp_code);
  const big = m.big >= BIG;
  const open = () => preview?.(m);

  if (compact) return (
    <button className={`mc5 compact${tone === "ucl" ? " ucl" : ""}`} onClick={open} disabled={!preview}>
      <span className="mc5-ko-s"><b>{time}</b><span>{date}</span></span>
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
    <div className={`mc5${tone === "ucl" ? " ucl" : ""}${big ? " big" : ""}`} role={preview ? "button" : undefined} tabIndex={preview ? 0 : undefined}
      onClick={open} onKeyDown={(e) => { if (e.key === "Enter") open(); }}>
      <div className="mc5-top">
        <span className={`bdg ${tone}`}>{compLabel(m)}</span>
        <span className={`bdg ${m.d_day <= 1 ? "hot" : "neutral"}`}>{ddayLabel(m.d_day)}</span>
      </div>
      <div className="mc5-teams">
        <Side s={m.home} other={m.away} onPick={onPick} align="l" />
        <div className="mc5-ko"><b>{time}</b><span>{date}</span></div>
        <Side s={m.away} other={m.home} onPick={onPick} align="r" />
      </div>
      <PowerBar m={m} />
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
    <div className="mh5" style={{ ["--hc" as any]: hexA(hc, 0.34), ["--ac" as any]: hexA(ac, 0.42) }}>
      <div className="mh5-top">
        <span className={`bdg ${tone}`}>{compLabel(m)}</span>
        <span className={`bdg ${m.d_day <= 1 ? "hot" : "neutral"}`}>{ddayLabel(m.d_day)}</span>
        <span className="mh5-kicker">MATCH OF THE WEEK</span>
        <span className="mh5-score">BIG SCORE {m.big}</span>
      </div>
      <div className="mh5-teams">
        {side(m.home, m.away, false)}
        <div className="mh5-ko"><b>{time}</b><span>{date} · KST</span></div>
        {side(m.away, m.home, true)}
      </div>
      <PowerBar m={m} />
      <div className="mh5-foot">
        <span className="mc5-why"><span className="bdg neutral">WHY</span>{why}</span>
        {preview && <button className="btn5" onClick={() => preview(m)}>MATCH PREVIEW<Chevron /></button>}
      </div>
    </div>
  );
}
