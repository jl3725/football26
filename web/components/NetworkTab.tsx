"use client";
import { useEffect, useState } from "react";
import { getNetwork, type NetInsight, type NetworkData } from "@/lib/api";
import { initials } from "./NetShared";
import SectionHead from "./SectionHead";
import EmptyState from "./EmptyState";
import { Skel } from "./Skeleton";
import NetLeadership from "./NetLeadership";
import NetChemistry from "./NetChemistry";
import NetOrigins from "./NetOrigins";
import NetNations from "./NetNations";
import NetLinks from "./NetLinks";
import NetTies from "./NetTies";
import NetManager from "./NetManager";
import NetRumors from "./NetRumors";

// NETWORK 탭 — 팀 지식그래프(/api/network). 선수·클럽·국가·이적·출전 관계를 다섯 렌즈로 보고,
// 맨 위 GRAPH INSIGHTS 는 그래프 경로를 근거로 붙인 자동 요약(카드를 누르면 그 렌즈로).
// 예전엔 Overview '더 보기' 안의 네트워크 하나뿐이었다(2026-10-15 사용자 요청: 그래프 활용·주장단 강조).
const LENSES = [
  { k: "leadership", en: "LEADERSHIP", ko: "주장단·영향력" },
  { k: "chemistry", en: "CHEMISTRY", ko: "함께 뛴 관계망" },
  { k: "origins", en: "ORIGINS", ko: "스쿼드 구성" },
  { k: "nations", en: "NATIONS", ko: "국적·대표팀 동료" },
  { k: "ties", en: "TIES", ko: "전 소속 동료" },
  { k: "links", en: "LINKS", ko: "클럽 관계망" },
  { k: "rumors", en: "RUMOURS", ko: "이적설 지도" },
  { k: "manager", en: "MANAGER", ko: "감독 커리어" },
] as const;
type Lens = (typeof LENSES)[number]["k"];
const LENS_EN: Record<string, string> = Object.fromEntries(LENSES.map((l) => [l.k, l.en]));

// 인사이트 타일 — 큰 숫자 + 얼굴(선수 사진)·로고·국기 + 한 줄. 근거 경로는 접어 둔다.
// 예전엔 문장·근거 코드가 카드마다 4~6줄이라 한눈에 안 들어왔다(2026-10-15 사용자 지적).
function InsightTile({ i, d, on, onPick }: { i: NetInsight; d: NetworkData; on: boolean; onPick: () => void }) {
  const [ev, setEv] = useState(false);
  const photo = (n: string) => d.players.find((p) => p.name === n)?.photo || "";
  const logo = (c?: string) => !c ? "" : c === d.team ? d.logo
    : d.links.clubs.find((x) => x.club === c)?.logo || d.ties.clubs.find((x) => x.club === c)?.logo || "";
  const flag = (n?: string) => (n ? d.nations.countries.find((x) => x.name === n)?.flag || "" : "");
  const who = (i.who ?? []).slice(0, 4);
  const lg = logo(i.club), fl = flag(i.flag);
  return (
    <div role="button" tabIndex={0} className={`net-in nt tone-${i.tone}${on ? " on" : ""}`} onClick={onPick}
      onKeyDown={(e) => { if (e.key === "Enter") onPick(); }} title={i.text}>
      <span className="net-in-top"><span className="net-in-ic">{i.icon}</span><em>{LENS_EN[i.lens] ?? i.lens.toUpperCase()}</em><b>{i.title}</b></span>
      <div className="nt-main">
        {(who.length > 0 || fl || lg) && (
          <span className="nt-vis">
            {fl && <img className="nt-flag" src={fl} alt="" />}
            {who.map((n) => (photo(n)
              ? <img key={n} className="nt-face" src={photo(n)} alt="" title={n} />
              : <span key={n} className="nt-face nt-ini" title={n}>{initials(n)}</span>))}
            {lg && <img className="nt-logo" src={lg} alt="" title={i.club} />}
          </span>
        )}
        {i.big != null && <span className="nt-num"><strong>{i.big}</strong><em>{i.unit}</em></span>}
      </div>
      <p className="nt-line">{i.line ?? i.text}</p>
      {i.evidence.length > 0 && (
        <button type="button" className="nt-ev-t" onClick={(e) => { e.stopPropagation(); setEv((v) => !v); }} aria-expanded={ev}>
          근거 경로 {i.evidence.length} {ev ? "▴" : "▾"}
        </button>
      )}
      {ev && <span className="net-ev">{i.evidence.slice(0, 3).map((e, j) => <code key={j}>{e}</code>)}</span>}
    </div>
  );
}

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
        <h4 className="net-h">GRAPH INSIGHTS <span>그래프 자동 요약 · 누르면 해당 렌즈로</span></h4>
        <div className="net-ins">
          {d.insights.map((i, k) => (
            <InsightTile key={k} i={i} d={d} on={lens === i.lens} onPick={() => setLens(i.lens as Lens)} />
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
        {lens === "ties" && <NetTies d={d} accent={accent} />}
        {lens === "links" && <NetLinks d={d} accent={accent} />}
        {lens === "manager" && <NetManager d={d} accent={accent} />}
        {lens === "rumors" && <NetRumors team={team} accent={accent} logo={d.logo} />}
      </div>
      <p className="net-src">
        관계 원천 — 함께 뛴 시간: ESPN 라인업·교체(이번·지난 시즌) · 주장단·등번호·감독 경력: Wikipedia ·
        입단·이적: Transfermarkt · 국적·순위: FIFA 랭킹 · 대표팀: 2026 월드컵 명단 · 이적설: Transfermarkt 루머 + 뉴스 루머(매체 적중률 가중).
        같은 관계를 지식그래프(Neo4j)로도 적재한다.
      </p>
    </div>
  );
}
