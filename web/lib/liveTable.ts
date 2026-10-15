import type { TableRow } from "./api";
import type { LiveEvent } from "./live";

// 잠정 순위 — 아직 결과 파일에 안 들어온 리그 경기(lab.pending)에 라이브 스코어(ESPN)를 더해 순위를 다시 매긴다.
// 진행 중이면 '지금 끝나면' 기준, 끝난 경기는 공식 반영(매일 08:15 match_refresh) 전까지 미리 보여 준다.
// 동률 처리는 승점 → 골득실 → 다득점 → 원래 순위(리그별 승자승 규칙은 공식 갱신 때 반영).
export type LiveMark = { state: "in" | "post"; label: string; gf: number; ga: number; res: "W" | "D" | "L" };
export type LiveTableRow = TableRow & { live?: LiveMark; move?: number };

export function liveTable(
  table: TableRow[] | undefined,
  pending: Record<string, { home: string; away: string }> | undefined,
  live: Record<string, LiveEvent>,
  label: (e: LiveEvent) => string,
): { rows: LiveTableRow[]; on: boolean; inPlay: boolean } {
  const base = table ?? [];
  if (!pending || !base.length) return { rows: base, on: false, inPlay: false };
  const add = new Map<string, LiveMark>();
  let inPlay = false;
  for (const [id, p] of Object.entries(pending)) {
    const e = live[id];
    if (!e || e.state === "pre") continue;
    const hs = Number(e.home.score ?? 0), as = Number(e.away.score ?? 0);
    const st = e.state as "in" | "post";
    if (st === "in") inPlay = true;
    const lb = label(e);
    add.set(p.home, { state: st, label: lb, gf: hs, ga: as, res: hs > as ? "W" : hs < as ? "L" : "D" });
    add.set(p.away, { state: st, label: lb, gf: as, ga: hs, res: as > hs ? "W" : as < hs ? "L" : "D" });
  }
  if (!add.size) return { rows: base, on: false, inPlay: false };
  const rows: LiveTableRow[] = base.map((t) => {
    const a = add.get(t.team);
    if (!a) return { ...t };
    return {
      ...t, live: a, played: t.played + 1,
      won: t.won + (a.res === "W" ? 1 : 0), drawn: t.drawn + (a.res === "D" ? 1 : 0), lost: t.lost + (a.res === "L" ? 1 : 0),
      gf: t.gf + a.gf, ga: t.ga + a.ga, gd: t.gd + a.gf - a.ga,
      points: t.points + (a.res === "W" ? 3 : a.res === "D" ? 1 : 0),
      form: [...t.form, a.res].slice(-5),
    };
  });
  rows.sort((x, y) => y.points - x.points || y.gd - x.gd || y.gf - x.gf || x.rank - y.rank);
  rows.forEach((r, i) => { r.move = r.rank - (i + 1); r.rank = i + 1; });
  return { rows, on: true, inPlay };
}
