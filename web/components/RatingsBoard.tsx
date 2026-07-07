"use client";
import { useState } from "react";
import type { Overview } from "@/lib/api";
import { hexA } from "@/lib/ui";
import SquadGraph from "./SquadGraph";
import AgeStructure from "./AgeStructure";

export default function RatingsBoard({ ov, accent }: { ov: Overview; accent: string }) {
  const [view, setView] = useState<"network" | "age">("network");
  const sr = ov.squad_ratings || [];
  if (sr.length === 0) return null;

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <h3 style={{ margin: 0 }}>스쿼드 {view === "network" ? "네트워크" : "연령 구조"}
          <span className="rating-note">· {view === "network" ? "함께 뛴 조합" : "라인별 나이 분포"}</span></h3>
        <div style={{ display: "inline-flex", gap: 2, padding: 3, borderRadius: 9, background: hexA("#ffffff", 0.05), border: `1px solid ${hexA(accent, 0.15)}` }}>
          {([["network", "네트워크"], ["age", "연령"]] as const).map(([v, l]) => (
            <button key={v} onClick={() => setView(v)} style={{ padding: "5px 12px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer", border: "none", background: view === v ? accent : "transparent", color: view === v ? "#0a0a0a" : "inherit", opacity: view === v ? 1 : 0.6 }}>{l}</button>
          ))}
        </div>
      </div>
      {view === "network" ? <SquadGraph team={ov.team} accent={accent} /> : <AgeStructure ov={ov} accent={accent} />}
    </div>
  );
}
