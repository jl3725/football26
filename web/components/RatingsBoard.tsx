"use client";
import type { Overview } from "@/lib/api";
import AgeStructure from "./AgeStructure";
import SectionHead from "./SectionHead";

// 스쿼드 연령 구조 — 함께 뛴 관계망(예전 '네트워크' 토글)은 NETWORK 탭 CHEMISTRY 렌즈로 옮겼다(중복 금지).
export default function RatingsBoard({ ov, accent }: { ov: Overview; accent: string }) {
  if ((ov.squad_ratings || []).length === 0) return null;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <SectionHead title="AGE PROFILE" kr="연령 구조" meta="출전 가중 · 라인별 분포" />
      <AgeStructure ov={ov} accent={accent} />
    </div>
  );
}
