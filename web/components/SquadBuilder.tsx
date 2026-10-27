"use client";
import { useEffect, useMemo, useState } from "react";
import { getBuilder, type BuilderPlayer } from "@/lib/api";
import { tier } from "@/lib/ui";
import { ovrMeaning, scoreMeaning } from "@/lib/meaning";
import { MeaningTag } from "./Meaning";
import Info from "./Info";
import { usePeek } from "./PlayerPeek";
import { surname } from "@/lib/names";

// Best XI 빌더 — 포메이션 칸마다 역할(GK·LB·CB·RB·DM·CM·AM·LW·RW·ST)이 있고, '선수 OVR × 그 역할 적합도'의 합이
// 가장 큰 배치를 고른다(헝가리안 알고리즘). 적합도: 주포지션 1.0 · 2/3포지션 0.95 · 비슷한 자리 0.85 · 같은 라인 0.75.
// 주·2·3포지션 = 실제로 선 자리(ESPN 라인업, src/positions.py). 예전엔 라인만 봐서 Calafiori(LB)가 RB 에 들어갔고,
// 이번 시즌 출전이 없는 Saliba(부상)·Guimarães 는 후보에서 빠졌다 → 전체 스쿼드 + '부상 제외' 토글.

type Role = "GK" | "LB" | "CB" | "RB" | "DM" | "CM" | "AM" | "LW" | "RW" | "ST";
type Slot = { role: Role; x: number; y: number };
const LINE: Record<Role, string> = { GK: "GK", LB: "DEF", CB: "DEF", RB: "DEF", DM: "MID", CM: "MID", AM: "MID", LW: "ATT", RW: "ATT", ST: "ATT" };
const COLOR: Record<string, string> = { GK: "#f4cf5e", DEF: "#6aa6e0", MID: "#4fc27f", ATT: "#e0707a" };
const NEAR: Record<Role, Role[]> = { LB: ["CB", "LW"], RB: ["CB", "RW"], CB: ["LB", "RB", "DM"], DM: ["CM", "CB"], CM: ["DM", "AM"],
  AM: ["CM", "LW", "RW", "ST"], LW: ["RW", "AM", "ST", "LB"], RW: ["LW", "AM", "ST", "RB"], ST: ["AM", "LW", "RW"], GK: [] };
const last = surname;

// y: 0 = 상대 골문(위) … 100 = 우리 골문, x: 왼쪽 → 오른쪽
const FORMATIONS: Record<string, Slot[]> = {
  "4-3-3": [{ role: "GK", x: 50, y: 92 }, { role: "LB", x: 14, y: 72 }, { role: "CB", x: 38, y: 77 }, { role: "CB", x: 62, y: 77 }, { role: "RB", x: 86, y: 72 },
    { role: "CM", x: 27, y: 50 }, { role: "DM", x: 50, y: 57 }, { role: "CM", x: 73, y: 50 }, { role: "LW", x: 18, y: 24 }, { role: "ST", x: 50, y: 16 }, { role: "RW", x: 82, y: 24 }],
  "4-2-3-1": [{ role: "GK", x: 50, y: 92 }, { role: "LB", x: 14, y: 72 }, { role: "CB", x: 38, y: 77 }, { role: "CB", x: 62, y: 77 }, { role: "RB", x: 86, y: 72 },
    { role: "DM", x: 36, y: 57 }, { role: "DM", x: 64, y: 57 }, { role: "LW", x: 18, y: 33 }, { role: "AM", x: 50, y: 34 }, { role: "RW", x: 82, y: 33 }, { role: "ST", x: 50, y: 14 }],
  "4-4-2": [{ role: "GK", x: 50, y: 92 }, { role: "LB", x: 14, y: 72 }, { role: "CB", x: 38, y: 77 }, { role: "CB", x: 62, y: 77 }, { role: "RB", x: 86, y: 72 },
    { role: "LW", x: 14, y: 46 }, { role: "CM", x: 38, y: 51 }, { role: "CM", x: 62, y: 51 }, { role: "RW", x: 86, y: 46 }, { role: "ST", x: 38, y: 18 }, { role: "ST", x: 62, y: 18 }],
  "4-1-4-1": [{ role: "GK", x: 50, y: 92 }, { role: "LB", x: 14, y: 72 }, { role: "CB", x: 38, y: 77 }, { role: "CB", x: 62, y: 77 }, { role: "RB", x: 86, y: 72 },
    { role: "DM", x: 50, y: 60 }, { role: "LW", x: 14, y: 40 }, { role: "CM", x: 38, y: 44 }, { role: "CM", x: 62, y: 44 }, { role: "RW", x: 86, y: 40 }, { role: "ST", x: 50, y: 15 }],
  "3-4-3": [{ role: "GK", x: 50, y: 92 }, { role: "CB", x: 28, y: 76 }, { role: "CB", x: 50, y: 78 }, { role: "CB", x: 72, y: 76 },
    { role: "LB", x: 12, y: 50 }, { role: "CM", x: 39, y: 53 }, { role: "CM", x: 61, y: 53 }, { role: "RB", x: 88, y: 50 }, { role: "LW", x: 20, y: 22 }, { role: "ST", x: 50, y: 15 }, { role: "RW", x: 80, y: 22 }],
  "3-5-2": [{ role: "GK", x: 50, y: 92 }, { role: "CB", x: 28, y: 76 }, { role: "CB", x: 50, y: 78 }, { role: "CB", x: 72, y: 76 },
    { role: "LB", x: 10, y: 50 }, { role: "CM", x: 33, y: 47 }, { role: "DM", x: 50, y: 56 }, { role: "CM", x: 67, y: 47 }, { role: "RB", x: 90, y: 50 }, { role: "ST", x: 39, y: 18 }, { role: "ST", x: 61, y: 18 }],
};

function fit(p: BuilderPlayer, role: Role): number {
  if (p.primary === role) return 1;
  if (p.secondary.includes(role)) return 0.95;
  if (role === "GK" || p.primary === "GK") return 0.2;
  if (NEAR[p.primary as Role]?.includes(role)) return 0.85;
  return LINE[p.primary as Role] === LINE[role] ? 0.75 : 0.55;
}
const score = (p: BuilderPlayer, role: Role) => p.ovr * fit(p, role);

// 헝가리안(최소 비용) — 칸 n ≤ 선수 m. 비용 = -점수. 반환: 칸마다 선수 인덱스(-1 = 없음)
function assign(cost: number[][]): number[] {
  const n = cost.length, m = cost[0]?.length ?? 0;
  if (!n || !m) return Array(n).fill(-1);
  const INF = 1e18, u = Array(n + 1).fill(0), v = Array(m + 1).fill(0), p = Array(m + 1).fill(0), way = Array(m + 1).fill(0);
  for (let i = 1; i <= n; i++) {
    p[0] = i;
    let j0 = 0;
    const minv = Array(m + 1).fill(INF), used = Array(m + 1).fill(false);
    do {
      used[j0] = true;
      const i0 = p[j0];
      let delta = INF, j1 = 0;
      for (let j = 1; j <= m; j++) {
        if (used[j]) continue;
        const cur = cost[i0 - 1][j - 1] - u[i0] - v[j];
        if (cur < minv[j]) { minv[j] = cur; way[j] = j0; }
        if (minv[j] < delta) { delta = minv[j]; j1 = j; }
      }
      for (let j = 0; j <= m; j++) {
        if (used[j]) { u[p[j]] += delta; v[j] -= delta; } else minv[j] -= delta;
      }
      j0 = j1;
    } while (p[j0] !== 0);
    do { const j1 = way[j0]; p[j0] = p[j1]; j0 = j1; } while (j0);
  }
  const res = Array(n).fill(-1);
  for (let j = 1; j <= m; j++) if (p[j]) res[p[j] - 1] = j - 1;
  return res;
}

export default function SquadBuilder({ team, accent }: { team: string; accent: string }) {
  const [players, setPlayers] = useState<BuilderPlayer[] | null>(null);
  const [formation, setFormation] = useState("4-3-3");
  const [overrides, setOverrides] = useState<Record<number, string>>({});
  const [pick, setPick] = useState<number | null>(null);
  const [availOnly, setAvailOnly] = useState(true);    // 부상 제외 — 기본 켬(다음 경기에 뛸 수 있는 XI)
  const peek = usePeek();
  useEffect(() => {
    let a = true; setPlayers(null); setOverrides({});
    getBuilder(team).then((d) => {
      if (!a) return;
      setPlayers(d.players);
      // 시작 포메이션 = 실제로 가장 많이 쓴 것(Overview FORMATION 과 같은 기준)
      if (d.formation && FORMATIONS[d.formation]) setFormation(d.formation);
    }).catch(() => a && setPlayers([]));
    return () => { a = false; };
  }, [team]);

  const slots = FORMATIONS[formation];
  const pool = useMemo(() => (players ?? []).filter((p) => !availOnly || !p.injured), [players, availOnly]);
  const { xi, bench, teamOvr, fitAvg } = useMemo(() => {
    const fixed = new Set(Object.values(overrides));
    const free = pool.filter((p) => !fixed.has(p.player));
    const openIdx = slots.map((_, i) => i).filter((i) => !overrides[i]);
    const pickIdx = assign(openIdx.map((i) => free.map((p) => -score(p, slots[i].role))));
    const xi: (BuilderPlayer | null)[] = slots.map((_, i) => (overrides[i] ? pool.find((p) => p.player === overrides[i]) ?? null : null));
    openIdx.forEach((si, k) => { xi[si] = pickIdx[k] >= 0 ? free[pickIdx[k]] : null; });
    const inXI = new Set(xi.filter(Boolean).map((p) => p!.player));
    const bench = pool.filter((p) => !inXI.has(p.player));
    const rated = xi.map((p, i) => (p ? { p, f: fit(p, slots[i].role) } : null)).filter(Boolean) as { p: BuilderPlayer; f: number }[];
    const teamOvr = rated.length ? Math.round(rated.reduce((s, r) => s + r.p.ovr * r.f, 0) / rated.length) : 0;
    const fitAvg = rated.length ? Math.round((rated.reduce((s, r) => s + r.f, 0) / rated.length) * 100) : 0;
    return { xi, bench, teamOvr, fitAvg };
  }, [pool, slots, overrides]);

  if (players === null) return <div className="skel-wrap"><span className="skel" style={{ display: "block", height: 430, borderRadius: 16 }} /></div>;
  const cands = pick == null ? [] : [...pool].filter((p) => !xi.some((x, i) => i !== pick && x?.player === p.player))
    .sort((a, b) => score(b, slots[pick].role) - score(a, slots[pick].role));
  const tagOf = (p: BuilderPlayer, role: Role) =>
    p.primary === role ? "주" : p.secondary.includes(role) ? "멀티" : `${p.primary}`;

  return (
    <div className="sb5">
      <div className="sb5-top">
        <div className="seg5">
          {Object.keys(FORMATIONS).map((f) => (
            <button key={f} className={f === formation ? "on" : ""} onClick={() => { setFormation(f); setOverrides({}); setPick(null); }}>{f}</button>
          ))}
        </div>
        <label className="sb5-tg"><input type="checkbox" checked={availOnly} onChange={(e) => { setAvailOnly(e.target.checked); setOverrides({}); }} />부상 선수 제외</label>
        <div className="sb5-ovr" style={{ flexWrap: "wrap", rowGap: 4 }}>
          <em>XI OVR</em>
          <b style={{ color: tier(teamOvr).light }} title={`베스트 XI 평균 OVR(자리 적합도 반영) ${teamOvr} · ${ovrMeaning(teamOvr).label}`}>{teamOvr}</b>
          <MeaningTag sm m={ovrMeaning(teamOvr)} title="OVR 등급(OVR GUIDE 와 같은 띠)" />
          <span>
            포지션 적합도 <b style={{ font: "inherit", fontWeight: 700, color: scoreMeaning(fitAvg).c }}>{fitAvg}%</b>
            <Info label="포지션 적합도 기준">
              <p><b>포지션 적합도</b> = 선수들이 본래 자리에 얼마나 맞게 섰는지(XI 평균).</p>
              <p>주 포지션 100% · 멀티 95% · 비슷한 자리 85% · 같은 라인 75%</p>
              <p className="muted">포지션 = 실제로 선 자리(이번 시즌 + 지난 시즌 선발, 부족하면 Transfermarkt).</p>
            </Info>
          </span>
        </div>
        {Object.keys(overrides).length > 0 && <button className="sb5-reset" onClick={() => { setOverrides({}); setPick(null); }}>자동 배치로</button>}
      </div>
      <div className="sb5-grid">
        <div className="sb5-pitch">
          {slots.map((s, i) => {
            const p = xi[i];
            const f = p ? fit(p, s.role) : 0;
            return (
              <button key={i} className={`sb5-slot${pick === i ? " on" : ""}${p?.injured ? " inj" : ""}`} style={{ left: `${s.x}%`, top: `${s.y}%` }}
                onClick={() => setPick(pick === i ? null : i)} title={p ? `${p.player} · ${s.role} 적합도 ${Math.round(f * 100)}%` : s.role}>
                <span className="sb5-ph" style={{ borderColor: COLOR[LINE[s.role]] }}>
                  {p?.photo ? <img src={p.photo} alt="" /> : <i>{s.role}</i>}
                  {p && <b className="sb5-o" style={{ background: tier(p.ovr).deep }}>{p.ovr}</b>}
                  {p?.injured && <em className="sb5-inj">+</em>}
                </span>
                <span className="sb5-nm">{p ? last(p.player) : "—"}</span>
                <span className={`sb5-rl${p && f < 0.95 ? " off" : ""}`}>{s.role}{p && f < 0.95 ? ` · ${p.primary}` : ""}</span>
              </button>
            );
          })}
        </div>
        <div className="sb5-side">
          {pick != null ? (
            <>
              <div className="sb5-st">{slots[pick].role} 자리 · 교체 선수 <span>적합도 × OVR 순</span></div>
              <div className="sb5-list">
                {cands.map((p) => (
                  <button key={p.player} className="sb5-row" onClick={() => { setOverrides((o) => ({ ...o, [pick]: p.player })); setPick(null); }}>
                    {p.photo ? <img src={p.photo} alt="" /> : <span className="ph" />}
                    <span className="sb5-who"><b>{p.player}</b><em>{[p.primary, ...p.secondary].join(" · ")}{p.minutes === 0 ? " · 출전 없음" : ""}{p.injured ? ` · 부상 ${p.injured.until ? `~${p.injured.until.slice(0, 5)}` : ""}` : ""}</em></span>
                    <span className={`sb5-tag ${tagOf(p, slots[pick].role) === "주" ? "p" : tagOf(p, slots[pick].role) === "멀티" ? "s" : "x"}`}>{tagOf(p, slots[pick].role)}</span>
                    <b className="sb5-ov" style={{ color: tier(p.ovr).light }}>{p.ovr}</b>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <div className="sb5-st">벤치 · {bench.length}</div>
              <div className="sb5-list">
                {bench.map((p) => (
                  <button key={p.player} className="sb5-row" onClick={(e) => peek(e, { name: p.player, club: team, hint: { photo: p.photo, ovr: p.ovr } })}>
                    {p.photo ? <img src={p.photo} alt="" /> : <span className="ph" />}
                    <span className="sb5-who"><b>{p.player}</b><em>{[p.primary, ...p.secondary].join(" · ")}{p.minutes === 0 ? " · 출전 없음" : ""}{p.injured ? ` · 부상` : ""}</em></span>
                    <b className="sb5-ov" style={{ color: tier(p.ovr).light }}>{p.ovr}</b>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
