"use client";
import type { Placement } from "@/lib/api";
import { usePeek } from "./PlayerPeek";
import { surname } from "@/lib/names";
import { SusCard } from "./AbsenceMark";

const KIND_COLOR: Record<string, string> = { GK: "#37c98a", DEF: "#4c8ef0", MID: "#e0a53a", FWD: "#e2564f" };

function lastName(name: string): string {
  return !name || name === "—" ? "—" : surname(name);   // 'van Dijk'·'Mac Allister'(lib/names)
}

function initials(name: string): string {
  if (!name || name === "—" || name === "영입 필요") return "?";
  const p = name.split(" ").filter(Boolean);
  if (p.length >= 2) return (p[0][0] + p[p.length - 1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

// SVG 배경(잔디+라인) + HTML 토큰(둥근 얼굴). clipPath 미사용 → id 충돌·렌더 불안정 없음.
// team 을 주면 토큰 클릭 → PlayerPeek 미니 프로필.
// showOut=false — 바뀐 자리 '↔ 빠진 선수'를 그림 아래 목록이 이미 보여 줄 때(THIS WEEK 예상 XI): 그림 안 둘째 줄이 아래 줄 선수와 겹쳤다
export default function Pitch({ placements, accent, team, metric = "OVR", showOut = true }: { placements: Placement[]; formation?: string; accent?: string; idKey?: string; team?: string; metric?: string; showOut?: boolean }) {
  const peek = usePeek();
  // 이름 겹침 방지 — 같은 줄(세로 6% 이내) 옆 선수와의 가로 간격만큼만 이름 폭을 주고(컨테이너 폭 cqw 기준),
  // 너무 가까우면(14% 미만) 이름을 위·아래로 번갈아 놓는다. 예전엔 82px 고정이라 스리백·5미드·폰에서 겹쳤다.
  // 줄(세로 5 이내)마다 옆 선수 간격이 MIN_GAP 보다 좁으면 그 줄을 가운데 기준으로 넓힌다(경기장 안 6~94). 스리백(37·50·63)은
  // 간격 13 이라 가운데 수비수 이름이 위로 올라가 미드필더 줄에 섞이고, 골키퍼가 가운데 수비수 아래에 겹쳤다(2026-11-03 사용자)
  const MIN_GAP = 18;
  const xs = placements.map((p) => p.x);
  placements.forEach((a, i) => {
    const row = placements.map((b, j) => ({ j, x: b.x, y: b.y })).filter((b) => Math.abs(b.y - a.y) < 5).sort((u, v) => u.x - v.x);
    if (row.length < 2 || row[0].j !== i) return;                 // 줄마다 한 번(가장 왼쪽 선수 차례에)
    const gap = Math.min(...row.slice(1).map((b, k) => b.x - row[k].x));
    if (gap <= 0 || gap >= MIN_GAP) return;
    const f = MIN_GAP / gap;
    row.forEach((b) => { xs[b.j] = Math.max(6, Math.min(94, 50 + (b.x - 50) * f)); });
  });
  // 골키퍼는 골문 쪽으로 — 수비 줄과 세로 간격을 벌림
  const ys = placements.map((p) => (p.kind === "GK" ? Math.min(92, p.y + 4) : p.y));
  const pos = placements.map((_, i) => ({ left: 4 + (xs[i] / 100) * 92, top: ((4 + (ys[i] / 100) * 100) / 108) * 100 }));
  const gapOf = pos.map((a, i) => Math.min(100, ...pos.filter((b, j) => j !== i && Math.abs(b.top - a.top) < 6).map((b) => Math.abs(b.left - a.left))));
  const order = pos.map((a, i) => ({ i, a })).filter(({ i }) => gapOf[i] < 14).sort((x, y) => x.a.left - y.a.left);
  const up = new Set(order.filter((_, k) => k % 2 === 1).map(({ i }) => i));
  return (
    <div className="pitch2">
      <svg viewBox="0 0 100 108" className="pitch2-bg" preserveAspectRatio="none">
        <rect x="0" y="0" width="100" height="108" fill="#0f3020" />
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <rect key={i} x="0" y={i * 18} width="100" height="9" fill={i % 2 ? "rgba(255,255,255,0.02)" : "transparent"} />
        ))}
        <g stroke="rgba(255,255,255,0.16)" strokeWidth="0.4" fill="none">
          <rect x="4" y="4" width="92" height="100" />
          <line x1="4" y1="54" x2="96" y2="54" />
          <circle cx="50" cy="54" r="9" />
          <rect x="28" y="4" width="44" height="14" />
          <rect x="28" y="90" width="44" height="14" />
          <rect x="40" y="4" width="20" height="6" />
          <rect x="40" y="98" width="20" height="6" />
        </g>
      </svg>
      {placements.map((p, i) => {
        const c = KIND_COLOR[p.kind] || "#888";
        const { left, top } = pos[i];               // viewBox 100×108 → % (줄 넓히기·골키퍼 내리기 반영)
        const real = p.player && p.player !== "—" && p.player !== "영입 필요";
        return (
          <div className={`ptok${real ? " clickable" : ""}${up.has(i) ? " up" : ""}`} key={i} style={{ left: `${left}%`, top: `${top}%` }}
            title={real ? `${p.player}${p.club ? ` · ${p.club}` : ""}${p.ovr != null ? ` · ${metric} ${p.ovr}` : ""}` : undefined}
            onClick={real ? (e) => peek(e, { name: p.player, club: p.club ?? team, hint: { photo: p.photo, ovr: metric === "OVR" ? p.ovr ?? undefined : undefined } }) : undefined}>
            <div className="ptok-face" style={{ borderColor: p.in ? "#5fd08c" : c }}>
              {p.photo
                ? <img src={p.photo} alt="" />
                : <span className="ptok-init" style={{ background: `linear-gradient(135deg, ${c}44, #10151e)`, color: "#eef2f8" }}>{initials(p.player)}</span>}
              {p.ovr != null && <span className="ptok-ovr" style={{ background: c }}>{p.ovr}</span>}
              {p.in && <span className="ptok-in">IN</span>}
            </div>
            <div className="ptok-name" style={{ maxWidth: `min(82px, calc(${(gapOf[i] * (gapOf[i] < 14 ? 2 : 1)).toFixed(1)}cqw - 4px))` }}>
              <span className="ptok-nm">{lastName(p.player)}</span>{p.injured && (p.absence === "suspension" ? <SusCard /> : <span className="ptok-inj" title="지금 부상 결장">✚</span>)}{showOut && p.out && <span className="ptok-out">↔ {lastName(p.out)}</span>}</div>
          </div>
        );
      })}
    </div>
  );
}
