"use client";
import { useEffect, useState } from "react";
import SectionHead from "./SectionHead";
import { getTeamFixtures, type Fixture } from "@/lib/api";
import MatchCard from "./MatchCard";
import { useOpenTeam } from "./PlayerPeek";

// 팀 Overview '다음 경기' — 전 대회 다음 3경기(큰 카드 1 + 작은 카드 2). 일정은 매일 자동 갱신.
export default function NextMatch({ team }: { team: string }) {
  const [ms, setMs] = useState<Fixture[] | null>(null);
  const openTeam = useOpenTeam();
  useEffect(() => {
    let a = true; setMs(null);
    getTeamFixtures(team).then((d) => a && setMs(d.next)).catch(() => a && setMs([]));
    return () => { a = false; };
  }, [team]);
  if (!ms || ms.length === 0) return null;
  const go = (t: string, lg?: string | null) => { if (t !== team && lg && openTeam) openTeam(t, lg); };
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <SectionHead title="NEXT MATCHES" kr="다음 경기" meta="전 대회 · 누르면 프리뷰" />
      <div className="next-match">
        <MatchCard m={ms[0]} onPick={go} />
        {ms.length > 1 && <div className="next-rest">{ms.slice(1).map((m, i) => <MatchCard key={i} m={m} onPick={go} compact />)}</div>}
      </div>
    </div>
  );
}
