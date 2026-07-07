"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { getDatabase, fmtEur, type DbPlayer } from "@/lib/api";
import { hexA, tier } from "@/lib/ui";
import Icon from "./Icon";

// FM식 전역 검색 — 전 리그 선수·구단 즉시 조회 → 클릭 시 점프. Database 탭 대체.
// /api/database(캐시) 재사용 → 새 API 불필요. ⌘/Ctrl+/ 로 포커스.
export default function GlobalSearch({ accent, onPickPlayer, onPickTeam }: {
  accent: string;
  onPickPlayer: (club: string, league: string, player: string) => void;
  onPickTeam: (club: string, league: string) => void;
}) {
  const [players, setPlayers] = useState<DbPlayer[]>([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => { getDatabase().then((d) => setPlayers(d.players)).catch(() => {}); }, []);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "/") { e.preventDefault(); inputRef.current?.focus(); }
      if (e.key === "Escape") { setOpen(false); inputRef.current?.blur(); }
    };
    const click = (e: MouseEvent) => { if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("keydown", h); window.addEventListener("mousedown", click);
    return () => { window.removeEventListener("keydown", h); window.removeEventListener("mousedown", click); };
  }, []);

  const { pRes, cRes } = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (s.length < 2) return { pRes: [] as DbPlayer[], cRes: [] as { club: string; league: string; logo: string }[] };
    const pRes = players.filter((p) => p.player.toLowerCase().includes(s)).slice(0, 8);
    const seen = new Set<string>();
    const cRes: { club: string; league: string; logo: string }[] = [];
    for (const p of players) {
      if (p.squad && p.squad.toLowerCase().includes(s) && !seen.has(p.squad)) {
        seen.add(p.squad); cRes.push({ club: p.squad, league: p.league, logo: p.logo });
        if (cRes.length >= 4) break;
      }
    }
    return { pRes, cRes };
  }, [q, players]);

  const has = pRes.length > 0 || cRes.length > 0;

  return (
    <div ref={boxRef} style={{ position: "relative", margin: "0 0 4px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 13px", borderRadius: 10,
        background: hexA("#ffffff", 0.05), border: `1px solid ${open && has ? hexA(accent, 0.4) : hexA("#ffffff", 0.1)}` }}>
        <Icon name="search" size={15} color={hexA("#ffffff", 0.5)} />
        <input ref={inputRef} value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
          placeholder="선수·구단 검색…  (⌘/)" style={{ flex: 1, border: "none", outline: "none", background: "transparent", color: "inherit", fontSize: 13 }} />
        {q && <button onClick={() => { setQ(""); inputRef.current?.focus(); }} style={{ border: "none", background: "transparent", color: "inherit", opacity: 0.5, cursor: "pointer", fontSize: 13 }}>✕</button>}
      </div>

      {open && q.trim().length >= 2 && (
        <div style={{ position: "absolute", top: "calc(100% + 6px)", left: 0, right: 0, zIndex: 40,
          background: "rgba(16,16,22,0.99)", backdropFilter: "blur(10px)", borderRadius: 12,
          border: `1px solid ${hexA(accent, 0.25)}`, boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
          maxHeight: 460, overflowY: "auto", padding: 6 }}>
          {!has && <div style={{ padding: "14px 12px", fontSize: 12.5, opacity: 0.5 }}>검색 결과 없음</div>}
          {cRes.length > 0 && <div style={{ fontSize: 10, opacity: 0.45, padding: "6px 10px 3px", textTransform: "uppercase", letterSpacing: 0.5 }}>구단</div>}
          {cRes.map((c) => (
            <button key={c.club} onMouseDown={() => { onPickTeam(c.club, c.league); setOpen(false); setQ(""); }}
              style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", padding: "8px 10px", border: "none",
                background: "transparent", color: "inherit", cursor: "pointer", borderRadius: 8, textAlign: "left" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = hexA(accent, 0.12))}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
              {c.logo ? <img src={c.logo} alt="" style={{ width: 22, height: 22, objectFit: "contain" }} /> : <span style={{ width: 22 }} />}
              <span style={{ fontSize: 13 }}>{c.club}</span>
              <span style={{ fontSize: 10.5, opacity: 0.5, marginLeft: "auto" }}>{c.league}</span>
            </button>
          ))}
          {pRes.length > 0 && <div style={{ fontSize: 10, opacity: 0.45, padding: "8px 10px 3px", textTransform: "uppercase", letterSpacing: 0.5 }}>선수</div>}
          {pRes.map((p) => (
            <button key={`${p.player}-${p.squad}`} onMouseDown={() => { onPickPlayer(p.squad, p.league, p.player); setOpen(false); setQ(""); }}
              style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", padding: "7px 10px", border: "none",
                background: "transparent", color: "inherit", cursor: "pointer", borderRadius: 8, textAlign: "left" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = hexA(accent, 0.12))}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
              {p.photo ? <img src={p.photo} alt="" style={{ width: 28, height: 28, borderRadius: "50%", objectFit: "cover" }} /> : <span style={{ width: 28 }} />}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, fontWeight: 600 }}>{p.player}</div>
                <div style={{ fontSize: 10.5, opacity: 0.55 }}>{p.squad} · {p.pos} · {p.age}세 · {fmtEur(p.value_eur)}</div>
              </div>
              <span style={{ fontSize: 15, fontWeight: 800, color: tier(p.ovr).light }}>{p.ovr}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
