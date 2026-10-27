"use client";
import { tier } from "@/lib/ui";
import { useEffect, useState } from "react";
import SectionHead from "./SectionHead";
import { activeLeague, getLineup, getProjection, type Lineup, type LineupComp, type Projection } from "@/lib/api";
import { compEn, lgEn } from "@/lib/match";
import Pitch from "./Pitch";
import { usePeek } from "./PlayerPeek";
import { SkelPitch } from "./Skeleton";
import EmptyState from "./EmptyState";
import { showNextSeason } from "@/lib/season";
import { surname } from "@/lib/names";

type Departed = { player: string; left_for: string; pos: string; photo: string };

// 대회 토글 — 리그 · 챔스 · 컵을 대회 하나하나 따로(2026-10-19 사용자: '리그·챔스·컵 각각 따로'), + 전 대회 · 최근 한 경기.
// 예전 FORMATION 은 리그 전용이었다. 목록은 서버 comp_list(선발 기록 있는 대회만, 리그 → 유럽 → 컵).
type CompBtn = { k: LineupComp; en: string; kr: string; n: number | null };

export default function LineupBoard({ team, accent, departed = [] }: { team: string; accent: string; departed?: Departed[] }) {
  const [lu, setLu] = useState<Lineup | null>(null);
  const [pj, setPj] = useState<Projection | null>(null);
  const [leftView, setLeftView] = useState<"cur" | "next">("next");
  const [err, setErr] = useState(false);
  const [comp, setComp] = useState<LineupComp>("league");
  const [list, setList] = useState<NonNullable<Lineup["comp_list"]>>([]);
  const peek = usePeek();

  useEffect(() => {
    let a = true; setPj(null); setErr(false); setLeftView("next"); setComp("league"); setList([]);
    getProjection(team).then((d) => a && setPj(d)).catch(() => a && setErr(true));
    return () => { a = false; };
  }, [team]);
  useEffect(() => {
    let a = true; setLu(null);
    getLineup(team, undefined, comp).then((d) => { if (!a) return; setLu(d); if (d.comp_list) setList(d.comp_list); })
      .catch(() => a && setErr(true));
    return () => { a = false; };
  }, [team, comp]);

  const curLabel = pj?.current_label ?? "";
  const nextLabel = pj?.next_label ?? "";
  // 시즌 중에는 '다음 시즌 예상'이 의미 없음(같은 시즌) → 현재 시즌 BEST XI 만. 예상은 리그 기준이라 다른 대회에선 숨김
  const hasNext = !!pj && showNextSeason(pj) && comp === "league";
  const view = hasNext ? leftView : "cur";
  const leftBoard = view === "cur" ? lu?.season : pj?.projected;
  const leftFormation = view === "cur" ? lu?.season.formation : pj?.projected.formation;
  // 시즌 초엔 시즌 BEST XI 와 최근 5경기 XI 가 같은 경우가 많다 — 같은 그림을 두 번 그리지 않는다
  const sig = (b?: { formation: string; placements: { slot: string; player: string }[] } | null) =>
    b ? `${b.formation}|${b.placements.map((x) => `${x.slot}:${x.player}`).sort().join(",")}` : "";
  const sameXI = view === "cur" && ((!!lu?.recent && sig(lu.season) === sig(lu.recent)) || (comp === "last" && !!lu));
  const lg = activeLeague();
  const shown: CompBtn[] = [
    ...list.map((c) => ({ k: c.key, en: c.key === "league" ? (lgEn(lg) || "LEAGUE") : (compEn(c.key) || c.name), kr: c.key === "league" ? "리그" : c.name, n: c.n })),
    ...(list.length > 1 ? [{ k: "all", en: "ALL", kr: "전 대회", n: list.reduce((s, c) => s + c.n, 0) }] : []),
    { k: "last", en: "LAST MATCH", kr: "최근 한 경기", n: null },
  ];
  if (!list.length) shown.unshift({ k: "league", en: lgEn(lg) || "LEAGUE", kr: "리그", n: null });
  const compKr = shown.find((c) => c.k === comp)?.kr ?? "";
  const lm = lu?.last_match;
  const lmComp = lm && lm.code && lm.code !== comp ? (lm.code === "league" ? (lgEn(lg) || "리그") : (compEn(lm.code) || lm.comp || "")) : "";
  const lmTxt = lm ? `${lm.date.slice(5).replace("-", "/")} ${lm.home_away === "away" ? "@ " : "vs "}${lm.opponent}${lmComp ? ` (${lmComp})` : ""}` : "";
  const emptyComp = !!lu && lu.season.placements.length === 0;

  const bench = lu?.bench && lu.bench.length > 0 ? (
    <div className="bench-strip">
      <div className="bench-title">벤치 뎁스</div>
      {lu.bench.map((b, i) => (
        <div className="bench-chip peekable" key={i}
          onClick={(e) => peek(e, { name: b.player, club: team, hint: { photo: b.photo, ovr: b.ovr, pos: b.pos } })}>
          {b.photo ? <img src={b.photo} alt="" /> : <span className="bench-ph" />}
          <span className="bench-name">{surname(b.player)}</span>
          <span className="bench-ovr" style={{ color: tier(b.ovr).light }} title={`OVR ${b.ovr} · ${tier(b.ovr).ko}`}>{b.ovr}</span>
        </div>
      ))}
    </div>
  ) : null;
  const gone = departed.length > 0 ? (
    <div className="bench-strip departed">
      <div className="bench-title">↪ 떠난 선수</div>
      {departed.map((d, i) => (
        <div className="bench-chip peekable" key={i}
          onClick={(e) => peek(e, { name: d.player, hint: { photo: d.photo, pos: d.pos } })}>
          {d.photo ? <img src={d.photo} alt="" /> : <span className="bench-ph" />}
          <span className="bench-name">{surname(d.player)}</span>
          <span className="bench-to">→ {d.left_for}</span>
        </div>
      ))}
    </div>
  ) : null;

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <SectionHead title="FORMATION" kr="포메이션 · 베스트 XI"
        meta={lm ? `${Number(lm.date.slice(5, 7))}/${Number(lm.date.slice(8, 10))} 반영` : undefined}
        info={<>
          {lm
            ? <p><b>기준</b> = {comp === "last" ? "그 경기 선발 그대로" : `${compKr} — 선수마다 가장 많이 선 자리`}.</p>
            : <p><b>기준</b> = 시즌 평점 기준 XI · 최근 5경기 XI.</p>}
          {lm && <p><b>마지막 반영</b> = {lmTxt}</p>}
          <p className="muted">라인업은 경기 다음 날 아침 갱신됩니다.</p>
        </>}
        right={shown.length > 1 ? <div className="seg5 seg5-head" role="tablist" aria-label="대회">
          {shown.map((c) => (
            <button key={c.k} role="tab" aria-selected={comp === c.k} className={comp === c.k ? "on" : ""} title={`${c.kr}${c.n ? ` · 선발 기록 ${c.n}경기` : ""}`}
              onClick={() => { setComp(c.k); if (c.k !== "league") setLeftView("cur"); }}>
              {c.en}{c.n ? <em className="seg5-n">{c.n}</em> : null}</button>
          ))}
        </div> : undefined} />
      <div className={`pitch-grid${sameXI ? " single" : ""}`}>
        {/* LEFT — 시즌 베스트 XI + 시즌 토글 */}
        <div>
          <div className="proj-toggle" style={{ marginBottom: 10 }}>
            {hasNext && <button className={view === "next" ? "active" : ""} onClick={() => setLeftView("next")}
              style={view === "next" ? { background: accent, color: "#0b0f17" } : undefined}>🔮 {nextLabel} 예상</button>}
            <button className={view === "cur" ? "active" : ""} onClick={() => setLeftView("cur")}
              style={view === "cur" ? { background: accent, color: "#0b0f17" } : undefined}>
              {comp === "last" ? `LAST MATCH · ${lmTxt}` : `${curLabel} ${comp === "league" ? "" : `${compKr} `}BEST XI`}</button>
          </div>
          {emptyComp
            ? <EmptyState title="이 대회 라인업 없음" note="경기가 아직 없거나 미수집" />
            : leftBoard
            ? <Pitch placements={leftBoard.placements} accent={accent} team={team} />
            : err ? <EmptyState title="라인업을 불러오지 못했습니다" note="잠시 후 다시 열어 주세요" />
            : <SkelPitch />}
          <div className="pitch-cap">
            {sameXI && comp !== "last" && (lu?.season.matches ?? 6) > 5 ? <>최근 5경기와 같은 XI · </> : null}
            {view === "cur" && lu?.season.matches && comp !== "last" ? <>{lu.season.matches}경기 · </> : null}<span>{leftFormation || ""}</span>
          </div>
        </div>

        {/* RIGHT — 시즌 BEST XI 와 같으면 피치 대신 XI 요약·벤치·떠난 선수(예전엔 피치 하나가 가운데 떠 양옆이 비었다) */}
        {sameXI && leftBoard && !emptyComp && (
          <div className="xi-side">
            <XiSummary placements={leftBoard.placements} formation={leftFormation || ""} accent={accent} />
            {bench}
            {gone}
          </div>
        )}
        {!sameXI && !emptyComp && <div>
          <div className="proj-toggle" style={{ marginBottom: 10, visibility: "hidden" }}>
            <button>_</button>
          </div>
          {lu?.recent
            ? <Pitch placements={lu.recent.placements} accent={accent} team={team} />
            : lu ? <div className="loading" style={{ padding: 30 }}>최근 경기 데이터 부족</div> : <SkelPitch />}
          <div className="pitch-cap">{comp === "league" ? "" : `${compKr} `}최근 {lu?.recent?.matches ?? 5}경기 <span>{lu?.recent?.formation || ""}</span></div>
        </div>}
      </div>

      {/* 26/27 예상 효과 — 이탈/보강 진단 */}
      {view === "next" && pj && pj.diagnosis.length > 0 && (
        <div className="effect-box">
          <div className="effect-title" style={{ color: accent }}>{nextLabel} 이적 반영 효과</div>
          <div className="effect-grid">
            {pj.diagnosis.map((d, i) => (
              <div className={`effect-row ${d.kind} peekable`} key={i}
                onClick={(e) => peek(e, { name: d.player, club: d.kind === "loss" ? undefined : team, hint: { photo: d.photo } })}>
                {d.photo ? <img src={d.photo} alt="" /> : <span className="effect-ph" />}
                <div className="effect-body">
                  <div className="effect-top">
                    <span className="effect-ar">{d.kind === "loss" ? "▼" : "▲"}</span>
                    <b>{d.player}</b><span className="effect-tag">{d.slot}</span>
                  </div>
                  <div className="effect-note">{d.kind === "loss" ? `→ ${d.to || "이적"} · ` : ""}{d.note}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 벤치 + 이적 이탈 — 같은 XI(피치 하나)면 이미 오른쪽 칸에 있다 */}
      {!sameXI && bench}
      {!sameXI && gone}
    </div>
  );
}

// XI 요약 — 포메이션 · XI 평균 OVR · 라인별 평균(수비·중원·공격)
function XiSummary({ placements, formation, accent }: { placements: { kind: string; ovr: number | null }[]; formation: string; accent: string }) {
  const avg = (ks: string[]) => {
    const v = placements.filter((p) => ks.includes(p.kind) && p.ovr != null).map((p) => p.ovr as number);
    return v.length ? Math.round(v.reduce((a, b) => a + b, 0) / v.length) : null;
  };
  const rows: [string, string, number | null][] = [
    ["XI 평균", "XI", avg(["GK", "DEF", "MID", "FWD"])], ["수비", "DEF", avg(["GK", "DEF"])],
    ["중원", "MID", avg(["MID"])], ["공격", "ATT", avg(["FWD"])],
  ];
  return (
    <div className="xi-sum">
      <div className="xi-sum-f"><em>FORMATION</em><b>{formation || "—"}</b></div>
      {rows.map(([kr, en, v]) => (
        <div className="xi-sum-r" key={en}>
          <span>{en}<em>{kr}</em></span>
          <i><span style={{ width: `${v ?? 0}%`, background: accent }} /></i>
          <b>{v ?? "—"}</b>
        </div>
      ))}
    </div>
  );
}
