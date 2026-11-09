"use client";
import { useEffect, useState } from "react";
import { getInfluence, activeLeague, foldName, type InfluenceData } from "@/lib/api";
import { influenceMeaning } from "@/lib/meaning";
import { MeaningTag } from "./Meaning";
import { Skel } from "./Skeleton";
import Info from "./Info";

// INFLUENCE — 팀 안 영향력(NETWORK LEADERSHIP 과 같은 값). 2026-11-09 사용자 '팀 결속력·리더십·베테랑도 축구의 일부'
// → OVR·승부 예측엔 넣지 않고(백테스트에서 예측력 없음) 팀 안 역할 정보로만. NETWORK 계산이 무거워 선수 화면과 따로 늦게 받는다.
const COMP_KO: Record<string, string> = { quality: "실력", minutes: "출전", armband: "완장", play: "볼 관여", hub: "연결",
  form: "폼", tenure: "근속", experience: "경험", international: "대표팀" };

export default function PlayerInfluence({ team, player, accent }: { team: string; player: string; accent: string }) {
  const [d, setD] = useState<InfluenceData | null>(null);
  const league = activeLeague();          // 선수 화면(getPlayerDetail)과 같은 리그
  useEffect(() => {
    // 서버가 막 떠 NETWORK 를 처음 계산하면 요청 제한(70초)을 넘길 때가 있다 — 서버는 계속 계산해 캐시하므로 20초 뒤 두 번 더 받는다
    let a = true, timer: ReturnType<typeof setTimeout> | undefined; setD(null);
    const load = (left: number) => getInfluence(team, league).then((x) => a && setD(x)).catch(() => {
      if (!a) return;
      if (left > 0) timer = setTimeout(() => load(left - 1), 20_000);
      else setD({ available: false });
    });
    load(2);
    return () => { a = false; if (timer) clearTimeout(timer); };
  }, [team, league]);
  if (d === null) return <div className="pd-inf"><Skel w="60%" h={14} /><Skel w="100%" h={30} style={{ marginTop: 8 }} /></div>;
  const ps = d.players ?? {};
  const key = ps[player] ? player : Object.keys(ps).find((k) => foldName(k) === foldName(player));
  const p = key ? ps[key] : undefined;
  if (!d.available || !p || !d.n) return null;
  const mean = influenceMeaning(p.rank, d.n);
  const why = p.why.filter((x) => x !== p.role_ko);     // 완장 칩(C · 주장)과 겹치는 근거는 빼고
  const w = Object.entries(d.weights ?? {}).sort((x, y) => y[1] - x[1]).map(([k, v]) => `${COMP_KO[k] ?? k} ${v}`).join(" · ");
  return (
    <div className="pd-inf">
      <div className="pd-inf-head">
        <b>INFLUENCE</b><span>팀 내 영향력</span>
        <Info wide label="영향력 기준">
          <p><b>영향력 0~100</b> — 팀 안 상대값. NETWORK 탭 LEADERSHIP 과 같은 값</p>
          <p>가중치 — {w}</p>
          <p className="muted">OVR·승부 예측엔 미반영 — 26/27 검증에서 주장 결장·선발 연속성·베테랑 수가 Elo + 선발 전력 위에 예측을 더 낫게 하지 못한 결과(로그 손실 개선 0.001 이하)</p>
        </Info>
      </div>
      <div className="pd-inf-row">
        <div className="pd-inf-num" style={{ color: mean.c }}>{p.influence}<i>/100</i></div>
        <div className="pd-inf-side">
          <div className="pd-inf-rank">
            <MeaningTag m={mean} sm />
            <span>팀 {p.rank}위 · {d.n}명 중</span>
            {p.role && <span className="pd-inf-cap" title={p.role_ko ?? undefined}>{p.role} · {p.role_ko}</span>}
          </div>
          <div className="pd-inf-bar"><i style={{ width: `${Math.max(2, Math.min(100, p.influence))}%`, background: accent }} /></div>
          {why.length > 0 && <div className="pd-inf-why">{why.map((x) => <span key={x}>{x}</span>)}</div>}
        </div>
      </div>
    </div>
  );
}
