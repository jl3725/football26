"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { getDatabase, fmtEur, type DbPlayer } from "@/lib/api";
import { hexA, tier } from "@/lib/ui";
import Icon from "./Icon";

type Club = { club: string; league: string; logo: string };
type Item = { kind: "club"; c: Club } | { kind: "player"; p: DbPlayer };

const LEAGUE_ABBR: Record<string, string> = {
  EPL: "EPL", LaLiga: "LaLiga", SerieA: "Serie A", Bundesliga: "Bundes", Ligue1: "Ligue 1",
  LigaPortugal: "Liga POR", Eredivisie: "Erediv.", BelgianProLeague: "Belg.",
};

// FM식 전역 검색 — 전 리그 선수·구단 즉시 조회 → 클릭/↵ 시 점프. ⌘/Ctrl+/ 로 포커스.
export default function GlobalSearch({ accent, onPickPlayer, onPickTeam }: {
  accent: string;
  onPickPlayer: (club: string, league: string, player: string) => void;
  onPickTeam: (club: string, league: string) => void;
}) {
  const [players, setPlayers] = useState<DbPlayer[]>([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => { getDatabase().then((d) => setPlayers(d.players)).catch(() => {}); }, []);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "/") { e.preventDefault(); inputRef.current?.focus(); setOpen(true); }
      if (e.key === "Escape") { setOpen(false); inputRef.current?.blur(); }
    };
    const click = (e: MouseEvent) => { if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("keydown", h); window.addEventListener("mousedown", click);
    return () => { window.removeEventListener("keydown", h); window.removeEventListener("mousedown", click); };
  }, []);

  const s = q.trim().toLowerCase();
  const short = s.length < 2;

  const suggestions = useMemo(
    () => [...players].sort((a, b) => b.ovr - a.ovr).slice(0, 7),
    [players]
  );

  const { pRes, cRes } = useMemo(() => {
    if (short) return { pRes: [] as DbPlayer[], cRes: [] as Club[] };
    const pRes = players.filter((p) => p.player.toLowerCase().includes(s))
      .sort((a, b) => b.ovr - a.ovr).slice(0, 8);
    const seen = new Set<string>();
    const cRes: Club[] = [];
    for (const p of players) {
      if (p.squad && p.squad.toLowerCase().includes(s) && !seen.has(p.squad)) {
        seen.add(p.squad); cRes.push({ club: p.squad, league: p.league, logo: p.logo });
        if (cRes.length >= 5) break;
      }
    }
    return { pRes, cRes };
  }, [s, short, players]);

  // 키보드 내비게이션용 평면 리스트
  const items: Item[] = useMemo(() => (
    short
      ? suggestions.map((p) => ({ kind: "player" as const, p }))
      : [...cRes.map((c) => ({ kind: "club" as const, c })), ...pRes.map((p) => ({ kind: "player" as const, p }))]
  ), [short, suggestions, cRes, pRes]);

  useEffect(() => { setActive(0); }, [q]);
  useEffect(() => { rowRefs.current[active]?.scrollIntoView({ block: "nearest" }); }, [active]);

  const pick = (it: Item) => {
    if (it.kind === "club") onPickTeam(it.c.club, it.c.league);
    else onPickPlayer(it.p.squad, it.p.league, it.p.player);
    setOpen(false); setQ("");
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (!open) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(i + 1, items.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter" && items[active]) { e.preventDefault(); pick(items[active]); }
  };

  const focused = open;
  let idx = -1; // 평면 인덱스 카운터(렌더 중 증가)

  const PlayerRow = (p: DbPlayer, i: number) => {
    const t = tier(p.ovr);
    const on = i === active;
    return (
      <button key={`p-${p.player}-${p.squad}`} ref={(el) => { rowRefs.current[i] = el; }}
        onMouseEnter={() => setActive(i)} onMouseDown={() => pick({ kind: "player", p })}
        style={{ display: "flex", alignItems: "center", gap: 11, width: "100%", padding: "8px 10px",
          border: "none", background: on ? hexA(accent, 0.14) : "transparent", color: "inherit",
          cursor: "pointer", borderRadius: 9, textAlign: "left",
          boxShadow: on ? `inset 2px 0 0 ${accent}` : "none", transition: "background .1s" }}>
        {p.photo
          ? <img src={p.photo} alt="" style={{ width: 30, height: 30, borderRadius: "50%", objectFit: "cover", border: `1px solid ${hexA("#fff", 0.12)}` }} />
          : <span style={{ width: 30, height: 30, borderRadius: "50%", background: hexA("#fff", 0.06), display: "inline-block" }} />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12.8, fontWeight: 600, display: "flex", alignItems: "center", gap: 6, whiteSpace: "nowrap", overflow: "hidden" }}>
            {p.player}
            {p.big_match && <span title="빅매치 검증" style={{ color: "#f4cf5e", fontSize: 11 }}>◆</span>}
          </div>
          <div style={{ fontSize: 10.5, opacity: 0.55, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {p.squad} · {p.pos}{p.age ? ` · ${p.age}세` : ""} · {fmtEur(p.value_eur)}
          </div>
        </div>
        {p.role && <span style={{ fontSize: 9.5, padding: "2px 6px", borderRadius: 5, background: hexA("#fff", 0.06), opacity: 0.75, whiteSpace: "nowrap" }}>{p.role}</span>}
        <span style={{ minWidth: 30, textAlign: "center", fontSize: 14, fontWeight: 800, color: t.light,
          padding: "3px 6px", borderRadius: 7, background: hexA(t.deep, 0.28), border: `1px solid ${hexA(t.light, 0.35)}` }}>{p.ovr}</span>
      </button>
    );
  };

  const ClubRow = (c: Club, i: number) => {
    const on = i === active;
    return (
      <button key={`c-${c.club}`} ref={(el) => { rowRefs.current[i] = el; }}
        onMouseEnter={() => setActive(i)} onMouseDown={() => pick({ kind: "club", c })}
        style={{ display: "flex", alignItems: "center", gap: 11, width: "100%", padding: "8px 10px",
          border: "none", background: on ? hexA(accent, 0.14) : "transparent", color: "inherit",
          cursor: "pointer", borderRadius: 9, textAlign: "left",
          boxShadow: on ? `inset 2px 0 0 ${accent}` : "none", transition: "background .1s" }}>
        {c.logo ? <img src={c.logo} alt="" style={{ width: 26, height: 26, objectFit: "contain" }} /> : <span style={{ width: 26 }} />}
        <span style={{ fontSize: 13, fontWeight: 600 }}>{c.club}</span>
        <span style={{ fontSize: 10, opacity: 0.55, marginLeft: "auto", padding: "2px 7px", borderRadius: 5, background: hexA("#fff", 0.06) }}>
          {LEAGUE_ABBR[c.league] || c.league}
        </span>
      </button>
    );
  };

  return (
    <div ref={boxRef} style={{ position: "relative", margin: "0 0 4px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "9px 14px", borderRadius: 12,
        background: focused ? hexA(accent, 0.06) : hexA("#ffffff", 0.05),
        border: `1px solid ${focused ? hexA(accent, 0.45) : hexA("#ffffff", 0.1)}`,
        boxShadow: focused ? `0 0 0 3px ${hexA(accent, 0.1)}` : "none", transition: "all .15s" }}>
        <Icon name="search" size={16} color={focused ? accent : hexA("#ffffff", 0.5)} />
        <input ref={inputRef} value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)} onKeyDown={onKey}
          placeholder="선수 · 구단 검색"
          style={{ flex: 1, border: "none", outline: "none", background: "transparent", color: "inherit", fontSize: 13.5 }} />
        {q
          ? <button onMouseDown={(e) => { e.preventDefault(); setQ(""); inputRef.current?.focus(); }}
              style={{ border: "none", background: hexA("#fff", 0.08), color: "inherit", opacity: 0.6, cursor: "pointer",
                fontSize: 11, borderRadius: 6, width: 20, height: 20, lineHeight: "20px", padding: 0 }}>✕</button>
          : <kbd style={{ fontSize: 10, opacity: 0.4, border: `1px solid ${hexA("#fff", 0.15)}`, borderRadius: 5, padding: "2px 6px", fontFamily: "inherit" }}>⌘/</kbd>}
      </div>

      {open && (
        <div style={{ position: "absolute", top: "calc(100% + 7px)", left: 0, right: 0, zIndex: 40,
          background: "rgba(14,14,20,0.985)", backdropFilter: "blur(14px)", borderRadius: 14,
          border: `1px solid ${hexA(accent, 0.28)}`, boxShadow: "0 16px 48px rgba(0,0,0,0.55)",
          overflow: "hidden" }}>
          {/* 헤더 */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "8px 13px", borderBottom: `1px solid ${hexA("#fff", 0.07)}`,
            background: `linear-gradient(90deg, ${hexA(accent, 0.1)}, transparent)` }}>
            <span style={{ fontSize: 10.5, letterSpacing: 0.6, textTransform: "uppercase", opacity: 0.6, fontWeight: 700 }}>
              {short ? "추천 · 최고 평점" : `결과 ${cRes.length + pRes.length}`}
            </span>
            <span style={{ fontSize: 10, opacity: 0.4 }}>전 리그</span>
          </div>

          <div style={{ maxHeight: 430, overflowY: "auto", padding: 6 }}>
            {!short && items.length === 0 && (
              <div style={{ padding: "22px 12px", fontSize: 12.5, opacity: 0.5, textAlign: "center" }}>
                <div style={{ fontSize: 20, opacity: 0.4, marginBottom: 6 }}>⌕</div>
                "{q}" 검색 결과가 없습니다
              </div>
            )}

            {short && items.map((it) => { idx++; return it.kind === "player" ? PlayerRow(it.p, idx) : null; })}

            {!short && cRes.length > 0 && <div style={{ fontSize: 9.5, opacity: 0.4, padding: "6px 10px 3px", textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 700 }}>구단 {cRes.length}</div>}
            {!short && cRes.map((c) => { idx++; return ClubRow(c, idx); })}
            {!short && pRes.length > 0 && <div style={{ fontSize: 9.5, opacity: 0.4, padding: "8px 10px 3px", textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 700 }}>선수 {pRes.length}</div>}
            {!short && pRes.map((p) => { idx++; return PlayerRow(p, idx); })}
          </div>

          {/* 푸터 힌트 */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "7px 13px",
            borderTop: `1px solid ${hexA("#fff", 0.07)}`, fontSize: 10, opacity: 0.45 }}>
            <span><kbd style={kbd}>↑</kbd><kbd style={kbd}>↓</kbd> 이동</span>
            <span><kbd style={kbd}>↵</kbd> 선택</span>
            <span><kbd style={kbd}>esc</kbd> 닫기</span>
          </div>
        </div>
      )}
    </div>
  );
}

const kbd: React.CSSProperties = {
  fontFamily: "inherit", fontSize: 9.5, border: "1px solid rgba(255,255,255,0.18)",
  borderRadius: 4, padding: "1px 4px", marginRight: 2,
};
