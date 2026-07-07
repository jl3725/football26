"use client";
import { useEffect, useState } from "react";
import { getHomeAll, fmtEur, type HomeAll } from "@/lib/api";
import { tier } from "@/lib/ui";

// 세련된 라인 화살표 (텍스트 → 대체)
function Arrow({ color = "currentColor" }: { color?: string }) {
  return (
    <svg className="hub-arw" width="18" height="9" viewBox="0 0 18 9" aria-hidden style={{ color }}>
      <path d="M0.8 4.5h14M11 1l4 3.5-4 3.5" stroke="currentColor" strokeWidth="1.3"
        fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// 전 리그 통합 대시보드 — 빅딜·이적속보·감독교체·순위 스냅샷을 한 화면에.
export default function AllDashboard({ accent, onPick }: { accent: string; onPick: (t: string, league?: string) => void }) {
  const [d, setD] = useState<HomeAll | null>(null);
  const [spot, setSpot] = useState("form");   // 선수 스포트라이트 세그먼트
  useEffect(() => { let a = true; getHomeAll().then((x) => a && setD(x)).catch(() => {}); return () => { a = false; }; }, []);
  if (!d) return <div className="loading">Loading all leagues…</div>;

  const tag = (name: string) => <span className="hub-lg">{name}</span>;
  const sec = (en: string, kr: string) => (
    <div className="hub-h"><span className="hub-h-bar" style={{ background: accent }} />
      <span className="hub-h-en">{en}</span><span className="hub-h-kr">{kr}</span></div>
  );

  return (
    <div className="fade home">
      <div className="hub-hero" style={{ ["--tc" as any]: accent }}>
        <div className="hub-hero-k">ALL LEAGUES · 2025/26</div>
        <h1 className="hub-hero-t">GLOBAL DASHBOARD</h1>
        <div className="hub-hero-m">{d.leagues.map((l) => l.name).join("  ·  ")}
          {d.window?.is_open && <span style={{ color: accent }}>  ·  {d.window.label} TRANSFER WINDOW OPEN</span>}</div>
      </div>

      {/* 리그 스냅샷 */}
      {sec("STANDINGS", "리그 순위")}
      <div className="hub-snaps">
        {d.snapshots.map((s) => (
          <div className="card hub-snap" key={s.league}>
            <div className="hub-snap-h" style={{ borderColor: s.color }}>{s.league_name}</div>
            {s.table.map((t) => (
              <button className="hub-snap-row" key={t.rank} onClick={() => onPick(t.team, s.league)}>
                <span className="hub-rk">{t.rank}</span>
                {t.logo && <img src={t.logo} alt="" />}
                <span className="hub-snap-team">{t.team}</span>
                <span className="hub-snap-pts">{t.points}</span>
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* 전 리그 빅딜 */}
      {sec("TOP TRANSFERS", "전 리그 빅딜")}
      <div className="hub-deals">
        {d.top_deals.map((x, i) => (
          <button className="hub-deal" key={i} onClick={() => onPick(x.to, x.league)}>
            {x.photo ? <img className="hub-deal-ph" src={x.photo} alt="" /> : <span className="hub-deal-ph ph" />}
            <div className="hub-deal-body">
              <div className="hub-deal-top"><b>{x.player}</b>{tag(x.league_name)}</div>
              <div className="hub-deal-mv">
                <span className="hub-from">{x.from || "—"}</span>
                <Arrow color={accent} />
                {x.to_logo && <img src={x.to_logo} alt="" />}<span className="hub-to">{x.to}</span>
              </div>
            </div>
            <div className="hub-deal-fee" style={{ color: accent }}>{fmtEur(x.fee_eur)}</div>
          </button>
        ))}
        {d.top_deals.length === 0 && <div className="mgr-meta">No major deals this window</div>}
      </div>

      {/* 선수 스포트라이트 — 세그먼티드(폼·유망주·베테랑·가성비·득점·급등) */}
      {(() => {
        const SPOTS = [
          { k: "form", en: "HOT FORM", kr: "최고 폼", list: (d.hot_form ?? []) as any[] },
          { k: "prospect", en: "PROSPECTS", kr: "유망주 원석", list: (d.prospects ?? []) as any[] },
          { k: "veteran", en: "VETERANS", kr: "베테랑 32+", list: (d.veterans ?? []) as any[] },
          { k: "value", en: "VALUE PICKS", kr: "저평가 가성비", list: (d.value_picks ?? []) as any[] },
          { k: "goal", en: "GOAL LEADERS", kr: "득점 리더", list: (d.goal_leaders ?? []) as any[] },
          { k: "riser", en: "VALUE RISERS", kr: "시장가치 급등", list: (d.risers ?? []) as any[] },
        ].filter((s) => s.list.length > 0);
        if (!SPOTS.length) return null;
        const cur = SPOTS.find((s) => s.k === spot) || SPOTS[0];
        return (
          <>
            <div className="hub-h">
              <span className="hub-h-bar" style={{ background: accent }} />
              <span className="hub-h-en">PLAYER SPOTLIGHT</span><span className="hub-h-kr">선수 스포트라이트</span>
              <div style={{ display: "inline-flex", flexWrap: "wrap", gap: 3, marginLeft: "auto", padding: 3, borderRadius: 10, background: "rgba(255,255,255,0.05)" }}>
                {SPOTS.map((s) => (
                  <button key={s.k} onClick={() => setSpot(s.k)}
                    style={{ padding: "5px 11px", borderRadius: 7, fontSize: 11.5, fontWeight: 700, cursor: "pointer", border: "none",
                      background: cur.k === s.k ? accent : "transparent", color: cur.k === s.k ? "#0a0a0a" : "inherit", opacity: cur.k === s.k ? 1 : 0.6 }}>{s.kr}</button>
                ))}
              </div>
            </div>
            <div className="card hub-list" style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "1px 16px" }}>
              {cur.list.map((p: any, i: number) => (
                <button className="hub-plr" key={i} onClick={() => onPick(p.club, p.league)}>
                  <span className="hub-plr-rk">{i + 1}</span>
                  {p.photo ? <img className="hub-plr-ph" src={p.photo} alt="" /> : <span className="hub-plr-ph ph" />}
                  <div className="hub-plr-body">
                    <div className="hub-plr-nm">{p.player} {tag(p.league_name)}</div>
                    <div className="hub-plr-sub">
                      {p.club_logo && <img src={p.club_logo} alt="" />}{p.club}
                      {(cur.k === "prospect" || cur.k === "veteran") && p.age ? ` · ${p.age}세` : ""}
                      {(cur.k === "value" || cur.k === "riser") && p.value_eur ? ` · ${fmtEur(p.value_eur)}` : (cur.k !== "goal" && p.pos ? ` · ${p.pos}` : "")}
                    </div>
                  </div>
                  {cur.k === "goal"
                    ? (<><span className="hub-plr-metric big" style={{ color: accent }}>⚽{p.goals}</span><span className="hub-plr-a">{p.assists}A</span></>)
                    : cur.k === "riser"
                      ? (<span className="hub-plr-metric big" style={{ color: "#4fc27f" }}>▲{p.pct}%</span>)
                      : (<><span className="hub-plr-ovr" style={{ color: tier(p.ovr).light }}>{p.ovr}</span>
                          {p.rating != null && <span className="hub-plr-metric" style={{ color: accent }}>{p.rating.toFixed(2)}</span>}</>)}
                </button>
              ))}
            </div>
          </>
        );
      })()}

      {/* 이적 속보 + 감독 교체 */}
      <div className="hub-two">
        <div>
          {sec("TRANSFER WIRE", "이적 속보")}
          <div className="card hub-list">
            {d.buzz.map((b, i) => (
              <a className="hub-buzz" href={b.link || undefined} target="_blank" rel="noopener noreferrer" key={i}>
                <span className={`hub-tier ${b.tier}`}>{b.tier === "agreed" ? "DONE" : "RUMOUR"}</span>
                <span className="hub-buzz-t">{b.title}</span>
                <span className="hub-buzz-src">{tag(b.league_name)} {b.source}</span>
              </a>
            ))}
            {d.buzz.length === 0 && <div className="mgr-meta">No transfer news</div>}
          </div>
        </div>
        <div>
          {sec("MANAGER MOVES", "감독 교체")}
          <div className="card hub-list">
            {d.manager_changes.map((c, i) => (
              <button className="hub-mgr" key={i} onClick={() => onPick(c.team, c.league)}>
                {c.photo ? <img className="hub-mgr-ph" src={c.photo} alt="" /> : (c.logo && <img className="hub-mgr-ph" src={c.logo} alt="" />)}
                <div className="hub-mgr-body">
                  <div className="hub-mgr-team">{c.team} {tag(c.league_name)}</div>
                  <div className="hub-mgr-ch">
                    <span className="hub-mgr-prev">{c.previous}</span>
                    <Arrow color={accent} /><b>{c.current}</b>
                  </div>
                </div>
              </button>
            ))}
            {d.manager_changes.length === 0 && <div className="mgr-meta">No manager changes</div>}
          </div>
        </div>
      </div>

      {/* 부상 속보 + 곧 FA */}
      <div className="hub-two">
        <div>
          {sec("INJURY WATCH", "부상 속보")}
          <div className="card hub-list">
            {d.injuries.map((p, i) => (
              <button className="hub-plr" key={i} onClick={() => onPick(p.club, p.league)}>
                {p.photo ? <img className="hub-plr-ph" src={p.photo} alt="" /> : <span className="hub-plr-ph ph" />}
                <div className="hub-plr-body">
                  <div className="hub-plr-nm">{p.player} {tag(p.league_name)}</div>
                  <div className="hub-plr-sub">{p.club_logo && <img src={p.club_logo} alt="" />}{p.club} · {p.injury}</div>
                </div>
                <span className={`hub-inj ${p.event}`}>{p.event === "return" ? "복귀" : "부상"}</span>
              </button>
            ))}
            {d.injuries.length === 0 && <div className="mgr-meta">No injury updates</div>}
          </div>
        </div>
        <div>
          {sec("CONTRACT COUNTDOWN", "곧 FA · 계약 만료 임박")}
          <div className="card hub-list">
            {d.contracts.map((p, i) => (
              <button className="hub-plr" key={i} onClick={() => onPick(p.club, p.league)}>
                {p.photo ? <img className="hub-plr-ph" src={p.photo} alt="" /> : <span className="hub-plr-ph ph" />}
                <div className="hub-plr-body">
                  <div className="hub-plr-nm">{p.player} {tag(p.league_name)}</div>
                  <div className="hub-plr-sub">{p.club_logo && <img src={p.club_logo} alt="" />}{p.club} · {fmtEur(p.value_eur)}</div>
                </div>
                <span className="hub-plr-ovr" style={{ color: tier(p.ovr).light }}>{p.ovr}</span>
                <span className="hub-plr-until">~{p.until?.slice(2)}</span>
              </button>
            ))}
            {d.contracts.length === 0 && <div className="mgr-meta">No expiring contracts</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
