"use client";
import { FORM_NOTE, RECENT_NOTE, formMeaning, ssMeaning } from "@/lib/meaning";
import { compEn } from "@/lib/match";
import type { RecentMatch } from "@/lib/api";
import { MeaningTag } from "./Meaning";
import { isLeagueCode } from "@/lib/leagues";

// 폼 두 개 — SEASON(이번 시즌 전체) · LAST 5(최근 5경기, 전 대회 FotMob 경기 평점). 같은 45~99 척도(72 = 중간).
// 2026-10-19 사용자: '노팅엄전 사카가 엄청 못했는데 폼 절정 — 전체 폼과 최근 3·5경기 폼을 나누자'.
export default function FormPair({ season, recent, n, sm = false }: { season?: number | null; recent?: number | null; n?: number | null; sm?: boolean }) {
  if (season == null && recent == null) return null;
  const d = season != null && recent != null ? recent - season : null;
  return (
    <span className={`fp${sm ? " sm" : ""}`}>
      {season != null && (
        <span className="fp-i" title={FORM_NOTE}>
          <em>SEASON</em><b style={{ color: formMeaning(season).c }}>{season}</b><MeaningTag sm m={formMeaning(season)} />
        </span>
      )}
      {recent != null && (
        <span className="fp-i" title={RECENT_NOTE}>
          <em>LAST {Math.min(n ?? 5, 5)}</em><b style={{ color: formMeaning(recent).c }}>{recent}</b><MeaningTag sm m={formMeaning(recent)} />
          {d != null && Math.abs(d) >= 8 ? <i className={d > 0 ? "up" : "dn"} title={`시즌 폼보다 ${Math.abs(d)} ${d > 0 ? "높음" : "낮음"}`}>{d > 0 ? "▲" : "▼"}</i> : null}
        </span>
      )}
    </span>
  );
}

// FotMob 척도 → Sofascore 척도(src/rating_blend.fm_to_ss 와 같은 z 변환) — 색·뜻은 Sofascore 기준 한 벌로
export const fmToSs = (x: number) => 6.848 + ((x - 6.888) / 0.296) * 0.216;

// 최근 경기 평점 막대(과거 → 최신, 왼쪽 → 오른쪽). 숫자는 FotMob 원래 평점, 색은 같은 뜻 척도.
export function RecentStrip({ matches }: { matches: RecentMatch[] }) {
  if (!matches.length) return null;
  const xs = [...matches].reverse();
  return (
    <div className="rs5" role="list" aria-label="최근 경기 평점">
      {xs.map((m, i) => {
        const mn = ssMeaning(fmToSs(m.rating));
        const comp = isLeagueCode(m.comp_code) ? "" : (compEn(m.comp_code) || m.comp_code);
        const opp = m.opponent.length > 11 ? m.opponent.split(" ")[0] : m.opponent;
        return (
          <div className={`rs5-i${i === xs.length - 1 ? " last" : ""}`} role="listitem" key={m.date + m.opponent}
            title={`${m.date} ${m.home_away === "away" ? "@" : "vs"} ${m.opponent}${comp ? ` (${comp})` : ""} · ${m.minutes}′${m.goals ? ` · ${m.goals}골` : ""}${m.assists ? ` · ${m.assists}도움` : ""} · FotMob ${m.rating.toFixed(1)} (${mn.label})`}>
            <b style={{ color: mn.c, background: mn.bg }}>{m.rating.toFixed(1)}</b>
            <span>{m.home_away === "away" ? "@" : ""}{opp}</span>
            <em>{comp || m.date.slice(5).replace("-", "/")}{m.goals || m.assists ? ` · ${m.goals ? `${m.goals}G` : ""}${m.assists ? `${m.assists}A` : ""}` : ""}</em>
          </div>
        );
      })}
    </div>
  );
}
