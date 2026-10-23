"use client";
import { fmtEur, fmtEurRange, type FairPrice } from "@/lib/api";
import Info from "./Info";

// FAIR PRICE — 스카우트 리포트의 적정 이적료(src/fee_comps.py).
// 가운데 = 이적 직전 시장가치 × 사는 리그·나이 배수(13개 리그 이적 기록에서 매일 다시 배움). 진한 막대 = 실제 이적료의 가운데 50%,
// 옅은 막대 = 80%. 비슷한 이적 5건은 값을 내는 데 쓰지 않고 근거로 보여 준다 — 사례 이적료로 값을 내면 시장가치 하나보다
// 덜 맞았다(오차 중앙값 46% ↔ 33%, 2026-10-23 측정). 계약 잔여는 과거 이적에 기록이 없어 계산에 넣지 않는다.

const W = 600, H = 40, PAD = 14, Y = 22;

function niceMax(v: number): { max: number; step: number } {
  const raw = v / 4;
  const p = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw) ?? 10 * p;
  return { max: Math.ceil(v / step) * step, step };
}

function Scale({ f }: { f: FairPrice }) {
  const top = Math.max(f.hi80, f.mv_eur || 0, ...f.comps.map((c) => c.fee_eur)) * 1.04;
  const { max, step } = niceMax(top);
  const x = (v: number) => PAD + (Math.min(v, max) / max) * (W - PAD * 2);
  const ticks = Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step);
  // 가까운 사례 점은 위아래로 엇갈려 겹치지 않게
  const dots = [...f.comps].sort((a, b) => a.fee_eur - b.fee_eur).map((c, i, arr) => {
    const close = i > 0 && x(c.fee_eur) - x(arr[i - 1].fee_eur) < 11;
    return { c, cx: x(c.fee_eur), cy: close && i % 2 ? Y - 9 : Y + 3 };
  });
  return (
    <svg className="fp-scale" viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label={`적정 이적료 ${fmtEurRange(f.lo, f.hi)} · 넓게 ${fmtEurRange(f.lo80, f.hi80)}${f.mv_eur ? ` · 시장가치 ${fmtEur(f.mv_eur)}` : ""}`}>
      <rect className="fp-track" x={PAD} y={Y} width={W - PAD * 2} height={6} rx={3} />
      <rect className="fp-b80" x={x(f.lo80)} y={Y} width={Math.max(2, x(f.hi80) - x(f.lo80))} height={6} rx={3} />
      <rect className="fp-b50" x={x(f.lo)} y={Y - 2} width={Math.max(2, x(f.hi) - x(f.lo))} height={10} rx={4} />
      {f.mv_eur ? <line className="fp-mv" x1={x(f.mv_eur)} x2={x(f.mv_eur)} y1={Y - 12} y2={Y + 18}><title>{`시장가치 ${fmtEur(f.mv_eur)}`}</title></line> : null}
      {dots.map(({ c, cx, cy }) => (
        <circle key={c.player + c.when} className="fp-dot" cx={cx} cy={cy} r={5}>
          <title>{`${c.player} · ${c.from} → ${c.to} · ${fmtEur(c.fee_eur)}`}</title>
        </circle>
      ))}
    </svg>
  );
}

// 눈금 글자는 HTML 로 — SVG 글자는 폰 폭에서 같이 줄어 6px 쯤이 됐다
function Ticks({ f }: { f: FairPrice }) {
  const top = Math.max(f.hi80, f.mv_eur || 0, ...f.comps.map((c) => c.fee_eur)) * 1.04;
  const { max, step } = niceMax(top);
  const ticks = Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step);
  const left = (v: number) => `${((PAD + (v / max) * (W - PAD * 2)) / W) * 100}%`;
  return (
    <div className="fp-ticks" aria-hidden>
      {ticks.map((t, i) => (
        <span key={t} style={{ left: left(t), transform: i === 0 ? "none" : i === ticks.length - 1 ? "translateX(-100%)" : "translateX(-50%)" }}>
          {t === 0 ? "€0" : fmtEur(t).replace(".0M", "M")}
        </span>
      ))}
    </div>
  );
}

export default function FairPriceSection({ f, monthsLeft }: { f: FairPrice; monthsLeft?: number | null }) {
  const acc = f.acc;
  const pct = (v?: number) => (v == null ? "-" : `${Math.round(v * 100)}%`);
  return (
    <section className="sr-sec sr-fair">
      <h2>FAIR PRICE <em>적정 이적료 · {f.buyer ? `${f.buyer} 기준` : "사는 구단 미정(리그 평균)"}</em>
        <Info label="적정 이적료 설명" wide>
          {f.basis === "mv" ? (
            <p>가운데 {fmtEur(f.mid)} = 시장가치 {fmtEur(f.mv_eur || 0)}{f.factors.map((x) => ` × ${x.label} ${x.x}`).join("")}.
              배수는 13개 리그 이적 기록(이적 직전 시장가치가 있는 이적)에서 매일 다시 배웁니다.</p>
          ) : (
            <p>시장가치가 없어 OVR·나이·포지션·리그 수준으로 추정했습니다. 오차가 커서 범위가 넓습니다.</p>
          )}
          <p>진한 막대 = 실제 이적료가 두 번 중 한 번 든 폭({pct(acc?.in50)}), 옅은 막대 = 열 번 중 여덟 번({pct(acc?.in80)}).
            오차 중앙값 {pct(acc?.med_err)}{acc?.mv_only_err ? ` (시장가치만 ${pct(acc.mv_only_err)})` : ""}.</p>
          <p>비슷한 이적 = 같은 라인(GK·수비·중원·공격)에서 나이·당시 OVR·판 리그·산 리그가 가까운 순. ×값 = 이적료 ÷ 당시 시장가치.
            사례로 값을 내면 시장가치 하나보다 덜 맞아 근거로만 보여 줍니다.</p>
          <p className="muted">계약 잔여는 과거 이적에 기록이 없어 계산에 넣지 않았습니다.</p>
        </Info>
      </h2>
      <div className="fp-top">
        <div className="fp-range">
          <b>{fmtEurRange(f.lo, f.hi)}</b>
          <span>가운데 {fmtEur(f.mid)}{f.mv_eur ? ` · 시장가치 ${fmtEur(f.mv_eur)}` : " · 추정"}</span>
        </div>
        <div className="fp-chips">
          {f.factors.filter((x) => Math.abs(x.x - 1) >= 0.03).map((x) => (
            <span key={x.k} title={`이적 기록 ${x.n}건에서 배운 배수`}>{x.label} ×{x.x.toFixed(2)}</span>
          ))}
          {monthsLeft != null && monthsLeft >= 0 && monthsLeft <= 12 && (
            <span className="warn" title="계약이 1년 안에 끝나면 이적료가 범위 아래쪽에서 정해지는 경우가 많습니다 — 과거 기록이 없어 계산엔 넣지 않았습니다">계약 {monthsLeft}개월</span>
          )}
        </div>
      </div>
      <Scale f={f} />
      <Ticks f={f} />
      <div className="fp-legend"><span><i className="k50" />적정 범위</span><span><i className="k80" />넓게</span>{f.mv_eur ? <span><i className="kmv" />시장가치</span> : null}<span><i className="kdot" />비슷한 이적</span></div>
      {f.comps.length > 0 && (
        <div className="fp-comps">
          <table className="sr-table">
            <thead><tr><th className="l">비슷한 이적</th><th>이적료</th><th>나이</th><th>OVR</th><th className="l">이동</th></tr></thead>
            <tbody>
              {f.comps.map((c) => (
                <tr key={c.player + c.when}>
                  <td className="l"><b>{c.player}</b> <small>{c.when}</small></td>
                  <td><b>{fmtEur(c.fee_eur)}</b>{c.ratio != null && <small title="이적료 ÷ 당시 시장가치"> ×{c.ratio.toFixed(2)}</small>}</td>
                  <td>{c.age}</td>
                  <td>{c.ovr}</td>
                  <td className="l">{c.from} → {c.to}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
