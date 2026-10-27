"use client";
import { useEffect, useState } from "react";
import { getChemistry, type ChemistryData, type ChemCard } from "@/lib/api";
import { hexA } from "@/lib/ui";
import { usePeek } from "./PlayerPeek";
import { SkelCards } from "./Skeleton";
import EmptyState from "./EmptyState";
import Info from "./Info";
import { surname } from "@/lib/names";

const LINE_COLOR: Record<string, string> = { GK: "#f4cf5e", DEF: "#6aa6e0", MID: "#4fc27f", ATT: "#e0707a" };
const last = surname;
// 케미 숫자의 뜻(api/main.py chemistry) — 분 기준: 팀 시즌 전체 시간(경기 수 × 90분) 중 둘이 함께 뛴 비율(%)
// 경기 기준(관계 그래프): 함께 뛴 경기 수를 팀 안 최다 듀오 = 100 으로 둔 상대값
const CHEM_MIN_NOTE = "팀 시즌 전체 시간(경기 수 × 90분) 중 둘이 함께 그라운드에 있던 비율";
const CHEM_MATCH_NOTE = "CHEM 0~100 = 함께 뛴 경기 수, 팀 안에서 가장 많이 함께 뛴 듀오 = 100 인 상대값";

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
    getChemistry(team).then((x) => a && setD(x)).catch(() => a && setD({ available: false, reason: "응답 없음", duos: [], trios: [] } as ChemistryData));
    return () => { a = false; };
  }, [team]);
  if (!d) return <SkelCards n={6} />;
    if (!d.available || !d.duos.length) return <EmptyState title="케미스트리 준비 중" note="함께 뛴 기록(관계 그래프)이 연결되면 표시됩니다" />;

  const byMin = d.basis === "minutes";
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 9 }}>
        {byMin ? `시즌 ${d.games}경기 라인업 기준` : "함께 뛴 경기 기준"}
        <Info label="케미 기준">
          {byMin ? <>
            <p>실제로 함께 그라운드에 있던 시간 — 시즌 {d.games}경기 라인업·교체 기록 기준.</p>
            <p><b>% · 막대</b> = {CHEM_MIN_NOTE}</p>
          </> : <>
            <p>함께 뛴 경기(관계 그래프) 기준.</p>
            <p><b>CHEM</b> = {CHEM_MATCH_NOTE}</p>
          </>}
        </Info>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 10 }}>
        {d.duos.map((duo, i) => (
          <div key={i} style={{ background: hexA("#ffffff", 0.03), border: `1px solid ${hexA("#ffffff", 0.08)}`, borderRadius: 12, padding: "11px 13px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Face c={duo.a} team={team} />
              <span style={{ opacity: 0.4, fontSize: 14 }}>⟷</span>
              <Face c={duo.b} team={team} />
              <div style={{ marginLeft: "auto", textAlign: "right" }} title={byMin ? `함께 뛴 시간 ${duo.minutes}분 · ${CHEM_MIN_NOTE} ${duo.chem}%` : `CHEM ${duo.chem} — ${CHEM_MATCH_NOTE}`}>
                <div className="num" style={{ fontSize: 21, fontWeight: 800, color: accent, lineHeight: 1 }}>
                  {byMin ? <>{duo.minutes}<span style={{ fontSize: 12, opacity: 0.7 }}>′</span></> : duo.chem}
                </div>
                <div style={{ fontSize: 9, opacity: 0.5, letterSpacing: 1 }}>{byMin ? "함께 뛴 시간" : "CHEM"}</div>
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, fontWeight: 600, marginTop: 8 }}>
              <span>{last(duo.a.name)}</span>
              <span style={{ opacity: 0.45, fontWeight: 400, fontSize: 10.5 }} title={byMin ? `${CHEM_MIN_NOTE} ${duo.chem}%` : undefined}>
                {duo.matches}경기{byMin ? ` · 시즌의 ${duo.chem}%` : ""}
              </span>
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
                  <div style={{ fontSize: 10, opacity: 0.5, marginTop: 2 }}>
                    {tr.minutes != null ? `셋이 함께 ${tr.minutes}′ · ${tr.score}경기` : `합산 ${tr.score}경기`}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
