"use client";
import { useEffect, useMemo, useState } from "react";
import { getDiscover, fmtEur, type Discover, type DiscoverPick } from "@/lib/api";
import { hexA, tier } from "@/lib/ui";
import { scoreMeaning, ssMeaning, SS_NOTE } from "@/lib/meaning";
import { MeaningTag } from "./Meaning";
import { usePeek } from "./PlayerPeek";
import { SkelCards } from "./Skeleton";
import EmptyState from "./EmptyState";

const POS_BTNS: [string, string][] = [
  ["", "전체"], ["Centre-Back", "CB"], ["Left-Back", "LB"], ["Right-Back", "RB"],
  ["Defensive Midfield", "DM"], ["Central Midfield", "CM"], ["Attacking Midfield", "AM"],
  ["Left Winger", "LW"], ["Right Winger", "RW"], ["Centre-Forward", "CF"],
];
const LEAGUES: [string, string][] = [
  ["EPL", "Premier League"], ["LaLiga", "La Liga"], ["SerieA", "Serie A"], ["Bundesliga", "Bundesliga"],
  ["Ligue1", "Ligue 1"], ["LigaPortugal", "Liga Portugal"], ["Eredivisie", "Eredivisie"],
  ["BelgianProLeague", "Belgian Pro League"],
];
const SORTS: [string, string][] = [["fit", "추천순(니즈·정책)"], ["style", "유사도"], ["ovr", "예상 OVR"], ["value", "시장가"], ["age", "나이"]];

function Kpi({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent: string }) {
  return (
    <div className="card" style={{ padding: "12px 14px" }}>
      <div style={{ fontSize: 10.5, opacity: 0.55, textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 21, fontWeight: 800, marginTop: 2, color: accent }}>{value}</div>
      {sub && <div style={{ fontSize: 10, opacity: 0.5 }}>{sub}</div>}
    </div>
  );
}

function Card({ p, accent }: { p: DiscoverPick; accent: string }) {
  const t = tier(p.ovr);
  const sf = scoreMeaning(p.style_fit);
  const rising = (p.age ?? 30) <= 21;
  const peek = usePeek();
  // ovr = 우리 리그 기준 예상 OVR(다른 리그 선수는 리그 수준 차이 보정) · current_ovr = 지금 뛰는 리그 기준
  const ovrTitle = p.cross_league
    ? `현재 OVR ${p.current_ovr} (${p.source_league} 기준) → 우리 리그 기준 예상 ${p.ovr} · ${t.ko}`
    : `OVR ${p.ovr} · ${t.ko}`;
  return (
    <div className="card hoverable" style={{ padding: 13, cursor: "pointer" }}
      onClick={(e) => peek(e, { name: p.player, club: p.squad, league: p.source_league, hint: { photo: p.photo, ovr: p.current_ovr ?? p.ovr, pos: p.pos, age: p.age ?? undefined, value_eur: p.value_eur ?? undefined } })}>
      <div style={{ display: "flex", gap: 11, alignItems: "flex-start" }}>
        {p.photo ? <img src={p.photo} alt="" style={{ width: 46, height: 46, borderRadius: "50%", objectFit: "cover", border: `1px solid ${hexA(accent, 0.3)}` }} />
          : <span style={{ width: 46, height: 46, borderRadius: "50%", background: hexA("#fff", 0.06), display: "inline-block" }} />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13.5, fontWeight: 700, display: "flex", alignItems: "center", gap: 5 }}>
            {p.player}
            {p.kg_rumored && <span title={`이 팀과 루머 연결${p.kg_rumor_prob ? ` ${p.kg_rumor_prob}%` : ""}`}
              style={{ fontSize: 9, fontWeight: 700, padding: "1px 5px", borderRadius: 5, background: hexA(accent, 0.2), color: accent }}>링크</span>}
          </div>
          <div style={{ fontSize: 10.5, opacity: 0.6, marginTop: 1 }}>{p.squad} · {p.source_league}</div>
          <span style={{ fontSize: 9.5, padding: "1px 6px", borderRadius: 6, background: hexA(accent, 0.14), color: accent, marginTop: 4, display: "inline-block" }}>{p.pos}</span>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }} title={ovrTitle}>
          <div style={{ fontSize: 22, fontWeight: 800, lineHeight: 1, color: t.light }}>{p.ovr}</div>
          <div style={{ fontSize: 9, opacity: 0.6, marginTop: 2 }}>{p.cross_league ? "우리 리그 예상 OVR" : "OVR"}</div>
          <div style={{ fontSize: 9.5, fontWeight: 700, color: t.light }}>{t.ko}</div>
          {p.cross_league && <div style={{ fontSize: 9, opacity: 0.5 }}>현재 {p.current_ovr}</div>}
        </div>
      </div>
      {/* 스탯 */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "4px 14px", marginTop: 10, fontSize: 11 }}>
        <span><b>{p.goals ?? 0}</b><span style={{ opacity: 0.5 }}> G</span></span>
        <span><b>{p.assists ?? 0}</b><span style={{ opacity: 0.5 }}> A</span></span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }} title={SS_NOTE}>
          <b style={p.rating ? { color: ssMeaning(p.rating).c } : undefined}>{p.rating || "-"}</b><span style={{ opacity: 0.5 }}>평점</span>
          {p.rating ? <MeaningTag sm m={ssMeaning(p.rating)} /> : null}
        </span>
        <span style={{ marginLeft: "auto", opacity: 0.7 }}>{p.age ?? "?"}세 · {fmtEur(p.value_eur || 0)}</span>
      </div>
      {/* 유사도 바 */}
      <div style={{ marginTop: 8 }} title={`우리 팀이 이 자리에 쓰는 플레이 스타일과의 유사도 ${p.style_fit} / 100 (${sf.label})`}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 9.5, marginBottom: 2 }}>
          <span style={{ opacity: 0.6 }}>스타일 유사도</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            <MeaningTag sm m={sf} /><b style={{ color: sf.c }}>{p.style_fit}</b>
          </span>
        </div>
        <div style={{ height: 4, borderRadius: 3, background: hexA("#fff", 0.08) }}>
          <span style={{ display: "block", height: "100%", borderRadius: 3, width: `${p.style_fit}%`, background: sf.bar }} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 5, marginTop: 8, flexWrap: "wrap" }}>
        {p.level && <span title="팀 OVR 대비 수준" style={{ fontSize: 9.5, padding: "1px 7px", borderRadius: 8, fontWeight: 700,
          background: hexA(p.level === "starter" ? "#4fc27f" : p.level === "rotation" ? "#5b8def" : p.level === "prospect" ? "#b98cd8" : "#8a94a8", 0.16),
          color: p.level === "starter" ? "#4fc27f" : p.level === "rotation" ? "#8fb0f5" : p.level === "prospect" ? "#c9a6e6" : "#9aa3b5" }}>
          {p.level === "starter" ? "주전급" : p.level === "rotation" ? "로테이션" : p.level === "prospect" ? "유망주" : "수준 아래"}</span>}
        <span style={{ fontSize: 9.5, padding: "1px 7px", borderRadius: 8, background: hexA(rising ? "#4fc27f" : "#8aa", 0.15), color: rising ? "#4fc27f" : "#9ab" }}>{rising ? "성장형" : "안정"}</span>
        {p.euro && <span style={{ fontSize: 9.5, padding: "1px 7px", borderRadius: 8, background: hexA("#f4cf5e", 0.15), color: "#f4cf5e" }}>유럽 검증</span>}
        {p.price_verdict === "over-budget" && <span style={{ fontSize: 9.5, padding: "1px 7px", borderRadius: 8, background: hexA("#e0556b", 0.15), color: "#e0707a" }}>예산 초과</span>}
        {p.price_verdict === "stretch" && <span style={{ fontSize: 9.5, padding: "1px 7px", borderRadius: 8, background: hexA("#e0a53a", 0.15), color: "#e0a53a" }}>가격 무리</span>}
        {p.kg_precedent ? <span style={{ fontSize: 9.5, padding: "1px 7px", borderRadius: 8, background: hexA(accent, 0.12), color: accent }}>선례 {p.kg_precedent}</span> : null}
        {p.policy_ok === true && <span title="구단 이적 정책(최근 두 시즌 영입 나이·이적료)에 맞음" style={{ fontSize: 9.5, padding: "1px 7px", borderRadius: 8, background: hexA("#4fc27f", 0.13), color: "#4fc27f" }}>정책 부합</span>}
        {p.policy_ok === false && <span title={(p.policy_notes || []).join(" · ")} style={{ fontSize: 9.5, padding: "1px 7px", borderRadius: 8, background: hexA("#e0a53a", 0.13), color: "#e0a53a" }}>정책 밖</span>}
        {p.realistic === false && <span title="경쟁 팀(같은 리그)·강팀의 핵심 주전 — 시즌 중·1월에 데려오기 어려움" style={{ fontSize: 9.5, padding: "1px 7px", borderRadius: 8, background: hexA("#e0556b", 0.13), color: "#e0707a" }}>가능성 낮음</span>}
      </div>
    </div>
  );
}

const PAGE = 12;

export default function RecruitPool({ team, accent, focusRole }: { team: string; accent: string; focusRole?: string }) {
  const [disc, setDisc] = useState<Discover | null>(null);
  const [loading, setLoading] = useState(true);
  const [role, setRole] = useState("");
  // 니즈 피치에서 포지션을 누르면 풀이 그 포지션으로(예전엔 피치와 풀이 따로 놀았다, 2026-10-20 점검)
  useEffect(() => { if (focusRole !== undefined) setRole(focusRole); }, [focusRole]);
  const [lgs, setLgs] = useState<string[]>([]);     // 빈=전체
  const [ageMin, setAgeMin] = useState(16);
  const [ageMax, setAgeMax] = useState(34);
  const [valMax, setValMax] = useState(200);         // M€
  const [sortBy, setSortBy] = useState("fit");
  // 수준 — 팀 OVR 대비(서버 level). 기본은 '수준 아래' 제외(강팀에 60~70대가 깔리던 문제, 2026-10-19)
  const [lvl, setLvl] = useState<"squad" | "starter" | "prospect" | "all">("squad");
  const [railOpen, setRailOpen] = useState(false);   // 폰: 필터 접기(예전엔 sticky 필터가 카드 위에 겹쳤다)
  const [shown, setShown] = useState(PAGE);          // 한 번에 다 그리면 카드 35장·페이지 4,400px — 12장씩

  useEffect(() => {
    let a = true; setLoading(true); setDisc(null);
    // 예전엔 40명만 받아 필터 뒤 35명 남짓이었다(2026-10-19 사용자) — 포지션당 넉넉히 받아 화면에서 12장씩
    getDiscover(team, { role, top: 150 }).then((d) => a && setDisc(d)).catch(() => a && setDisc(null)).finally(() => a && setLoading(false));
    return () => { a = false; };
  }, [team, role]);

  const toggleLg = (k: string) => setLgs((s) => s.includes(k) ? s.filter((x) => x !== k) : [...s, k]);

  const picks = useMemo(() => {
    const all = disc?.recommendations || [];
    const lvOk = (p: DiscoverPick) => !p.level || lvl === "all" ? true
      : lvl === "starter" ? p.level === "starter" || p.level === "rotation"
      : lvl === "prospect" ? p.level === "prospect" : p.level !== "below";
    const f = all.filter((p) => lvOk(p) && (lgs.length === 0 || lgs.includes(p.source_league))
      && (p.age == null || (p.age >= ageMin && p.age <= ageMax))
      && (!p.value_eur || p.value_eur <= valMax * 1e6));
    const key = (p: DiscoverPick) => sortBy === "ovr" ? p.ovr : sortBy === "value" ? (p.value_eur || 0) : sortBy === "age" ? -(p.age || 99) : p.style_fit;
    // 추천순 = 서버 순서(니즈 시급도·스타일·전력·가격) 그대로, 영입 가능성 낮음·구단 정책 밖 후보는 뒤로
    const ok = (p: DiscoverPick) => (p.realistic === false ? 0 : 2) + (p.policy_ok === false ? 0 : 1);
    if (sortBy === "fit") return [...f].sort((a, b) => ok(b) - ok(a));
    return [...f].sort((a, b) => key(b) - key(a));
  }, [disc, lgs, ageMin, ageMax, valMax, sortBy, lvl]);
  useEffect(() => { setShown(PAGE); }, [team, role, lgs, ageMin, ageMax, valMax, sortBy, lvl]);

  const kAge = picks.filter((p) => p.age).map((p) => p.age as number);
  const kVal = picks.filter((p) => p.value_eur).map((p) => p.value_eur as number);
  const avgAge = kAge.length ? (kAge.reduce((s, x) => s + x, 0) / kAge.length).toFixed(1) : "-";
  const avgVal = kVal.length ? kVal.reduce((s, x) => s + x, 0) / kVal.length : 0;

  if (disc && !disc.available) return (
    <EmptyState title="스타일 유사 선수 추천 준비 중" note="벡터 검색 저장소가 연결되면 전 리그 후보를 추천합니다" />
  );

  const railLabel: React.CSSProperties = { fontSize: 10, fontWeight: 700, opacity: 0.5, textTransform: "uppercase", letterSpacing: 0.5, margin: "14px 0 7px" };

  return (
    <div style={{ marginTop: 16 }}>
      {/* KPI */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10, marginBottom: 14 }}>
        <Kpi label="후보" value={String(picks.length)} sub="필터 적용" accent={accent} />
        <Kpi label="평균 나이" value={`${avgAge}세`} accent={accent} />
        <Kpi label="평균 시장가" value={fmtEur(avgVal)} accent={accent} />
        <Kpi label="커버 리그" value={String(new Set(picks.map((p) => p.source_league)).size)} accent={accent} />
      </div>

      <div className="rp-layout">
        {/* 필터 레일 */}
        <div className={`card rp-rail${railOpen ? " open" : ""}`}>
          <button className="rp-rail-toggle" onClick={() => setRailOpen((v) => !v)} aria-expanded={railOpen}>
            필터 · {lvl === "squad" ? "주전급·로테이션·유망주" : lvl === "starter" ? "주전급·로테이션" : lvl === "prospect" ? "유망주" : "전체"}{role ? ` · ${role}` : ""} {railOpen ? "▴" : "▾"}
          </button>
          <div className="rp-rail-body">
          <div style={{ ...railLabel, marginTop: 0 }}>수준 <span style={{ textTransform: "none", fontWeight: 400 }}>· 팀 OVR {disc?.team_ovr ?? "?"} 대비</span></div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 5 }}>
            {([["squad", "쓸 만한 후보"], ["starter", "주전급·로테이션"], ["prospect", "유망주"], ["all", "전체"]] as const).map(([v, lbl]) => (
              <button key={v} onClick={() => setLvl(v)} title={v === "squad" ? "팀 OVR −9 이상 + 21세 이하 유망주" : v === "starter" ? "팀 OVR −9 이상" : v === "prospect" ? "21세 이하 · 팀 수준 아래" : "수준 무관"} style={{
                fontSize: 11, padding: "5px 0", borderRadius: 7, cursor: "pointer",
                border: `1px solid ${lvl === v ? accent : hexA(accent, 0.2)}`,
                background: lvl === v ? hexA(accent, 0.2) : "transparent", color: lvl === v ? accent : "inherit",
              }}>{lbl}</button>
            ))}
          </div>
          <div style={railLabel}>리그</div>
          {LEAGUES.map(([k, name]) => (
            <label key={k} style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, padding: "3px 0", cursor: "pointer", opacity: (lgs.length === 0 || lgs.includes(k)) ? 1 : 0.5 }}>
              <input type="checkbox" checked={lgs.length === 0 || lgs.includes(k)} onChange={() => toggleLg(k)} />
              {name}
            </label>
          ))}
          <div style={railLabel}>포지션</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 5 }}>
            {POS_BTNS.map(([v, lbl]) => (
              <button key={v} onClick={() => setRole(v)} style={{
                fontSize: 11, padding: "5px 0", borderRadius: 7, cursor: "pointer",
                border: `1px solid ${role === v ? accent : hexA(accent, 0.2)}`,
                background: role === v ? hexA(accent, 0.2) : "transparent", color: role === v ? accent : "inherit",
              }}>{lbl}</button>
            ))}
          </div>
          <div style={railLabel}>나이 {ageMin}–{ageMax}</div>
          <input type="range" min={16} max={34} value={ageMin} onChange={(e) => setAgeMin(Math.min(+e.target.value, ageMax))} style={{ width: "100%" }} />
          <input type="range" min={16} max={40} value={ageMax} onChange={(e) => setAgeMax(Math.max(+e.target.value, ageMin))} style={{ width: "100%" }} />
          <div style={railLabel}>시장가 ≤ €{valMax}M</div>
          <input type="range" min={5} max={200} step={5} value={valMax} onChange={(e) => setValMax(+e.target.value)} style={{ width: "100%" }} />
          </div>
        </div>

        {/* 그리드 */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <span style={{ fontSize: 12, opacity: 0.7 }}>
              {loading ? "—" : `${picks.length}명`}
              {!role && disc?.needs?.length ? <span style={{ opacity: 0.6 }} title="스카우트 데스크 포지션 니즈 상위(부상·폼·이적 공백)"> · 니즈 {disc.needs.map((n) => `${n.label}(${n.urgency})`).join(" · ")}</span>
                : disc?.target_roles && !role ? <span style={{ opacity: 0.6 }}> · 대상 {disc.target_roles.join("·")}</span> : null}
            </span>
            <label style={{ fontSize: 12, opacity: 0.7 }}>정렬{" "}
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} style={{ background: hexA("#fff", 0.06), border: `1px solid ${hexA(accent, 0.3)}`, color: "inherit", borderRadius: 6, padding: "3px 8px", fontSize: 12 }}>
                {SORTS.map(([v, l]) => <option key={v} value={v} style={{ color: "#111" }}>{l}</option>)}
              </select>
            </label>
          </div>
          {loading ? <SkelCards n={6} cols="repeat(auto-fill, minmax(280px, 1fr))" />
            : picks.length === 0 ? <div className="mgr-meta">조건에 맞는 후보 없음 — 필터를 넓혀보세요</div>
              : <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
                  {picks.slice(0, shown).map((p, i) => <Card key={i} p={p} accent={accent} />)}
                </div>
                {picks.length > shown && (
                  <button className="more-btn" onClick={() => setShown((v) => v + PAGE)}>
                    더 보기 · {Math.min(PAGE, picks.length - shown)}명 더 ({shown}/{picks.length})
                  </button>
                )}
              </>}
        </div>
      </div>
    </div>
  );
}
