"use client";
import { useEffect, useState } from "react";
import { getSquad, fmtEur, type Squad, type SquadPlayer, type DepthOption } from "@/lib/api";
import { tier, hexA, ageText } from "@/lib/ui";
import { depthMeaning } from "@/lib/meaning";
import { MeaningTag } from "./Meaning";
import SquadBuilder from "./SquadBuilder";
import SectionHead from "./SectionHead";
import { usePeek } from "./PlayerPeek";
import { SkelCards } from "./Skeleton";
import { TrendArrow } from "./Trend";

const LINES: { key: string; label: string }[] = [
  { key: "GK", label: "골키퍼" }, { key: "DEF", label: "수비" },
  { key: "MID", label: "미드필드" }, { key: "ATT", label: "공격" },
];
const POS_LABEL: Record<string, string> = {
  GK: "골키퍼", CB: "센터백", RB: "라이트백", LB: "레프트백", DM: "수비형MF",
  CM: "중앙MF", AM: "공격형MF", RW: "우측WG", LW: "좌측WG", W: "윙어", ST: "스트라이커",
};

function Row({ p, team }: { p: SquadPlayer; team: string }) {
  const t = tier(p.ovr);
  const peek = usePeek();
  return (
    <div className={`sq-row peekable${p.roster_only ? " dnp" : ""}`}
      onClick={(e) => peek(e, { name: p.player, club: team, hint: { photo: p.photo, ovr: p.ovr, pos: p.pos, age: p.age, value_eur: p.value_eur } })}>
      <span className="sq-ovr" style={{ color: t.light, borderColor: t.deep }}>{p.ovr}</span>
      <span className="sq-trend"><TrendArrow t={p.trend} ovr={p.ovr} /></span>
      {p.photo ? <img className="sq-photo" src={p.photo} alt="" /> : <span className="sq-photo ph" />}
      <div className="sq-info">
        <div className="sq-name">{p.player}</div>
        <div className="sq-meta">{p.pos} · {ageText(p.age)} · {p.roster_only
          ? <span className="sq-dnp" title="이번 시즌 출전 기록 없음 — OVR·가치는 지난 시즌 기준">출전 없음</span>
          : <>{p.minutes.toLocaleString()}′</>}</div>
      </div>
      <span className="sq-val">{fmtEur(p.value_eur)}</span>
    </div>
  );
}

export default function SquadTab({ team, accent }: { team: string; accent: string }) {
  const [data, setData] = useState<Squad | null>(null);
  const [view, setView] = useState<"squad" | "builder">("squad");
  const [allLoans, setAllLoans] = useState(false);
  useEffect(() => { let a = true; getSquad(team).then((d) => a && setData(d)).catch(() => {}); return () => { a = false; }; }, [team]);
  const peek = usePeek();
  if (!data) return <div className="skel-wrap"><SkelCards n={8} cols="repeat(auto-fill, minmax(280px, 1fr))" /></div>;

  const toggle = (
    <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
      <div style={{ display: "inline-flex", gap: 2, padding: 3, borderRadius: 9, background: hexA("#ffffff", 0.05) }}>
        {([["squad", "스쿼드"], ["builder", "Best XI 빌더"]] as const).map(([v, l]) => (
          <button key={v} onClick={() => setView(v)}
            style={{ padding: "6px 13px", borderRadius: 6, fontSize: 12, fontWeight: 700, cursor: "pointer", border: "none",
              background: view === v ? accent : "transparent", color: view === v ? "#0a0a0a" : "inherit", opacity: view === v ? 1 : 0.6 }}>{l}</button>
        ))}
      </div>
    </div>
  );

  if (view === "builder") {
    return (
      <div className="fade">
        {toggle}
        <div className="card">
          <SectionHead title="BEST XI BUILDER" kr="베스트 XI 빌더" meta="칸을 눌러 교체"
            info={<>
              <p>칸마다 &lsquo;선수 OVR × 그 자리 포지션 적합도&rsquo;의 합이 가장 큰 배치를 자동으로 고릅니다.</p>
              <p>칸을 누르면 그 자리에 맞는 순으로 교체 후보가 나옵니다.</p>
            </>} />
          <SquadBuilder team={team} accent={accent} />
        </div>
      </div>
    );
  }

  return (
    <div className="fade">
      {toggle}
      {/* 포지션별 뎁스 차트 — 역할마다 1st·2nd·3rd 옵션, 멀티 포지션(2·3포지션) 선수 포함 */}
      <div className="card">
        <SectionHead title="DEPTH CHART" kr="포지션별 뎁스"
          info={<>
            <p><b>뎁스</b> = 2·3번째 옵션의 OVR + 인원으로 매긴 점수(색 = 아래 범례).</p>
            <p>포지션 = 실제로 선 자리 기준. <b>멀티</b> = 그 선수의 2·3번째 포지션. <b>✚</b> = 부상.</p>
          </>} />
        <div className="mn-legend" style={{ marginTop: 0, marginBottom: 10 }}>
          <b>뎁스</b>
          {([[75, "탄탄 75+"], [65, "양호 65+"], [55, "보통 55+"], [45, "얇음 45+"], [0, "매우 얇음 45↓"]] as const).map(([v, l]) => (
            <span key={l}><i style={{ background: depthMeaning(v).c }} />{l}</span>
          ))}
        </div>
        <div className="depth-head dp5">
          <span>POS</span><span>1ST</span><span>2ND · 3RD · 그 외</span><span>뎁스</span>
        </div>
        {data.buckets.map((b) => {
          const dm = depthMeaning(b.depth);
          const chip = (o: DepthOption, rank: number) => (
            <span key={o.player} className={`dp5-chip peekable${o.kind === "secondary" ? " multi" : ""}${o.injured ? " inj" : ""}${rank === 1 ? " r2" : rank === 2 ? " r3" : ""}`}
              onClick={(e) => peek(e, { name: o.player, club: team, hint: { photo: o.photo, ovr: o.ovr, age: o.age } })}
              title={o.kind === "secondary" ? `${o.player} — 주포지션 ${o.primary}, ${b.pos} 멀티` : o.player}>
              {rank <= 2 && <i className="dp5-n">{rank === 1 ? "2nd" : "3rd"}</i>}
              <b style={{ color: tier(o.ovr).light }}>{o.ovr}</b> {o.player.split(" ").slice(-1)[0]}
              {o.kind === "secondary" && <em className="dp5-m">멀티·{o.primary}</em>}
              {o.injured && <em className="dp5-inj">✚</em>}
            </span>
          );
          return (
            <div className="depth-row dp5" key={b.pos}>
              <span className="depth-pos">{POS_LABEL[b.pos] || b.pos}</span>
              <span className={`depth-starter peekable${b.starter.injured ? " inj" : ""}`}
                onClick={(e) => peek(e, { name: b.starter.player, club: team, hint: { photo: b.starter.photo, ovr: b.starter.ovr, age: b.starter.age } })}>
                <b style={{ color: tier(b.starter.ovr).light }}>{b.starter.ovr}</b> {b.starter.player.split(" ").slice(-1)[0]}
                {b.starter.kind === "secondary" && <em className="dp5-m">멀티·{b.starter.primary}</em>}
                {b.starter.injured && <em className="dp5-inj">✚</em>}
              </span>
              <span className="depth-rot">
                {b.rotation.length === 0 ? <em>백업 없음</em> : b.rotation.map((r, i) => chip(r, i + 1))}
              </span>
              <span className="depth-score" title={`뎁스 ${b.depth} · ${dm.label} — 2·3번째 옵션의 OVR + 인원`}>
                <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                  <div className="depth-bar" style={{ flex: "none" }}><span style={{ width: `${b.depth}%`, background: dm.bar }} /></div>
                  <span style={{ alignSelf: "flex-start" }}><MeaningTag sm m={dm} /></span>
                </span>
                <b style={{ color: dm.c }}>{b.depth}</b>
              </span>
            </div>
          );
        })}
      </div>

      {/* 라인별 스쿼드 */}
      <div className="squad-grid" style={{ marginTop: 16 }}>
        {LINES.map((ln) => {
          const players = data.lines[ln.key] || [];
          return (
            <div className="card" key={ln.key}>
              <h3>{ln.label} · {players.length}</h3>
              <div className="sq-list">
                {players.map((p, i) => <Row key={i} p={p} team={team} />)}
                {players.length === 0 && <div className="mgr-meta">선수 없음</div>}
              </div>
            </div>
          );
        })}
      </div>

      {/* 임대 보낸 선수 — 계약은 우리, 지금은 다른 팀(스쿼드·XI·팀 OVR 에서 뺀다) */}
      {(data.loans?.length ?? 0) > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <SectionHead title="OUT ON LOAN" kr="임대 보낸 선수" meta={`${data.loans!.length}명`}
            info={<>
              <p>계약은 우리 팀, 지금은 다른 팀에서 뛰는 선수 — 스쿼드·XI·팀 OVR 에서 뺍니다.</p>
              <p className="muted">행선지 기록(출전 분·OVR)은 우리가 다루는 리그 안에서만 보입니다.</p>
            </>} />
          <div className="loan-grid">
            {data.loans!.slice(0, allLoans ? undefined : 8).map((l) => (
              <div key={l.player} className="loan-card peekable"
                onClick={(e) => peek(e, { name: l.player, club: l.club || team, hint: { photo: l.photo, ovr: l.ovr ?? undefined, pos: l.pos } })}>
                {l.photo ? <img className="sq-photo" src={l.photo} alt="" />
                  : <span className="sq-photo ph loan-ini">{l.player.split(" ").map((w) => w[0]).slice(0, 2).join("")}</span>}
                <div className="sq-info">
                  <div className="sq-name">{l.player}</div>
                  <div className="sq-meta">
                    <span className="loan-badge">임대중</span>
                    {l.club ? <> → <b>{l.club}</b></> : <em> 행선지 미상</em>}
                    {l.minutes != null && <> · {l.minutes.toLocaleString()}′</>}
                  </div>
                </div>
                {l.ovr != null && <span className="sq-ovr" style={{ color: tier(l.ovr).light, borderColor: tier(l.ovr).deep }}>{l.ovr}</span>}
              </div>
            ))}
          </div>
          {data.loans!.length > 8 && (
            <button className="loan-more" onClick={() => setAllLoans((x) => !x)}>
              {allLoans ? "접기" : `+${data.loans!.length - 8}명 더 보기`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
