"use client";
import { useCallback, useEffect, useState } from "react";
import { getOverview, type Fixture, type FixtureSide, type Overview } from "@/lib/api";
import { colorsClose, compLabel, compTone, ddayLabel, lgKo, liftHex, rankLabel, streak } from "@/lib/match";
import { MatchPreviewCtx } from "@/lib/matchPreview";
import { futTier, hexA } from "@/lib/ui";
import { Crest, FormBoxes, PredictBar } from "./MatchCard";
import { usePeek, useOpenTeam } from "./PlayerPeek";
import { Skel } from "./Skeleton";

// 매치 프리뷰 서랍 — 경기 카드를 누르면 열린다. 두 팀 Overview(전력·폼·핵심 선수·결장)를 불러
// 규칙으로 '관전 포인트'를 만든다(유료 AI 없음). 데이터는 매일 자동 갱신분 그대로.

const UNITS: [string, "overall" | "attack" | "midfield" | "defense"][] = [["OVERALL", "overall"], ["ATTACK", "attack"], ["MIDFIELD", "midfield"], ["DEFENSE", "defense"]];
const KO_UNIT: Record<string, string> = { ATTACK: "공격", MIDFIELD: "중원", DEFENSE: "수비" };

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
    if (Math.abs(d) >= 2) out.push(`${KO_UNIT[k]} 전력 ${d > 0 ? h.team : a.team} 우세 (+${Math.abs(d)})`);
    const hEdge = H.ovr.attack - A.ovr.defense, aEdge = A.ovr.attack - H.ovr.defense;
    if (Math.abs(hEdge - aEdge) >= 3) {
      out.push(hEdge > aEdge
        ? `${h.team} 공격(${H.ovr.attack}) vs ${a.team} 수비(${A.ovr.defense}) 싸움이 열쇠`
        : `${a.team} 공격(${A.ovr.attack}) vs ${h.team} 수비(${H.ovr.defense}) 싸움이 열쇠`);
    }
    const starOut = (o: Overview) => o.stars.filter((s) => o.injuries.some((i) => i.player === s.player)).map((s) => s.player);
    const so = [...starOut(H), ...starOut(A)];
    if (so.length) out.push(`핵심 선수 결장: ${so.join(", ")}`);
    else if (H.injuries.length + A.injuries.length > 0) out.push(`결장 ${h.team} ${H.injuries.length}명 · ${a.team} ${A.injuries.length}명`);
  }
  return out.slice(0, 5);
}

function Drawer({ m, onClose }: { m: Fixture; onClose: () => void }) {
  const [H, setH] = useState<Overview | null | undefined>(undefined);
  const [A, setA] = useState<Overview | null | undefined>(undefined);
  const peek = usePeek();
  const openTeam = useOpenTeam();
  useEffect(() => {
    let alive = true;
    const load = (s: FixtureSide, set: (o: Overview | null) => void) =>
      s.league ? getOverview(s.team, s.league).then((o) => alive && set(o)).catch(() => alive && set(null)) : set(null);
    load(m.home, setH); load(m.away, setA);
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => { alive = false; window.removeEventListener("keydown", esc); };
  }, [m, onClose]);

  const loading = H === undefined || A === undefined;
  const hc = liftHex(m.home.color), ac0 = liftHex(m.away.color);
  const ac = colorsClose(hc, ac0) ? "#8a94a8" : ac0;   // 비슷한 색이면 원정은 중립색(막대가 한 덩어리로 보이지 않게)
  const pts = loading ? [] : keyPoints(m, H ?? null, A ?? null);
  const go = (s: FixtureSide) => { if (s.league && openTeam) { onClose(); openTeam(s.team, s.league); } };

  const head = (s: FixtureSide, o: FixtureSide) => (
    <div className="pv-side">
      <Crest s={s} size={64} />
      <b>{s.team}</b>
      <span>{[rankLabel(s, o) || lgKo(s.league), s.ovr ? `OVR ${s.ovr}` : ""].filter(Boolean).join(" · ")}</span>
    </div>
  );

  return (
    <>
      <button className="pv-scrim" aria-label="프리뷰 닫기" onClick={onClose} />
      <aside className="pv" role="dialog" aria-modal="true" aria-label={`${m.home.team} 대 ${m.away.team} 매치 프리뷰`}>
        <header className="pv-head" style={{ ["--hc" as any]: hexA(hc, 0.32), ["--ac" as any]: hexA(ac, 0.38) }}>
          <div className="pv-top">
            <span className={`bdg ${compTone(m.comp_code)}`}>{compLabel(m)}</span>
            <span className={`bdg ${m.d_day <= 1 ? "hot" : "neutral"}`}>{ddayLabel(m.d_day)}</span>
            <span className="pv-when">{m.kst} KST</span>
            <button className="pv-x" onClick={onClose} aria-label="닫기">×</button>
          </div>
          <div className="pv-teams">{head(m.home, m.away)}<span className="pv-vs">VS</span>{head(m.away, m.home)}</div>
        </header>

        <div className="pv-body">
          {(m.fans || m.elo) && (
            <section>
              <h3>PREDICTIONS<span>팬 투표 · 예측 모델</span></h3>
              {m.fans && (
                <>
                  <div className="pv-src">FAN VOTE <em>Sofascore 사용자 {m.fans.n.toLocaleString()}표</em></div>
                  <div className="pv-prob">
                    <div><b>{Math.round(m.fans.h * 100)}%</b><span>{m.home.team} 승</span></div>
                    <div><b>{Math.round(m.fans.d * 100)}%</b><span>무승부</span></div>
                    <div><b>{Math.round(m.fans.a * 100)}%</b><span>{m.away.team} 승</span></div>
                  </div>
                  <PredictBar m={{ ...m, elo: undefined }} slim />
                  {(m.fans.btts != null || m.fans.first_h != null) && (
                    <div className="pv-side-votes">
                      {m.fans.btts != null && <span>양 팀 모두 득점 <b>{Math.round(m.fans.btts * 100)}%</b></span>}
                      {m.fans.first_h != null && m.fans.first_a != null && (
                        <span>선제골 <b>{m.home.team} {Math.round(m.fans.first_h * 100)}%</b> · <b>{m.away.team} {Math.round(m.fans.first_a * 100)}%</b></span>
                      )}
                    </div>
                  )}
                </>
              )}
              {m.elo && (
                <div className="pv-elo">
                  <div className="pv-src">CLUBELO <em>유럽 클럽 Elo 레이팅 기반 독립 예측 모델</em></div>
                  <PredictBar m={{ ...m, fans: undefined }} slim />
                </div>
              )}
              <p className="pv-note">팬 투표는 Sofascore 앱 사용자 투표(재미용), ClubElo 는 clubelo.com 의 공개 예측입니다. 베팅 정보가 아닙니다.</p>
            </section>
          )}

          <section>
            <h3>KEY POINTS<span>관전 포인트</span></h3>
            {loading ? <><Skel h={14} style={{ marginBottom: 8 }} /><Skel h={14} w="80%" /></>
              : pts.length ? <ul className="pv-points">{pts.map((p) => <li key={p}>{p}</li>)}</ul>
              : <p className="pv-empty">두 팀 데이터가 부족해 요약을 만들지 못했습니다.</p>}
          </section>

          <section>
            <h3>TEAM STRENGTH<span>전력 비교 · 팀 OVR</span></h3>
            {UNITS.map(([k, u]) => {
              const hv = u === "overall" ? (H?.ovr.overall ?? m.home.ovr) : H?.ovr[u];
              const av = u === "overall" ? (A?.ovr.overall ?? m.away.ovr) : A?.ovr[u];
              if (hv == null || av == null) return null;
              const share = Math.round((hv ** 4 / (hv ** 4 + av ** 4)) * 100);
              return (
                <div className="pv-cmp" key={k}>
                  <b className={hv > av ? "up" : ""}>{hv}</b>
                  <div className="pv-cmp-mid"><span>{k}</span>
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
                        <span className="pv-star-t"><b>{p.player}</b><em>{p.pos}{p.form ? ` · 폼 ${p.form}` : ""}</em></span>
                        <span className="pv-star-o">{p.ovr}</span>
                      </button>
                    ))}
                  </div>
                );
              })}
            </div>
          </section>

          <section>
            <h3>ABSENCES<span>결장</span></h3>
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
          <p className="pv-note">전력(팀 OVR)·최근 결과·결장은 매일 자동으로 갱신되는 데이터로 계산한 규칙 기반 요약입니다.</p>
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
