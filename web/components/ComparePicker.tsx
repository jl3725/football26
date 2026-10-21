"use client";
import { useEffect, useMemo, useState } from "react";
import { foldName, getDatabase, type DbPlayer } from "@/lib/api";
import { tier } from "@/lib/ui";

export type CmpRef = { player: string; team: string; league: string };

// 비교 B 선수 — 8개 리그 누구든(P2 ⑥ 리그 간 비교). 같은 스쿼드 선수는 왼쪽 카드로 고른다.
// 전 리그 선수 목록은 전역 검색과 같은 /api/database(세션 캐시).
export default function ComparePicker({ exclude, onPick }: { exclude?: string; onPick: (r: CmpRef) => void }) {
  const [all, setAll] = useState<DbPlayer[]>([]);
  const [q, setQ] = useState("");
  useEffect(() => { getDatabase().then((d) => setAll(d.players)).catch(() => {}); }, []);
  const s = foldName(q.trim());
  const hits = useMemo(() => (s.length < 2 ? [] : all
    .filter((p) => p.player !== exclude && foldName(`${p.player} ${p.squad}`).includes(s))
    .sort((a, b) => b.ovr - a.ovr).slice(0, 8)), [all, s, exclude]);
  return (
    <div className="cmp-pick">
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="다른 클럽·리그 선수 검색 (예: Bastoni, Saliba)"
        aria-label="비교할 선수 검색 — 8개 리그" />
      {hits.length > 0 && (
        <div className="cmp-pick-list" role="listbox">
          {hits.map((p) => (
            <button key={`${p.player}|${p.squad}`} role="option" aria-selected={false}
              onClick={() => { onPick({ player: p.player, team: p.squad, league: p.league }); setQ(""); }}>
              {p.photo ? <img src={p.photo} alt="" /> : <span className="cmp-pick-ph" />}
              <span><b>{p.player}</b><em>{p.squad} · {p.league} · {p.pos}</em></span>
              <b style={{ color: tier(p.ovr).light }}>{p.ovr}</b>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
