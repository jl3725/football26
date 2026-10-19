"use client";
import { useEffect, useState } from "react";
import { getPredictionLeague, type PredPick, type PredictionLeague as PL, type PredRecent } from "@/lib/api";
import SectionHead from "./SectionHead";
import { Skel } from "./Skeleton";
import { TONE } from "@/lib/meaning";

// 세 결과에 1/3씩 걸면 브라이어 (2/3)²+(1/3)²+(1/3)² = 0.667 — 확률 오차의 '찍기' 수준
const RANDOM_BRIER = 0.667;
// 순위 색 — 셋이 같은 경기를 두고 겨룬 결과(예전 '무작위 33% 대비' 꼬리표는 셋 다 '크게 높음'이라 변별력이 없었다, 2026-10-19)
const RANK_TONE = [TONE.best, TONE.avg, TONE.weak];

// 홈 'PREDICTION LEAGUE' — 팬 투표 vs 우리 모델 vs ClubElo, 누가 더 잘 맞히나(경기 전 기록 → 결과 대조)
//   왼쪽: 출처별 적중률·브라이어(낮을수록 좋음) / 오른쪽: 다가오는 경기 중 팬과 모델의 픽이 갈린 경기 / 아래: 최근 결과 채점표
const PICK_KO = (p: PredPick, home: string, away: string) =>
  !p ? "—" : p.pick === "H" ? `${home} 승` : p.pick === "A" ? `${away} 승` : "무승부";
const short = (t: string) => (t.length > 14 ? t.split(" ").slice(-1)[0] : t);

function Mark({ p, r }: { p: PredPick; r: PredRecent["result"] }) {
  if (!p) return <i className="pl5-mk none">—</i>;
  return <i className={`pl5-mk ${p.pick === r ? "hit" : "miss"}`}>{p.pick === r ? "✓" : "✗"}</i>;
}

export default function PredictionLeague() {
  const [d, setD] = useState<PL | null | undefined>(undefined);
  useEffect(() => { let a = true; getPredictionLeague().then((x) => a && setD(x)).catch(() => a && setD(null)); return () => { a = false; }; }, []);
  if (d === undefined) return <Skel h={240} r={14} />;
  if (!d || !d.available) return null;
  const shown = d.sources.filter((s) => s.n > 0);
  const c = d.common;
  const best = c ? c.rank[0] : shown.length > 1 ? [...shown].sort((a, b) => (a.brier ?? 9) - (b.brier ?? 9))[0].key : null;
  const lead = c ? c.scores[c.rank[0]] : null;
  return (
    <section className="h5-sec">
      <SectionHead title="PREDICTION LEAGUE" kr="팬 vs 모델" meta={`누가 더 잘 맞히나 · ${d.since?.slice(5).replace("-", "/")}부터 경기 전 예측 기록`} />
      <div className="pl5">
        <div className="card pl5-board">
          <div className="pl5-cols">
            {d.sources.map((s) => {
              // 같은 경기 맞대결 값(셋 다 예측한 경기) — 없으면 출처별 전체 값
              const cs = c?.scores[s.key];
              const v = cs ?? s;
              const rk = c ? c.rank.indexOf(s.key) : -1;
              const tone = rk >= 0 ? RANK_TONE[Math.min(rk, 2)] : null;
              const gap = lead && cs && rk > 0 && lead.acc != null && cs.acc != null ? Math.round((cs.acc - lead.acc) * 1000) / 10 : null;
              return (
                <div className={`pl5-src ${s.key}${best === s.key ? " best" : ""}`} key={s.key}>
                  <em>{s.en}</em>
                  <b>{v.acc != null ? `${Math.round(v.acc * 100)}%` : "—"}</b>
                  <span>{v.n ? `${v.hits}/${v.n} 적중` : "기록 없음"}</span>
                  {tone && (
                    <span className="mn-tag sm" style={{ color: tone.c, background: tone.bg, whiteSpace: "normal", alignSelf: "flex-start", borderRadius: 6 }}
                      title={`셋 다 예측한 같은 ${c!.n}경기 기준 순위(적중률 → 브라이어)`}>
                      {rk + 1}위{gap != null ? ` · ${gap > 0 ? "+" : ""}${gap}%p` : rk === 0 ? " · 선두" : ""}
                    </span>
                  )}
                  <small title={`브라이어 점수 — 확률이 결과와 얼마나 가까웠나(0 = 완벽, 낮을수록 좋음 · ${RANDOM_BRIER} = 세 결과에 1/3씩 건 찍기 수준)`}>{v.brier != null ? `브라이어 ${v.brier.toFixed(3)}` : ""}</small>
                  {cs && s.n !== cs.n && <small style={{ opacity: 0.65 }}>전체 {s.hits}/{s.n}</small>}
                </div>
              );
            })}
          </div>
          <p className="pl5-note" style={{ marginTop: 8 }}>
            {c ? <>셋 다 예측한 <b>같은 {c.n}경기</b> 맞대결 — 순위는 적중률, 같으면 브라이어(확률 오차, 낮을수록 정확 · {RANDOM_BRIER} = 찍기 수준)</>
              : <>브라이어 = 확률 오차, 낮을수록 정확(0 = 완벽, {RANDOM_BRIER} = 찍기 수준)</>}
            {c && c.n < 30 && <> · 아직 표본이 작아 우열을 단정하기 이릅니다</>}
          </p>
          {c?.v3 && (
            <p className="pl5-h2h" title="v3 = 최근 흐름 가중·자체 Elo·부상 결장 반영. v3 이전 경기는 그 경기 전 데이터만으로 다시 계산한 값(부상 명단 제외 · 팀 OVR 은 지금 값)이라 참고용">
              <b>MODEL v3</b>{d.v3_since ? ` (${d.v3_since.slice(5).replace("-", "/")} 경기부터 실시간 기록)` : ""} · 같은 {c.v3.n}경기
              {" "}<b>{c.v3.acc != null ? `${Math.round(c.v3.acc * 100)}%` : "—"}</b> 적중 · 브라이어 <b>{c.v3.brier?.toFixed(3)}</b>
              {c.v3_live < c.v3.n && <span style={{ opacity: 0.7 }}> — 지난 경기는 재계산(참고)</span>}
            </p>
          )}
          <div className="pl5-recent">
            <div className="pl5-rh"><span>최근 결과</span><em>팬</em><em>모델</em><em>Elo</em></div>
            {d.recent.slice(0, 8).map((r) => (
              <div className="pl5-rr" key={r.event_id}>
                <span className="pl5-m">
                  {r.home_logo ? <img src={r.home_logo} alt="" /> : <i className="ph" />}
                  <b>{short(r.home)}</b><strong>{r.hg}-{r.ag}</strong><b>{short(r.away)}</b>
                  {r.away_logo ? <img src={r.away_logo} alt="" /> : <i className="ph" />}
                </span>
                <Mark p={r.fans} r={r.result} /><Mark p={r.model} r={r.result} /><Mark p={r.elo} r={r.result} />
              </div>
            ))}
          </div>
        </div>
        <div className="card pl5-split">
          <div className="pl5-st">의견 갈린 경기<span>다가오는 경기 · 팬과 모델의 예상 결과가 다름</span></div>
          {d.split.length ? d.split.map((x) => (
            <div className="pl5-sr" key={x.event_id}>
              <div className="pl5-sm">
                {x.home_logo ? <img src={x.home_logo} alt="" /> : <i className="ph" />}<b>{x.home}</b>
                <em>vs</em><b>{x.away}</b>{x.away_logo ? <img src={x.away_logo} alt="" /> : <i className="ph" />}
                <span className="pl5-d">{x.date.slice(5).replace("-", "/")}</span>
              </div>
              <div className="pl5-sp">
                <span className="fans">FANS <b>{PICK_KO(x.fans, short(x.home), short(x.away))}</b> {x.fans ? `${Math.round(x.fans.p * 100)}%` : ""}</span>
                <span className="model">MODEL <b>{PICK_KO(x.model, short(x.home), short(x.away))}</b> {x.model ? `${Math.round(x.model.p * 100)}%` : ""}</span>
              </div>
            </div>
          )) : <p className="pv-empty">이번 주는 팬과 모델의 예상이 대부분 같습니다</p>}
          <p className="pl5-note">MODEL = 이 사이트의 데이터 통계 모델(xG·득실·선수 평점) · FANS = Sofascore 팬 투표 · 재미용, 베팅 정보 아님</p>
        </div>
      </div>
    </section>
  );
}
