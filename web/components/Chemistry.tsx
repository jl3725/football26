"use client";
import { useEffect, useState } from "react";
import { getChemistry, type ChemistryData, type ChemCard } from "@/lib/api";
import { hexA } from "@/lib/ui";
import { usePeek } from "./PlayerPeek";
import { SkelCards } from "./Skeleton";

const LINE_COLOR: Record<string, string> = { GK: "#f4cf5e", DEF: "#6aa6e0", MID: "#4fc27f", ATT: "#e0707a" };
const last = (n: string) => n.split(" ").slice(-1)[0];

function Face({ c, size = 42, team }: { c: ChemCard; size?: number; team?: string }) {
  const b = LINE_COLOR[c.line] || "#8a94a8";
  const peek = usePeek();
  const onClick = team
    ? (e: React.MouseEvent) => { e.stopPropagation(); peek(e, { name: c.name, club: team, hint: { photo: c.photo, pos: c.pos } }); }
    : undefined;
  return c.photo
    ? <img src={c.photo} alt="" title={c.name} onClick={onClick}
        style={{ width: size, height: size, borderRadius: "50%", objectFit: "cover", border: `2px solid ${hexA(b, 0.7)}`, cursor: team ? "pointer" : undefined }} />
    : <span title={c.name} onClick={onClick}
        style={{ width: size, height: size, borderRadius: "50%", background: hexA(b, 0.18), display: "inline-block", cursor: team ? "pointer" : undefined }} />;
}

export default function Chemistry({ team, accent }: { team: string; accent: string }) {
  const [d, setD] = useState<ChemistryData | null>(null);
  useEffect(() => {
    let a = true; setD(null);
    getChemistry(team).then((x) => a && setD(x)).catch(() => a && setD(null));
    return () => { a = false; };
  }, [team]);
  if (!d) return <SkelCards n={6} />;
  if (!d.available || !d.duos.length) return <div className="mgr-meta">케미스트리 데이터 없음 (KG 미가동 리그)</div>;

  return (
    <div>
      <div style={{ fontSize: 11, opacity: 0.5, marginBottom: 9 }}>함께 뛴 경기(TEAMMATE_OF) 기반 — 손발 맞는 조합</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 10 }}>
        {d.duos.map((duo, i) => (
          <div key={i} style={{ background: hexA("#ffffff", 0.03), border: `1px solid ${hexA("#ffffff", 0.08)}`, borderRadius: 12, padding: "11px 13px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Face c={duo.a} team={team} />
              <span style={{ opacity: 0.4, fontSize: 14 }}>⟷</span>
              <Face c={duo.b} team={team} />
              <div style={{ marginLeft: "auto", textAlign: "right" }}>
                <div style={{ fontSize: 21, fontWeight: 800, color: accent, lineHeight: 1 }}>{duo.chem}</div>
                <div style={{ fontSize: 9, opacity: 0.5, letterSpacing: 1 }}>CHEM</div>
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, fontWeight: 600, marginTop: 8 }}>
              <span>{last(duo.a.name)}</span>
              <span style={{ opacity: 0.45, fontWeight: 400, fontSize: 10.5 }}>{duo.matches}경기</span>
              <span>{last(duo.b.name)}</span>
            </div>
            <div style={{ height: 4, borderRadius: 2, background: hexA("#ffffff", 0.08), marginTop: 6 }}>
              <div style={{ width: `${duo.chem}%`, height: "100%", borderRadius: 2, background: accent }} />
            </div>
          </div>
        ))}
      </div>

      {d.trios.length > 0 && (
        <>
          <div style={{ fontSize: 11, opacity: 0.5, margin: "16px 0 9px" }}>삼각편대 — 셋이 함께 뛴 조합</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))", gap: 10 }}>
            {d.trios.map((tr, i) => (
              <div key={i} style={{ background: hexA("#ffffff", 0.03), border: `1px solid ${hexA("#ffffff", 0.08)}`, borderRadius: 12, padding: "11px 13px", display: "flex", alignItems: "center", gap: 11 }}>
                <div style={{ display: "flex" }}>
                  {tr.players.map((p, j) => <span key={j} style={{ marginLeft: j ? -12 : 0 }}><Face c={p} size={34} team={team} /></span>)}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{tr.players.map((p) => last(p.name)).join(" · ")}</div>
                  <div style={{ fontSize: 10, opacity: 0.5, marginTop: 2 }}>합산 {tr.score}경기</div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
