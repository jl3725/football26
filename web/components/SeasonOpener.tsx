"use client";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Fixture } from "@/lib/api";
import { fmtEur } from "@/lib/api";
import { lgEn, splitKst } from "@/lib/match";

// 시즌 오프닝 — 전 리그 홈에 들어올 때 한 번(브라우저 세션당) 나오는 방송 타이틀 같은 4초짜리 모션 그래픽.
// 영상 파일이 아니라 코드로 그린다: 실제 데이터(시즌·리그 선두 엠블럼·이적 집계·이번 주 빅매치)가 들어가고,
// 저작권 걱정(BBC·PL 중계 영상)이 없고, 용량이 0 에 가깝다. 아무 곳이나 누르거나 Esc 로 건너뛴다.

export type OpenerCrest = { logo: string; team: string; league: string };
export type OpenerStats = { spend_eur: number; signings: number; manager_changes: number };

const EXIT_AT = 4300;   // 빠지기 시작(ms)
const GONE_AT = 4950;   // 화면에서 제거

function useCount(target: number, delay: number, dur = 900) {
  const [v, setV] = useState(0);
  const raf = useRef(0);
  useEffect(() => {
    let start = 0;
    const t = setTimeout(() => {
      const step = (now: number) => {
        if (!start) start = now;
        const k = Math.min(1, (now - start) / dur);
        setV(target * (1 - Math.pow(1 - k, 3)));
        if (k < 1) raf.current = requestAnimationFrame(step);
      };
      raf.current = requestAnimationFrame(step);
    }, delay);
    return () => { clearTimeout(t); cancelAnimationFrame(raf.current); };
  }, [target, delay, dur]);
  return v;
}

export default function SeasonOpener({ season, seasonLong, crests, stats, match, onDone }: {
  season: string; seasonLong: string; crests: OpenerCrest[]; stats?: OpenerStats; match?: Fixture | null; onDone: () => void;
}) {
  const [leaving, setLeaving] = useState(false);
  const spend = useCount(stats?.spend_eur ?? 0, 2000);
  const sign = useCount(stats?.signings ?? 0, 2000);
  const mgr = useCount(stats?.manager_changes ?? 0, 2000);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const t1 = setTimeout(() => setLeaving(true), EXIT_AT);
    const t2 = setTimeout(onDone, GONE_AT);
    return () => { clearTimeout(t1); clearTimeout(t2); document.body.style.overflow = prev; };
  }, [onDone]);

  const skip = () => { setLeaving(true); setTimeout(onDone, 380); };
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape" || e.key === "Enter" || e.key === " ") skip(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const kickTime = match ? splitKst(match.kst).time : "";
  // body 로 띄운다 — 화면 안쪽(main)에 두면 사이드바가 오프닝 위로 올라왔다(쌓임 맥락)
  return createPortal(
    <div className={`op${leaving ? " leaving" : ""}`} role="dialog" aria-label={`${seasonLong} 시즌 오프닝`} onClick={skip}>
      <span className="op-beam b1" /><span className="op-beam b2" /><span className="op-beam b3" />
      <svg className="op-pitch" viewBox="0 0 1050 680" aria-hidden="true">
        <rect x="5" y="5" width="1040" height="670" rx="6" pathLength={1} />
        <line x1="525" y1="5" x2="525" y2="675" pathLength={1} />
        <circle cx="525" cy="340" r="92" pathLength={1} />
        <rect x="5" y="190" width="165" height="300" pathLength={1} />
        <rect x="880" y="190" width="165" height="300" pathLength={1} />
      </svg>

      <div className="op-core">
        <div className="op-eyebrow">SCOUT.AI · ALL LEAGUES</div>
        <div className="op-season" data-text={season}>{season}</div>
        <div className="op-word">SEASON</div>

        {crests.length > 0 && (
          <div className="op-crests">
            {crests.map((c, i) => (
              <div className="op-crest" key={c.team + i} style={{ ["--i" as any]: i }} title={`${c.team} · ${lgEn(c.league)} 선두`}>
                <img src={c.logo} alt="" />
                <span>{lgEn(c.league)}</span>
              </div>
            ))}
          </div>
        )}

        {stats && (
          <div className="op-stats">
            <div className="op-stat"><b>{spend < 1e6 ? "€0" : fmtEur(spend)}</b><span>SUMMER SPEND</span></div>
            <div className="op-stat"><b>{Math.round(sign).toLocaleString()}</b><span>SIGNINGS</span></div>
            <div className="op-stat"><b>{Math.round(mgr)}</b><span>NEW MANAGERS</span></div>
          </div>
        )}

        {match && (
          <div className="op-match">
            <em>MATCH OF THE WEEK</em>
            {match.home.logo && <img src={match.home.logo} alt="" />}
            <b>{match.home.team}</b><i>vs</i><b>{match.away.team}</b>
            {match.away.logo && <img src={match.away.logo} alt="" />}
            <span>{kickTime} KST</span>
          </div>
        )}
      </div>

      <button className="op-skip" onClick={(e) => { e.stopPropagation(); skip(); }}>SKIP ▸</button>
      <span className="op-bar" />
    </div>,
    document.body,
  );
}
