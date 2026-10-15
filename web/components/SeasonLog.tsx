"use client";
import { useState } from "react";
import type { SeasonLog as Log } from "@/lib/api";
import { hexA } from "@/lib/ui";

// SEASON LOG — 리그·국내컵·유럽대항전을 경기별로 쌓고(출전 분·골·도움·카드) 대회별로 나눠 합산한다.
// 원천: ESPN 라인업·교체(대회별) + 선수 이벤트(data/match_events). 예전 Player 탭은 리그 스탯 + 컵·유럽 선발 수뿐이었다.
export const COMP_COLOR: Record<string, string> = {
  "리그": "#8aa0b8", "챔피언스리그": "#5b8def", "유로파리그": "#e08a3c", "컨퍼런스리그": "#4fc27f",
  "FA컵": "#b98cd8", "EFL컵": "#c98a8a", "코파델레이": "#d8b34e",
};
const cc = (c: string) => COMP_COLOR[c] || "#a58bd6";
const ST: Record<string, string> = { start: "선발", sub: "교체", bench: "벤치", out: "명단 외" };

export default function SeasonLog({ log, accent }: { log: Log; accent: string }) {
  const [comp, setComp] = useState<string>("all");
  const [hover, setHover] = useState<number | null>(null);
  if (!log.available || !log.matches.length) return null;
  const ms = log.matches.filter((m) => comp === "all" || m.comp === comp);
  const W = Math.max(520, ms.length * 30 + 60), H = 168, base = 128, top = 34, PADL = 34;
  const bw = Math.min(20, (W - PADL - 16) / Math.max(1, ms.length) - 6);
  const x = (i: number) => PADL + 8 + i * ((W - PADL - 16) / Math.max(1, ms.length)) + bw / 2;
  const y = (min: number) => base - (Math.min(min, 120) / 90) * (base - top);
  const hm = hover != null ? ms[hover] : null;
  return (
    <div className="slog">
      <div className="slog-head">
        <h4 className="net-h">SEASON LOG <span>대회별 분리 · 합산 — 리그·컵·유럽 라인업과 득점 기록</span></h4>
        <div className="comp-seg chips5">
          <button className={comp === "all" ? "active" : ""} onClick={() => setComp("all")}>전체</button>
          {log.by_comp.filter((c) => c.matches).map((c) => (
            <button key={c.comp} className={comp === c.comp ? "active" : ""} onClick={() => setComp(c.comp)}>{c.comp}</button>
          ))}
        </div>
      </div>
      <div className="slog-table" role="table">
        <div className="slog-row h" role="row"><span>대회</span><span>출전(선발)</span><span>분</span><span>골</span><span>도움</span><span>카드</span></div>
        {log.by_comp.map((c) => (
          <button key={c.comp} className={`slog-row${comp === c.comp ? " on" : ""}`} onClick={() => setComp(comp === c.comp ? "all" : c.comp)}>
            <span><i style={{ background: cc(c.comp) }} />{c.comp}</span>
            <span>{c.apps}<em>({c.starts})</em> <small>/ {c.matches}</small></span>
            <span>{c.minutes.toLocaleString()}′</span><span>{c.goals}</span><span>{c.assists}</span>
            <span>{c.yellow ? `🟨${c.yellow}` : ""}{c.red ? ` 🟥${c.red}` : ""}</span>
          </button>
        ))}
        <div className="slog-row tot" role="row">
          <span>합계</span><span>{log.total.apps}<em>({log.total.starts})</em> <small>/ {log.total.matches}</small></span>
          <span>{log.total.minutes.toLocaleString()}′</span><span>{log.total.goals}</span><span>{log.total.assists}</span>
          <span>{log.total.yellow ? `🟨${log.total.yellow}` : ""}{log.total.red ? ` 🟥${log.total.red}` : ""}</span>
        </div>
      </div>
      <div className="net-scroll">
        <svg viewBox={`0 0 ${W} ${H}`} className="net-svg" style={{ minWidth: Math.min(W, 640) }} role="img"
          aria-label="경기별 출전 시간(막대, 색 = 대회)과 골·도움(점)">
          {[0, 45, 90].map((v) => (
            <g key={v}><line x1={PADL} y1={y(v)} x2={W - 6} y2={y(v)} stroke={hexA("#ffffff", v ? 0.07 : 0.18)} strokeDasharray={v ? "3 4" : undefined} />
              <text x={PADL - 6} y={y(v)} dy="0.35em" textAnchor="end" fontSize="9" fill={hexA("#ffffff", 0.4)}>{v}′</text></g>
          ))}
          {ms.map((m, i) => {
            const on = hover === i;
            return (
              <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} style={{ cursor: "default" }}>
                <rect x={x(i) - bw / 2 - 3} y={top - 22} width={bw + 6} height={H - top + 10} fill={on ? hexA("#ffffff", 0.05) : "transparent"} />
                {m.minutes > 0
                  ? <rect x={x(i) - bw / 2} y={y(m.minutes)} width={bw} height={base - y(m.minutes)} rx={3} fill={cc(m.comp)} fillOpacity={m.status === "start" ? 0.95 : 0.55} />
                  : <rect x={x(i) - bw / 2} y={base - 3} width={bw} height={3} rx={1.5} fill={hexA("#ffffff", m.status === "bench" ? 0.25 : 0.1)} />}
                {Array.from({ length: m.goals }).map((_, k) => <circle key={"g" + k} cx={x(i)} cy={y(m.minutes) - 8 - k * 11} r={4.5} fill="#f6f8fa" stroke="#0c1016" />)}
                {Array.from({ length: m.assists }).map((_, k) => (
                  <path key={"a" + k} d={`M${x(i)},${y(m.minutes) - 12 - (m.goals + k) * 11 - 4} l4.5,8 h-9 z`} fill={accent} />
                ))}
                {m.red > 0 && <rect x={x(i) - 3} y={base + 5} width={6} height={8} rx={1} fill="#e5484d" />}
                <text x={x(i)} y={base + 22} textAnchor="middle" fontSize="8.5" fill={hexA("#ffffff", 0.45)}>{m.date.slice(5).replace("-", "/")}</text>
                <text x={x(i)} y={base + 33} textAnchor="middle" fontSize="8.5" fontWeight={700}
                  fill={m.result === "W" ? "#4fc27f" : m.result === "L" ? "#e07070" : hexA("#ffffff", 0.5)}>{m.result}</text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="slog-foot">
        {hm ? (
          <span><b style={{ color: cc(hm.comp) }}>{hm.comp}</b> {hm.date} · {hm.home_away === "H" ? "홈" : "원정"} vs {hm.opponent} {hm.score}
            {" · "}{ST[hm.status]}{hm.minutes ? ` ${hm.minutes}′` : ""}{hm.goals ? ` · ${hm.goals}골${hm.pens ? `(PK ${hm.pens})` : ""}` : ""}{hm.assists ? ` · ${hm.assists}도움` : ""}</span>
        ) : (
          <span>막대 = 출전 시간(진할수록 선발, 색 = 대회) · ● 골 · ▲ 도움 · 막대에 마우스를 올리면 경기 정보
            {log.events_coverage < 1 ? ` · 득점 기록 수집 ${Math.round(log.events_coverage * 100)}%` : ""}</span>
        )}
      </div>
    </div>
  );
}
