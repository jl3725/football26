"use client";
import { useEffect, useState } from "react";
import { getNetwork, type NetworkData } from "@/lib/api";
import SectionHead from "./SectionHead";
import EmptyState from "./EmptyState";
import { Skel } from "./Skeleton";
import NetLeadership from "./NetLeadership";
import NetChemistry from "./NetChemistry";
import NetOrigins from "./NetOrigins";
import NetNations from "./NetNations";
import NetLinks from "./NetLinks";

// NETWORK 탭 — 팀 지식그래프(/api/network). 선수·클럽·국가·이적·출전 관계를 다섯 렌즈로 보고,
// 맨 위 GRAPH INSIGHTS 는 그래프 경로를 근거로 붙인 자동 요약(카드를 누르면 그 렌즈로).
// 예전엔 Overview '더 보기' 안의 네트워크 하나뿐이었다(2026-10-15 사용자 요청: 그래프 활용·주장단 강조).
const LENSES = [
  { k: "leadership", en: "LEADERSHIP", ko: "주장단·영향력" },
  { k: "chemistry", en: "CHEMISTRY", ko: "함께 뛴 관계망" },
  { k: "origins", en: "ORIGINS", ko: "스쿼드 구성" },
  { k: "nations", en: "NATIONS", ko: "국적·대표팀" },
  { k: "links", en: "LINKS", ko: "클럽 관계망" },
] as const;
type Lens = (typeof LENSES)[number]["k"];
const LENS_EN: Record<string, string> = Object.fromEntries(LENSES.map((l) => [l.k, l.en]));

export default function NetworkTab({ team, accent }: { team: string; accent: string }) {
  const [d, setD] = useState<NetworkData | null>(null);
  const [err, setErr] = useState(false);
  const [lens, setLens] = useState<Lens>("leadership");
  useEffect(() => {
    let a = true;
    setD(null); setErr(false);
    getNetwork(team).then((x) => a && setD(x)).catch(() => a && setErr(true));
    return () => { a = false; };
  }, [team]);

  if (err) return <EmptyState title="관계 그래프를 불러오지 못했습니다" note="잠시 뒤 다시 열어 주세요" />;
  if (!d) return <div className="skel-wrap"><Skel h={150} r={14} /><div style={{ height: 14 }} /><Skel h={420} r={14} /></div>;
  if (!d.available) return <EmptyState title="관계 그래프 준비 중" note={d.reason || "선수 데이터가 쌓이면 표시됩니다"} />;

  const nRel = d.chemistry.edges.length + d.links.clubs.reduce((s, c) => s + c.in.length + c.out.length + c.alumni.length
    + c.rumor_in.length + c.rumor_out.length, 0) + d.players.filter((p) => p.nation).length;

  return (
    <div className="fade net" style={{ ["--ac" as string]: accent }}>
      <div className="card net-hero">
        <SectionHead title="NETWORK" kr="팀 지식그래프"
          meta={`선수 ${d.players.length} · 관계 ${nRel} · 클럽 ${d.links.n_clubs} · ${d.nations.n}개국 · ${d.games}경기`} />
        <h4 className="net-h">GRAPH INSIGHTS <span>관계 경로를 근거로 한 자동 요약 · 누르면 해당 렌즈로</span></h4>
        <div className="net-ins">
          {d.insights.map((i, k) => (
            <button key={k} className={`net-in tone-${i.tone}${lens === i.lens ? " on" : ""}`} onClick={() => setLens(i.lens as Lens)}>
              <span className="net-in-top"><span className="net-in-ic">{i.icon}</span><em>{LENS_EN[i.lens] ?? i.lens.toUpperCase()}</em></span>
              <b>{i.title}</b>
              <p>{i.text}</p>
              {i.evidence.length > 0 && <span className="net-ev">{i.evidence.slice(0, 3).map((e, j) => <code key={j}>{e}</code>)}</span>}
            </button>
          ))}
        </div>
      </div>

      <div className="net-tabs comp-seg chips5" role="tablist" aria-label="관계 그래프 렌즈">
        {LENSES.map((l) => (
          <button key={l.k} role="tab" aria-selected={lens === l.k} className={lens === l.k ? "active" : ""} onClick={() => setLens(l.k)}>
            {l.en}<em>{l.ko}</em>
          </button>
        ))}
      </div>

      <div className="card net-stage">
        {lens === "leadership" && <NetLeadership d={d} accent={accent} />}
        {lens === "chemistry" && <NetChemistry d={d} accent={accent} />}
        {lens === "origins" && <NetOrigins d={d} accent={accent} />}
        {lens === "nations" && <NetNations d={d} accent={accent} />}
        {lens === "links" && <NetLinks d={d} accent={accent} />}
      </div>
      <p className="net-src">
        관계 원천 — 함께 뛴 시간: ESPN 라인업·교체 · 주장단·등번호: Wikipedia 스쿼드 표 · 입단·이적: Transfermarkt ·
        국적·순위: FIFA 랭킹 · 2026 월드컵 명단 · 이적설: Transfermarkt 루머. 같은 관계를 지식그래프(Neo4j)로도 적재한다.
      </p>
    </div>
  );
}
