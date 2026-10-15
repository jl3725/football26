"use client";
import { useEffect, useMemo, useState } from "react";
import { getHeatmaps, type HeatmapData, type HeatmapPlayer } from "@/lib/api";
import { hexA } from "@/lib/ui";
import HeatmapPitch, { heat } from "./HeatmapPitch";
import { usePeek } from "./PlayerPeek";
import { Skel } from "./Skeleton";
import EmptyState from "./EmptyState";
import { LINE_COLOR, SvgAvatar, lastName } from "./NetShared";

// 팀 포지셔널 맵 — SHAPE · LINKS: 시즌 히트맵 평균 위치(사진) + 함께 그라운드에 있던 시간 연결선(패스 데이터 아님).
// 선수에 마우스를 올리면 그 선수의 히트맵이 깔리고 파트너 연결만 남는다. TERRITORY: 주전 14인 히트맵 합산.
// 공격 방향 → , 위 = 왼쪽 측면 · 아래 = 오른쪽 측면(예전엔 Sofascore 세로축 그대로라 좌우가 뒤바뀌어 있었다).
const W = 640, H = 414, PAD = 10;

function centroid(p: HeatmapPlayer, gw: number) {
  let sx = 0, sy = 0, sv = 0;
  p.grid.forEach((v, i) => { sx += (i % gw) * v; sy += Math.floor(i / gw) * v; sv += v; });
  return sv ? { cx: sx / sv, cy: sy / sv } : null;
}

function Pitch() {
  const s = hexA("#ffffff", 0.22);
  const iw = W - PAD * 2, ih = H - PAD * 2;
  return (
    <g stroke={s} strokeWidth="1.3" fill="none">
      <rect x={PAD} y={PAD} width={iw} height={ih} rx="4" />
      <line x1={W / 2} y1={PAD} x2={W / 2} y2={H - PAD} />
      <circle cx={W / 2} cy={H / 2} r={ih * 0.13} />
      <rect x={PAD} y={H / 2 - ih * 0.3} width={iw * 0.15} height={ih * 0.6} />
      <rect x={W - PAD - iw * 0.15} y={H / 2 - ih * 0.3} width={iw * 0.15} height={ih * 0.6} />
      <rect x={PAD} y={H / 2 - ih * 0.13} width={iw * 0.055} height={ih * 0.26} />
      <rect x={W - PAD - iw * 0.055} y={H / 2 - ih * 0.13} width={iw * 0.055} height={ih * 0.26} />
    </g>
  );
}

export default function TeamTerritory({ team, accent }: { team: string; accent: string }) {
  const peek = usePeek();
  const [d, setD] = useState<HeatmapData | null>(null);
  const [view, setView] = useState<"shape" | "territory">("shape");
  const [hover, setHover] = useState<string | null>(null);
  const [allLinks, setAllLinks] = useState(false);
  useEffect(() => {
    let a = true; setD(null);
    getHeatmaps(team).then((x) => a && setD(x)).catch(() => a && setD({ available: false, team, players: [] } as unknown as HeatmapData));
    return () => { a = false; };
  }, [team]);

  const agg = useMemo(() => {
    if (!d || !d.players.length) return null;
    const { gw, gh } = d, n = gw * gh;
    const byMin = [...d.players].sort((a, b) => b.minutes - a.minutes);
    const sum = new Array(n).fill(0);
    for (const p of byMin.slice(0, 14)) p.grid.forEach((v, i) => (sum[i] += v));
    const mx = Math.max(1, ...sum);
    const territory = sum.map((v) => Math.round((v / mx) * 100));
    const xi = byMin.slice(0, 11).map((p) => {
      const c = centroid(p, gw);
      if (!c) return null;
      return { p, x: PAD + ((c.cx + 0.5) / gw) * (W - PAD * 2), y: PAD + ((c.cy + 0.5) / gh) * (H - PAD * 2) };
    }).filter(Boolean) as { p: HeatmapPlayer; x: number; y: number }[];
    // 평균 위치가 겹치는 선수(인버티드 풀백과 수비형 미드 등)는 서로 밀어낸다 — 위치 의미는 유지할 만큼만
    const maxMin0 = Math.max(1, ...xi.map((n) => n.p.minutes));
    const rad = (n: { p: HeatmapPlayer }) => 14 + 7 * Math.sqrt(n.p.minutes / maxMin0);
    for (let it = 0; it < 40; it++) {
      for (let i = 0; i < xi.length; i++) for (let j = i + 1; j < xi.length; j++) {
        const a = xi[i], b = xi[j];
        const dx = b.x - a.x, dy = b.y - a.y, dist = Math.hypot(dx, dy) || 0.01, need = rad(a) + rad(b) + 28;   // 이름표 몫까지
        if (dist < need) {
          const push = (need - dist) / 2, ux = dx / dist, uy = dy / dist;
          a.x -= ux * push; a.y -= uy * push; b.x += ux * push; b.y += uy * push;
        }
      }
      for (const n of xi) {
        n.x = Math.max(PAD + 24, Math.min(W - PAD - 24, n.x));
        n.y = Math.max(PAD + 26, Math.min(H - PAD - 34, n.y));
      }
    }
    const at = Object.fromEntries(xi.map((n) => [n.p.player, n]));
    const links = (d.links ?? []).filter((e) => at[e.a] && at[e.b]);
    const maxL = Math.max(1, ...links.map((e) => e.minutes));
    const maxMin = Math.max(1, ...xi.map((n) => n.p.minutes));
    return { gw, gh, territory, xi, at, links, maxL, maxMin };
  }, [d]);

  if (!d) return <div style={{ maxWidth: 640, margin: "0 auto" }}><Skel h={380} r={14} /></div>;
  if (!d.available || !agg) return <EmptyState compact title="포지셔널 맵 없음" note="이번 시즌 히트맵은 아직 수집 전입니다" />;

  // 핵심 연결 = 선수마다 가장 오래 함께 뛴 3명(합집합) — 주전끼리는 거의 다 180분+ 라 전체는 빽빽하다
  const top3 = new Set<string>();
  if (!allLinks) {
    for (const n of agg.xi) {
      agg.links.filter((e) => e.a === n.p.player || e.b === n.p.player).sort((a, b) => b.minutes - a.minutes)
        .slice(0, 3).forEach((e) => top3.add(e.a + "|" + e.b));
    }
  }
  const shown = agg.links.filter((e) => e.minutes >= 180 && (allLinks || top3.has(e.a + "|" + e.b) || e.a === hover || e.b === hover));
  const hp = hover ? agg.xi.find((n) => n.p.player === hover)?.p : null;
  const bg = hp ? (() => { const mx = Math.max(1, ...hp.grid); return hp.grid.map((v) => Math.round((v / mx) * 100)); })() : agg.territory;
  const partners = hover ? agg.links.filter((e) => e.a === hover || e.b === hover).sort((a, b) => b.minutes - a.minutes).slice(0, 4) : [];
  const cw = (W - PAD * 2) / agg.gw, ch = (H - PAD * 2) / agg.gh;

  return (
    <div className="terr">
      <div className="net-toolbar">
        <div className="comp-seg chips5">
          <button className={view === "shape" ? "active" : ""} onClick={() => setView("shape")}>SHAPE · LINKS</button>
          <button className={view === "territory" ? "active" : ""} onClick={() => setView("territory")}>TERRITORY</button>
        </div>
        {view === "shape" && (
          <div className="comp-seg chips5">
            <button className={!allLinks ? "active" : ""} onClick={() => setAllLinks(false)}>핵심 연결</button>
            <button className={allLinks ? "active" : ""} onClick={() => setAllLinks(true)}>전체(180분+)</button>
          </div>
        )}
      </div>
      {view === "territory" ? (
        <div style={{ maxWidth: 560, margin: "0 auto" }}>
          <HeatmapPitch grid={agg.territory} gw={agg.gw} gh={agg.gh} id="team-terr" />
        </div>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} className="net-svg terr-svg" role="img"
          aria-label="주전 11명의 시즌 평균 위치와 함께 뛴 시간 연결 — 공격 방향 오른쪽, 위가 왼쪽 측면">
          <defs><filter id="terr-blur" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation={hp ? 9 : 11} /></filter></defs>
          <rect x="0" y="0" width={W} height={H} rx="14" fill="#0d1712" />
          <g filter="url(#terr-blur)" opacity={hp ? 0.95 : 0.45}>
            {bg.map((v, idx) => (v < 8 ? null : (
              <rect key={idx} x={PAD + (idx % agg.gw) * cw} y={PAD + Math.floor(idx / agg.gw) * ch} width={cw} height={ch} fill={heat(v)} />
            )))}
          </g>
          <Pitch />
          <text x={W - 16} y={26} textAnchor="end" fontSize="10.5" fill={hexA("#ffffff", 0.5)} fontWeight={700}>공격 →</text>
          <text x={W / 2} y={24} textAnchor="middle" fontSize="9.5" fill={hexA("#ffffff", 0.38)} letterSpacing="1">왼쪽 측면</text>
          <text x={W / 2} y={H - 16} textAnchor="middle" fontSize="9.5" fill={hexA("#ffffff", 0.38)} letterSpacing="1">오른쪽 측면</text>
          {shown.map((e) => {
            const a = agg.at[e.a], b = agg.at[e.b];
            const on = !hover || e.a === hover || e.b === hover;
            const w = e.minutes / agg.maxL;
            return <line key={e.a + e.b} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={hover && on ? accent : "#ffffff"}
              strokeOpacity={hover ? (on ? 0.95 : 0.06) : 0.18 + w * 0.5} strokeWidth={1 + w * 5.5} strokeLinecap="round" />;
          })}
          {agg.xi.map(({ p, x, y }) => {
            const r = 14 + 7 * Math.sqrt(p.minutes / agg.maxMin);
            const dim = !!hover && hover !== p.player && !partners.some((e) => e.a === p.player || e.b === p.player);
            return (
              <SvgAvatar key={p.player} x={x} y={y} r={r} photo={p.photo} name={`${p.player} · ${p.pos} · ${p.minutes}분`}
                ring={LINE_COLOR[p.line] || "#8a94a8"} ringW={hover === p.player ? 3.5 : 2.2} dim={dim}
                onEnter={() => setHover(p.player)} onLeave={() => setHover(null)}
                onClick={(ev) => peek(ev, { name: p.player, club: team, hint: { photo: p.photo, ovr: p.ovr, pos: p.pos } })}>
                <g transform={`translate(${r * 0.72},${-r * 0.72})`}>
                  <rect x={-11} y={-7} width={22} height={14} rx={7} fill="#0d1712" stroke={LINE_COLOR[p.line] || "#8a94a8"} strokeWidth={1} />
                  <text textAnchor="middle" dy="0.35em" fontSize="8" fontWeight={800} fill="#e8edf3">{p.pos.slice(0, 3)}</text>
                </g>
                <text y={r + 12} textAnchor="middle" fontSize="10.5" fontWeight={600} fill="#f2f5f7" stroke="#0d1712" strokeWidth={3}
                  paintOrder="stroke" style={{ pointerEvents: "none" }}>{lastName(p.player)}</text>
              </SvgAvatar>
            );
          })}
        </svg>
      )}
      <div className="net-hover terr-foot">
        {view === "territory" ? <em>주전 14인 히트맵 합산 — 팀이 실제로 점유하는 구역 · 공격 → · Sofascore</em>
          : hover ? (
            <>
              <b>{hover}</b> <em>히트맵 표시 중 · 함께 오래 뛴 파트너</em>
              {partners.map((e) => <span key={e.a + e.b}>{e.a === hover ? e.b : e.a} <i>{e.minutes}분</i></span>)}
            </>
          ) : <em>위치 = 시즌 히트맵 평균 · 선 = 선수별 가장 오래 함께 뛴 3명(굵기 = 함께 그라운드에 있던 시간, 패스 데이터 아님) · 선수에 마우스를 올리면 그 선수 히트맵</em>}
      </div>
    </div>
  );
}
