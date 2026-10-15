"use client";
import { useEffect, useState } from "react";
import { getPredictionLeague, type PredPick, type PredictionLeague as PL, type PredRecent } from "@/lib/api";
import SectionHead from "./SectionHead";
import { Skel } from "./Skeleton";
import { vsBaseline } from "@/lib/meaning";

// 3지선다(홈·무·원정) 기준값 — 무작위로 찍으면 적중률 33%, 세 결과에 1/3씩 걸면 브라이어 (2/3)²+(1/3)²+(1/3)² = 0.667
const RANDOM_ACC = 33;
const RANDOM_BRIER = 0.667;

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
  const best = shown.length > 1 ? [...shown].sort((a, b) => (a.brier ?? 9) - (b.brier ?? 9))[0].key : null;
  const minN = Math.min(...shown.map((s) => s.n));
  return (
    <section className="h5-sec">
      <SectionHead title="PREDICTION LEAGUE" kr="팬 vs 모델" meta={`누가 더 잘 맞히나 · ${d.since?.slice(5).replace("-", "/")}부터 경기 전 예측 기록`} />
      <div className="pl5">
        <div className="card pl5-board">
          <div className="pl5-cols">
            {d.sources.map((s) => (
              <div className={`pl5-src ${s.key}${best === s.key ? " best" : ""}`} key={s.key}>
                <em>{s.en}</em>
                <b>{s.acc != null ? `${Math.round(s.acc * 100)}%` : "—"}</b>
                <span>{s.n ? `${s.hits}/${s.n} 적중` : "기록 없음"}</span>
                {s.acc != null && (() => {
                  const vb = vsBaseline(s.acc * 100, RANDOM_ACC);
                  // 칸이 좁아(390px 에서 ~80px) 꼬리표가 두 줄로 접히게 둔다
                  return (
                    <span className="mn-tag sm" style={{ color: vb.c, background: vb.bg, whiteSpace: "normal", alignSelf: "flex-start", borderRadius: 6 }}
                      title={`무작위로 찍으면 ${RANDOM_ACC}% — ${Math.round(s.acc * 100)}%는 ${vb.label}`}>
                      {vb.label}
                    </span>
                  );
                })()}
                <small title={`브라이어 점수 — 확률이 결과와 얼마나 가까웠나(0 = 완벽, 낮을수록 좋음 · ${RANDOM_BRIER} = 세 결과에 1/3씩 건 찍기 수준)`}>{s.brier != null ? `브라이어 ${s.brier.toFixed(3)}` : ""}</small>
              </div>
            ))}
          </div>
          <p className="pl5-note" style={{ marginTop: 8 }}>
            적중률 = 무작위 {RANDOM_ACC}% 대비 · 브라이어 = 확률 오차, 낮을수록 정확(0 = 완벽, {RANDOM_BRIER} = 찍기 수준)
          </p>
          {d.h2h && (
            <p className="pl5-h2h">
              맞대결(둘 다 예측한 {d.h2h.n}경기): 팬 <b>{d.h2h.fans.hits}</b>적중 · 모델 <b>{d.h2h.model.hits}</b>적중
              {minN < 30 && <> — 아직 표본이 작아 우열을 말하기 이릅니다</>}
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
