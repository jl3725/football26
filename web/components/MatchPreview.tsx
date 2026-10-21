"use client";
import { useLiveFixture } from "@/lib/standings";
import FormPair from "./FormPair";
import { useCallback, useEffect, useState } from "react";
import { getOverview, type Fixture, type FixtureSide, type Overview, type ResultMatch } from "@/lib/api";
import { liveLabel, useLive } from "@/lib/live";
import { colorsClose, compLabel, compTone, ddayLabel, lgKo, liftHex, rankLabel, streak } from "@/lib/match";
import { MatchPreviewCtx } from "@/lib/matchPreview";
import { futTier, hexA } from "@/lib/ui";
import { TONE, ovrMeaning, type Meaning } from "@/lib/meaning";
import { MeaningTag } from "./Meaning";
import { Crest, FormBoxes, PredictBar } from "./MatchCard";
import { usePeek, useOpenTeam } from "./PlayerPeek";
import { Skel } from "./Skeleton";
import { ReviewSections } from "./MatchReview";
import Info from "./Info";

// 매치 서랍 — 경기 카드를 누르면 열린다. 두 팀 Overview(전력·폼·핵심 선수·결장)를 불러
// 규칙으로 '관전 포인트'를 만든다(유료 AI 없음). 데이터는 매일 자동 갱신분 그대로.
// 진행 중·끝난 경기면 맨 위에 경기 리뷰(MatchReview — ESPN 경기 상세 기반)를 붙이고 경기 전 예측·관전 포인트는 접는다.

const UNITS: [string, "overall" | "attack" | "midfield" | "defense"][] = [["OVERALL", "overall"], ["ATTACK", "attack"], ["MIDFIELD", "midfield"], ["DEFENSE", "defense"]];
const KO_UNIT: Record<string, string> = { ATTACK: "공격", MIDFIELD: "중원", DEFENSE: "수비" };
const adv = (d: number): Meaning => ({ label: `+${d} 우위`, tone: "good", ...TONE.good });

function keyPoints(m: Fixture, H: Overview | null, A: Overview | null): string[] {
  const out: string[] = [];
  const h = m.home, a = m.away;
  for (const s of [h, a]) {
    const w = streak(s.form, "W"), l = streak(s.form, "L");
    if (w >= 3) out.push(`${s.team} 리그 최근 ${w}연승`);
    else if (l >= 2) out.push(`${s.team} 리그 최근 ${l}연패`);
  }
  if (h.rank && a.rank && h.league && h.league === a.league && h.points != null && a.points != null) {
    out.push(`${h.rank}위 vs ${a.rank}위 · 승점 차 ${Math.abs(h.points - a.points)}`);
  }
  if (H && A) {
    const diffs = UNITS.slice(1).map(([k, u]) => [k, H.ovr[u] - A.ovr[u]] as const);
    const [k, d] = diffs.reduce((x, y) => (Math.abs(y[1]) > Math.abs(x[1]) ? y : x));
    if (Math.abs(d) >= 2) out.push(`${KO_UNIT[k]} 전력 ${d > 0 ? h.team : a.team} 우세 (OVR ${Math.abs(d)} 차)`);
    const hEdge = H.ovr.attack - A.ovr.defense, aEdge = A.ovr.attack - H.ovr.defense;
    if (Math.abs(hEdge - aEdge) >= 3) {
      out.push(hEdge > aEdge
        ? `${h.team} 공격(OVR ${H.ovr.attack}) vs ${a.team} 수비(OVR ${A.ovr.defense}) 싸움이 열쇠`
        : `${a.team} 공격(OVR ${A.ovr.attack}) vs ${h.team} 수비(OVR ${H.ovr.defense}) 싸움이 열쇠`);
    }
    const starOut = (o: Overview) => o.stars.filter((s) => o.injuries.some((i) => i.player === s.player)).map((s) => s.player);
    const so = [...starOut(H), ...starOut(A)];
    if (so.length) out.push(`핵심 선수 결장: ${so.join(", ")}`);
    else if (H.injuries.length + A.injuries.length > 0) out.push(`결장 ${h.team} ${H.injuries.length}명 · ${a.team} ${A.injuries.length}명`);
  }
  return out.slice(0, 5);
}

function Drawer({ m: m0, onClose }: { m: Fixture; onClose: () => void }) {
  const m = useLiveFixture(m0);   // 순위·승점 차 = 잠정 순위
  const [H, setH] = useState<Overview | null | undefined>(undefined);
  const [A, setA] = useState<Overview | null | undefined>(undefined);
  const peek = usePeek();
  const openTeam = useOpenTeam();
  useEffect(() => {
    let alive = true;
    const load = (s: FixtureSide, set: (o: Overview | null) => void) =>
      s.league ? getOverview(s.team, s.league).then((o) => alive && set(o)).catch(() => alive && set(null)) : set(null);
    load(m0.home, setH); load(m0.away, setA);   // 원래 경기 기준 — 잠정 순위가 30초마다 바뀌어도 다시 받지 않게
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => { alive = false; window.removeEventListener("keydown", esc); };
  }, [m0, onClose]);

  const lv = useLive(m.event_id);
  const res = (m as ResultMatch).home && "goals" in m.home ? (m as ResultMatch) : null;   // 결과 띠에서 연 경기
  const state = lv?.state ?? (res || m.d_day < 0 ? "post" : "pre");
  const score = lv && lv.state !== "pre" ? { h: Number(lv.home.score ?? 0), a: Number(lv.away.score ?? 0) }
    : res ? { h: res.home.goals, a: res.away.goals } : null;
  const ours = !!(m.home.league || m.away.league);   // 우리가 다루는 리그 팀이 없으면(유럽대회 상대끼리) 전력·결장 섹션 생략
  const loading = H === undefined || A === undefined;
  const hc = liftHex(m.home.color || lv?.home.color || "#8a94a8"), ac0 = liftHex(m.away.color || lv?.away.color || "#8a94a8");   // 일정 밖 경기는 ESPN 팀 색
  const ac = colorsClose(hc, ac0) ? "#8a94a8" : ac0;   // 비슷한 색이면 원정은 중립색(막대가 한 덩어리로 보이지 않게)
  const pts = loading ? [] : keyPoints(m, H ?? null, A ?? null);
  const go = (s: FixtureSide) => { if (s.league && openTeam) { onClose(); openTeam(s.team, s.league); } };

  const head = (s: FixtureSide, o: FixtureSide) => (
    <div className="pv-side">
      <Crest s={s} size={64} />
      <b>{s.team}</b>
      <span>
        {[rankLabel(s, o) || lgKo(s.league), s.ovr ? `OVR ${s.ovr}` : ""].filter(Boolean).join(" · ")}
        {s.ovr ? <> <MeaningTag sm m={ovrMeaning(s.ovr)} title={`팀 전력 OVR ${s.ovr} — ${ovrMeaning(s.ovr).label} 수준`} /></> : null}
      </span>
    </div>
  );

  return (
    <>
      <button className="pv-scrim" aria-label="프리뷰 닫기" onClick={onClose} />
      <aside className="pv" role="dialog" aria-modal="true" aria-label={`${m.home.team} 대 ${m.away.team} ${state === "pre" ? "매치 프리뷰" : "경기 리뷰"}`}>
        <header className="pv-head" style={{ ["--hc" as any]: hexA(hc, 0.32), ["--ac" as any]: hexA(ac, 0.38) }}>
          <div className="pv-top">
            <span className={`bdg ${compTone(m.comp_code)}`}>{compLabel(m)}</span>
            {state === "in" ? <span className="bdg live"><i className="live-dot" />LIVE {lv ? liveLabel(lv) : ""}</span>
              : state === "post" ? <span className="bdg ft">{lv ? liveLabel(lv) : "FT"}</span>
              : <span className={`bdg ${m.d_day <= 1 ? "hot" : "neutral"}`}>{ddayLabel(m.d_day)}</span>}
            {m.kst && <span className="pv-when">{m.kst} KST</span>}
            <button className="pv-x" onClick={onClose} aria-label="닫기">×</button>
          </div>
          <div className="pv-teams">{head(m.home, m.away)}
            {score ? <span className={`pv-score${state === "in" ? " is-live" : ""}`}><span className={score.h > score.a ? "w" : ""}>{score.h}</span>–<span className={score.a > score.h ? "w" : ""}>{score.a}</span></span>
              : <span className="pv-vs">VS</span>}
            {head(m.away, m.home)}</div>
        </header>

        <div className="pv-body">
          {state !== "pre" && m.event_id && <ReviewSections m={m} inPlay={state === "in"} hc={hc} ac={ac} />}
          {state !== "post" && (m.fans || m.elo || m.model) && (
            <section>
              <h3>PREDICTIONS<span>팬 투표 vs 우리 모델</span>
                <Info label="PREDICTIONS 설명">
                  <ul>
                    <li><b>FANS</b> — Sofascore 앱 사용자 투표</li>
                    <li><b>MODEL</b> — 이 사이트의 데이터 모델</li>
                    <li><b>CLUBELO</b> — clubelo.com 의 공개 예측(유럽 클럽 Elo 레이팅 기반 독립 예측)</li>
                  </ul>
                  <p className="muted">한쪽이 10%p 넘게 높으면 그 칸을 강조합니다. 재미로 보는 정보이며 베팅 정보가 아닙니다.</p>
                </Info></h3>
              <PredictBar m={m} detail />
              {(m.fans || m.model) && (
                <div className="pv-vs-grid">
                  <div className="pv-vs-h"><span /><b>FANS</b><b>MODEL</b></div>
                  {([["홈 승", m.fans?.h, m.model?.h], ["무승부", m.fans?.d, m.model?.d], ["원정 승", m.fans?.a, m.model?.a],
                    ["양 팀 득점", m.fans?.btts, m.model?.btts], ["2.5골 이상", null, m.model?.o25]] as [string, number | null | undefined, number | undefined][])
                    .filter(([, f, mo]) => f != null || mo != null)
                    .map(([k, f, mo]) => (
                      <div className="pv-vs-r" key={k}>
                        <span>{k === "홈 승" ? `${m.home.team} 승` : k === "원정 승" ? `${m.away.team} 승` : k}</span>
                        <b className={f != null && mo != null && f > mo + 0.1 ? "hi" : ""}>{f != null ? `${Math.round(f * 100)}%` : "—"}</b>
                        <b className={f != null && mo != null && mo > f + 0.1 ? "hi" : ""}>{mo != null ? `${Math.round(mo * 100)}%` : "—"}</b>
                      </div>
                    ))}
                </div>
              )}
              {m.model && (
                <div className="pv-model">
                  <div className="pv-src">MODEL <em>예상 득점 {m.model.xg_h.toFixed(2)} : {m.model.xg_a.toFixed(2)} · 유력 스코어 {m.model.score}</em>
                    <Info label="MODEL 설명" wide>
                      <p>이번 시즌 경기 내용(xG·득실, 상대 강도 보정 · 최근 경기일수록 무게)과 선수 평점(OVR), 지난 시즌부터의 팀 Elo,
                        부상·출장정지 결장 전력을 합친 통계 모델입니다.
                        {m.model.n_h + m.model.n_a < 10 ? " 아직 리그 경기가 적어 선수 평점 비중이 큽니다." : ""}</p>
                      {m.model.inputs && (
                        <ul>
                          <li><b>최근 흐름 가중</b> — 최근 40일 경기에 더 무게(시즌 초 경기보다 지금 흐름)</li>
                          {m.model.inputs.elo_d != null && <li><b>Elo 차</b> — 팀 Elo(지난 시즌부터 리그·컵·유럽 결과로 계산) {m.home.team} {m.model.inputs.elo_h ?? "?"} · {m.away.team} {m.model.inputs.elo_a ?? "?"}</li>}
                          {(m.model.inputs.miss_h != null || m.model.inputs.miss_a != null) && <li><b>결장 손실</b> — 부상·출장정지로 빠진 선수 때문에 줄어든 베스트 11 평균 OVR(Transfermarkt + FotMob 결장 명단)</li>}
                          {(m.model.inputs.intl_h != null || m.model.inputs.intl_a != null) && <li><b>A매치 복귀</b> — A매치 기간 직후 첫 경기에 대표팀에 다녀온 선수 수(유럽 밖 = 장거리 이동). 효과를 검증할 과거 소집 기록이 없어 확률 계산에는 넣지 않은 참고값</li>}
                        </ul>
                      )}
                    </Info>
                  </div>
                  {m.model.inputs && (
                    <div className="pv-inputs">
                      <span title="최근 40일 경기에 더 무게 — 시즌 초 경기보다 지금 흐름">최근 흐름 가중</span>
                      {m.model.inputs.elo_d != null && (
                        <span title={`팀 Elo(지난 시즌부터 리그·컵·유럽 결과로 계산) ${m.home.team} ${m.model.inputs.elo_h ?? "?"} · ${m.away.team} ${m.model.inputs.elo_a ?? "?"}`}>
                          Elo 차 <b className={m.model.inputs.elo_d >= 0 ? "up" : "dn"}>{m.model.inputs.elo_d >= 0 ? "+" : ""}{Math.round(m.model.inputs.elo_d)}</b>
                        </span>
                      )}
                      {(m.model.inputs.miss_h != null || m.model.inputs.miss_a != null) && (
                        <span title="부상·출장정지로 빠진 선수 때문에 줄어든 베스트 11 평균 OVR(Transfermarkt + FotMob 결장 명단)">
                          결장 손실 {m.home.team} <b>−{(m.model.inputs.miss_h ?? 0).toFixed(1)}</b> · {m.away.team} <b>−{(m.model.inputs.miss_a ?? 0).toFixed(1)}</b>
                        </span>
                      )}
                      {(m.model.inputs.intl_h != null || m.model.inputs.intl_a != null) && (
                        <span title="A매치 기간 직후 첫 경기 — 대표팀에 다녀온 선수(유럽 밖 = 장거리 이동). 참고용이며 확률 계산에는 넣지 않았습니다(효과를 검증할 과거 소집 기록이 없음)">
                          A매치 복귀 {m.home.team} <b>{m.model.inputs.intl_h ?? 0}</b>{m.model.inputs.intl_far_h ? `(유럽 밖 ${m.model.inputs.intl_far_h})` : ""}
                          {" · "}{m.away.team} <b>{m.model.inputs.intl_a ?? 0}</b>{m.model.inputs.intl_far_a ? `(유럽 밖 ${m.model.inputs.intl_far_a})` : ""}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )}
              {m.fans?.first_h != null && m.fans.first_a != null && (
                <div className="pv-side-votes">
                  <span>팬 투표 선제골 <b>{m.home.team} {Math.round(m.fans.first_h * 100)}%</b> · <b>{m.away.team} {Math.round(m.fans.first_a * 100)}%</b></span>
                </div>
              )}
              {m.elo && (
                <div className="pv-elo">
                  <div className="pv-src">CLUBELO <em>참고</em>
                    <Info label="CLUBELO 설명"><p>clubelo.com 의 유럽 클럽 Elo 레이팅으로 낸 독립 예측입니다(참고용).</p></Info>
                  </div>
                  <PredictBar m={m} only="elo" slim />
                </div>
              )}
              <p className="pv-note">재미로 보는 정보 · 베팅 정보 아님</p>
            </section>
          )}

          {state === "pre" && <section>
            <h3>KEY POINTS<span>관전 포인트</span></h3>
            {loading ? <><Skel h={14} style={{ marginBottom: 8 }} /><Skel h={14} w="80%" /></>
              : pts.length ? <ul className="pv-points">{pts.map((p) => <li key={p}>{p}</li>)}</ul>
              : <p className="pv-empty">데이터 부족 · 요약 없음</p>}
          </section>}

          {ours && <>
          <section>
            <h3>TEAM STRENGTH<span>전력 비교 · 팀 OVR</span></h3>
            {UNITS.map(([k, u]) => {
              const hv = u === "overall" ? (H?.ovr.overall ?? m.home.ovr) : H?.ovr[u];
              const av = u === "overall" ? (A?.ovr.overall ?? m.away.ovr) : A?.ovr[u];
              if (hv == null || av == null) return null;
              const share = Math.round((hv ** 4 / (hv ** 4 + av ** 4)) * 100);
              // 더 강한 쪽 위에 'OVR +N 우위' — 흰 글씨만으로는 차이가 얼마인지 안 읽혔다
              const edge = (d: number) => d > 0 ? <MeaningTag sm m={adv(d)} title={`팀 OVR ${d} 높음`} /> : <span />;
              return (
                <div className="pv-cmp" key={k}>
                  <b className={hv > av ? "up" : ""}>{hv}</b>
                  <div className="pv-cmp-mid">
                    <span style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", alignItems: "center", gap: 6 }}>
                      <span style={{ justifySelf: "start" }}>{edge(hv - av)}</span>
                      {k}
                      <span style={{ justifySelf: "end" }}>{edge(av - hv)}</span>
                    </span>
                    <div className="mc5-bar"><span style={{ flexBasis: `${share}%`, background: hc }} /><span style={{ flexBasis: `${100 - share}%`, background: ac }} /></div>
                  </div>
                  <b className={av > hv ? "up" : ""}>{av}</b>
                </div>
              );
            })}
          </section>

          <section>
            <h3>FORM<span>리그 최근 5경기</span></h3>
            {[m.home, m.away].map((s) => (
              <div className="pv-form" key={s.team}><Crest s={s} size={20} /><span>{s.team}</span>{s.form.length ? <FormBoxes form={s.form} /> : <em>기록 없음</em>}</div>
            ))}
          </section>

          <section>
            <h3>KEY PLAYERS<span>핵심 선수</span></h3>
            <div className="pv-two">
              {[[m.home, H], [m.away, A]].map(([s, o], i) => {
                const side = s as FixtureSide, ov = o as Overview | null | undefined;
                return (
                  <div key={i}>
                    {ov === undefined ? <Skel h={120} r={12} /> : !ov ? <p className="pv-empty">데이터 없음</p> : ov.stars.slice(0, 3).map((p) => (
                      <button className={`pv-star fut ${futTier(p.ovr)}`} key={p.player}
                        onClick={(e) => peek(e, { name: p.player, club: side.team, league: side.league ?? undefined })}>
                        {p.photo ? <img src={p.photo} alt="" /> : <span className="pv-ph" />}
                        <span className="pv-star-t"><b>{p.player}</b>
                          <em>{p.pos}</em><FormPair season={p.form} recent={p.form_recent} n={p.recent_n} sm /></span>
                        <span className="pv-star-o" title={`OVR ${p.ovr} · ${ovrMeaning(p.ovr).label}`}>{p.ovr}</span>
                      </button>
                    ))}
                  </div>
                );
              })}
            </div>
          </section>

          <section>
            <h3>ABSENCES<span>결장</span>
              <Info label="데이터 설명"><p>전력(팀 OVR)·최근 결과·결장은 매일 자동으로 갱신되는 데이터로 계산한 규칙 기반 요약입니다.</p></Info></h3>
            <div className="pv-two">
              {[[m.home, H], [m.away, A]].map(([s, o], i) => {
                const ov = o as Overview | null | undefined;
                return (
                  <div key={i}>
                    {ov === undefined ? <Skel h={60} r={10} />
                      : !ov || ov.injuries.length === 0 ? <p className="pv-empty">{(s as FixtureSide).team} 결장 없음</p>
                      : ov.injuries.slice(0, 5).map((p) => (
                        <div className="pv-inj" key={p.player}><b>{p.player}</b><span>{p.injury}{p.until ? ` · ~${p.until}` : ""}</span></div>
                      ))}
                  </div>
                );
              })}
            </div>
          </section>

          <div className="pv-actions">
            {[m.home, m.away].map((s) => <button key={s.team} disabled={!s.league || !openTeam} onClick={() => go(s)}>{s.team} →</button>)}
          </div>
          </>}
        </div>
      </aside>
    </>
  );
}

export function MatchPreviewProvider({ children }: { children: React.ReactNode }) {
  const [m, setM] = useState<Fixture | null>(null);
  const open = useCallback((x: Fixture) => setM(x), []);
  const close = useCallback(() => setM(null), []);
  return (
    <MatchPreviewCtx.Provider value={open}>
      {children}
      {m && <Drawer m={m} onClose={close} />}
    </MatchPreviewCtx.Provider>
  );
}
