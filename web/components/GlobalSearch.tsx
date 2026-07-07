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
const kbd: React.CSSProperties = {
  fontFamily: "inherit", fontSize: 9.5, border: "1px solid rgba(255,255,255,0.18)",
  borderRadius: 4, padding: "1px 5px", marginRight: 2, lineHeight: 1.5,
};

// FM식 전역 검색 — ⌘/Ctrl+/ 또는 클릭으로 커맨드 팔레트를 열어 전 리그 선수·구단 조회.
export default function GlobalSearch({ accent, onPickPlayer, onPickTeam }: {
  accent: string;
  onPickPlayer: (club: string, league: string, player: string) => void;
  onPickTeam: (club: string, league: string) => void;
}) {
  const [players, setPlayers] = useState<DbPlayer[]>([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState(false);   // 등장 애니메이션
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => { getDatabase().then((d) => setPlayers(d.players)).catch(() => {}); }, []);

  useEffect(() => {
    if (open) {
      const id = requestAnimationFrame(() => { setShown(true); inputRef.current?.focus(); });
      return () => cancelAnimationFrame(id);
    }
    setShown(false);
  }, [open]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "/") { e.preventDefault(); setOpen(true); }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const close = () => { setOpen(false); setQ(""); };

  const s = q.trim().toLowerCase();
  const short = s.length < 2;

  const suggestions = useMemo(() => [...players].sort((a, b) => b.ovr - a.ovr).slice(0, 7), [players]);

  const { pRes, cRes } = useMemo(() => {
    if (short) return { pRes: [] as DbPlayer[], cRes: [] as Club[] };
    const pRes = players.filter((p) => p.player.toLowerCase().includes(s)).sort((a, b) => b.ovr - a.ovr).slice(0, 8);
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
    close();
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(i + 1, items.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter" && items[active]) { e.preventDefault(); pick(items[active]); }
  };

  let idx = -1;
  const PlayerRow = (p: DbPlayer, i: number) => {
    const t = tier(p.ovr);
    const on = i === active;
    return (
      <button key={`p-${p.player}-${p.squad}`} ref={(el) => { rowRefs.current[i] = el; }}
        onMouseEnter={() => setActive(i)} onMouseDown={() => pick({ kind: "player", p })}
        style={{ display: "flex", alignItems: "center", gap: 13, width: "100%", padding: "10px 12px",
          border: "none", background: on ? hexA(accent, 0.15) : "transparent", color: "inherit",
          cursor: "pointer", borderRadius: 11, textAlign: "left",
          boxShadow: on ? `inset 3px 0 0 ${accent}` : "none", transition: "background .1s" }}>
        {p.photo
          ? <img src={p.photo} alt="" style={{ width: 38, height: 38, borderRadius: "50%", objectFit: "cover", border: `1.5px solid ${on ? hexA(accent, 0.6) : hexA("#fff", 0.12)}` }} />
          : <span style={{ width: 38, height: 38, borderRadius: "50%", background: hexA("#fff", 0.06), display: "inline-block" }} />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, display: "flex", alignItems: "center", gap: 6, whiteSpace: "nowrap", overflow: "hidden" }}>
            {p.player}
            {p.big_match && <span title="빅매치 검증" style={{ color: "#f4cf5e", fontSize: 11 }}>◆</span>}
          </div>
          <div style={{ fontSize: 11, opacity: 0.55, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", marginTop: 1 }}>
            {p.squad} · {p.pos}{p.age ? ` · ${p.age}세` : ""}{p.nationality ? ` · ${p.nationality}` : ""} · {fmtEur(p.value_eur)}
          </div>
        </div>
        {p.role && <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 6, background: hexA("#fff", 0.07), opacity: 0.75, whiteSpace: "nowrap" }}>{p.role}</span>}
        <span style={{ minWidth: 34, textAlign: "center", fontSize: 15, fontWeight: 800, color: t.light,
          padding: "4px 7px", borderRadius: 8, background: hexA(t.deep, 0.3), border: `1px solid ${hexA(t.light, 0.4)}` }}>{p.ovr}</span>
      </button>
    );
  };
  const ClubRow = (c: Club, i: number) => {
    const on = i === active;
    return (
      <button key={`c-${c.club}`} ref={(el) => { rowRefs.current[i] = el; }}
        onMouseEnter={() => setActive(i)} onMouseDown={() => pick({ kind: "club", c })}
        style={{ display: "flex", alignItems: "center", gap: 13, width: "100%", padding: "10px 12px",
          border: "none", background: on ? hexA(accent, 0.15) : "transparent", color: "inherit",
          cursor: "pointer", borderRadius: 11, textAlign: "left",
          boxShadow: on ? `inset 3px 0 0 ${accent}` : "none", transition: "background .1s" }}>
        {c.logo ? <img src={c.logo} alt="" style={{ width: 32, height: 32, objectFit: "contain" }} /> : <span style={{ width: 32 }} />}
        <span style={{ fontSize: 14, fontWeight: 600 }}>{c.club}</span>
        <span style={{ fontSize: 10.5, opacity: 0.6, marginLeft: "auto", padding: "3px 9px", borderRadius: 6, background: hexA("#fff", 0.07) }}>
          {LEAGUE_ABBR[c.league] || c.league}
        </span>
      </button>
    );
  };

  return (
    <>
      {/* 트리거 (상단바 자리) */}
      <button onClick={() => setOpen(true)}
        style={{ display: "flex", alignItems: "center", gap: 9, width: "100%", margin: "0 0 4px",
          padding: "9px 14px", borderRadius: 12, cursor: "text", textAlign: "left",
          background: hexA("#ffffff", 0.05), border: `1px solid ${hexA("#ffffff", 0.1)}`, color: "inherit",
          transition: "all .15s" }}
        onMouseEnter={(e) => { e.currentTarget.style.borderColor = hexA(accent, 0.35); e.currentTarget.style.background = hexA(accent, 0.05); }}
        onMouseLeave={(e) => { e.currentTarget.style.borderColor = hexA("#ffffff", 0.1); e.currentTarget.style.background = hexA("#ffffff", 0.05); }}>
        <Icon name="search" size={16} color={hexA("#ffffff", 0.5)} />
        <span style={{ flex: 1, fontSize: 13.5, opacity: 0.5 }}>선수 · 구단 검색</span>
        <kbd style={{ ...kbd, opacity: 0.4 }}>⌘/</kbd>
      </button>

      {/* 커맨드 팔레트 오버레이 */}
      {open && (
        <div onMouseDown={close}
          style={{ position: "fixed", inset: 0, zIndex: 100, display: "flex", justifyContent: "center", alignItems: "flex-start",
            paddingTop: "11vh", background: hexA("#05060a", shown ? 0.62 : 0),
            backdropFilter: shown ? "blur(7px)" : "blur(0px)", WebkitBackdropFilter: shown ? "blur(7px)" : "blur(0px)",
            transition: "background .2s, backdrop-filter .2s" }}>
          <div onMouseDown={(e) => e.stopPropagation()}
            style={{ width: "min(600px, 92vw)", background: "rgba(15,16,23,0.985)", borderRadius: 18,
              border: `1px solid ${hexA(accent, 0.3)}`, boxShadow: `0 24px 80px rgba(0,0,0,0.6), 0 0 0 1px ${hexA(accent, 0.08)}`,
              overflow: "hidden", opacity: shown ? 1 : 0,
              transform: shown ? "translateY(0) scale(1)" : "translateY(-10px) scale(0.97)",
              transition: "opacity .2s, transform .2s cubic-bezier(.2,.8,.2,1)" }}>
            {/* 입력 */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px 20px",
              borderBottom: `1px solid ${hexA("#fff", 0.07)}`, background: `linear-gradient(90deg, ${hexA(accent, 0.08)}, transparent)` }}>
              <Icon name="search" size={19} color={accent} />
              <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
                placeholder="선수 · 구단 검색"
                style={{ flex: 1, border: "none", outline: "none", background: "transparent", color: "inherit", fontSize: 16.5, fontWeight: 500 }} />
              {q
                ? <button onMouseDown={(e) => { e.preventDefault(); setQ(""); inputRef.current?.focus(); }}
                    style={{ border: "none", background: hexA("#fff", 0.08), color: "inherit", opacity: 0.6, cursor: "pointer",
                      fontSize: 12, borderRadius: 7, width: 22, height: 22, padding: 0 }}>✕</button>
                : <kbd style={kbd}>esc</kbd>}
            </div>

            {/* 결과 */}
            <div style={{ maxHeight: "52vh", overflowY: "auto", padding: 8 }}>
              {!short && items.length === 0 && (
                <div style={{ padding: "34px 12px", fontSize: 13, opacity: 0.5, textAlign: "center" }}>
                  <div style={{ fontSize: 26, opacity: 0.35, marginBottom: 8 }}>⌕</div>
                  "{q}" 검색 결과가 없습니다
                </div>
              )}
              {short && (
                <div style={{ fontSize: 9.5, opacity: 0.4, padding: "6px 12px 4px", textTransform: "uppercase", letterSpacing: 0.7, fontWeight: 700 }}>추천 · 최고 평점</div>
              )}
              {short && items.map((it) => { idx++; return it.kind === "player" ? PlayerRow(it.p, idx) : null; })}

              {!short && cRes.length > 0 && <div style={{ fontSize: 9.5, opacity: 0.4, padding: "6px 12px 4px", textTransform: "uppercase", letterSpacing: 0.7, fontWeight: 700 }}>구단 {cRes.length}</div>}
              {!short && cRes.map((c) => { idx++; return ClubRow(c, idx); })}
              {!short && pRes.length > 0 && <div style={{ fontSize: 9.5, opacity: 0.4, padding: "10px 12px 4px", textTransform: "uppercase", letterSpacing: 0.7, fontWeight: 700 }}>선수 {pRes.length}</div>}
              {!short && pRes.map((p) => { idx++; return PlayerRow(p, idx); })}
            </div>

            {/* 푸터 */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 16px",
              borderTop: `1px solid ${hexA("#fff", 0.07)}`, fontSize: 10.5, opacity: 0.5 }}>
              <span style={{ display: "flex", gap: 13 }}>
                <span><kbd style={kbd}>↑</kbd><kbd style={kbd}>↓</kbd> 이동</span>
                <span><kbd style={kbd}>↵</kbd> 선택</span>
              </span>
              <span style={{ opacity: 0.7 }}>{short ? "전 리그" : `${cRes.length + pRes.length} 결과`}</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
