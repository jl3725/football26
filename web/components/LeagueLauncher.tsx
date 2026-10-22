"use client";
// 리그 홈·국가대표 화면 상단 — 리그 탭 한 줄 대신 '← 전체 · 지금 리그 ▾ · INTERNATIONAL'. 지금 리그를 누르면
// 리그 지도와 같은 묶음(TIER 1·2·3, 2부 리그는 1부 바로 뒤 ↳)을 작게 펼친다. 바깥 누르기·Esc 로 닫힌다.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLeagueGroups } from "@/lib/leagueMap";
import { leagueLabel } from "@/lib/leagues";

export default function LeagueLauncher({ current, view, onAll, onPick, right }: {
  current: string; view: "league" | "INTL"; onAll: () => void; onPick: (league: string) => void; right?: ReactNode;
}) {
  const g = useLeagueGroups();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  const pick = (k: string) => { setOpen(false); onPick(k); };
  const chip = (k: string, label: string, round = false) => (
    <button key={k} type="button" className={`ll-mini${round ? " o" : ""}${view === "league" && k === current ? " on" : ""}`}
      onClick={() => pick(k)}>{label}</button>
  );
  return (
    <div className="ll" ref={box}>
      <button type="button" className="ll-crumb" onClick={onAll}>← 전체</button>
      <button type="button" className={`ll-current${view === "league" ? " on" : ""}`} aria-expanded={open} aria-haspopup="true"
        onClick={() => setOpen((o) => !o)}>{view === "league" ? (current === "EPL" ? "EPL" : leagueLabel(current)) : "LEAGUES"} ▾</button>
      {right}
      {open && (
        <div className="ll-pop" role="menu">
          <div className="ll-row t1"><span className="ll-lab">TIER 1</span>
            {g[1].flatMap((l) => [chip(l.key, l.label), ...l.subs.map((s) => chip(s.key, `↳ ${s.label}`))])}</div>
          <div className="ll-row t2"><span className="ll-lab">TIER 2</span>{g[2].map((l) => chip(l.key, l.label))}</div>
          <div className="ll-row t3"><span className="ll-lab">TIER 3</span>
            {g[3].filter((l) => !l.soon).map((l) => chip(l.key, l.short, true))}</div>
        </div>
      )}
    </div>
  );
}
