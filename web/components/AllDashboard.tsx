"use client";
import { useEffect, useState } from "react";
import { getHomeAll, fmtEur, type HomeAll } from "@/lib/api";

// 전 리그 통합 대시보드 — 빅딜·이적속보·감독교체·순위 스냅샷을 한 화면에.
export default function AllDashboard({ accent, onPick }: { accent: string; onPick: (t: string, league?: string) => void }) {
  const [d, setD] = useState<HomeAll | null>(null);
  useEffect(() => { let a = true; getHomeAll().then((x) => a && setD(x)).catch(() => {}); return () => { a = false; }; }, []);
  if (!d) return <div className="loading">전 리그 데이터 불러오는 중…</div>;

  const tag = (name: string) => <span className="hub-lg">{name}</span>;

  return (
    <div className="fade home">
      <div className="hub-hero" style={{ ["--tc" as any]: accent }}>
        <div className="hub-hero-k">ALL LEAGUES · UNIFIED</div>
        <h1 className="hub-hero-t">전 리그 통합 대시보드</h1>
        <div className="hub-hero-m">{d.leagues.map((l) => l.name).join(" · ")}
          {d.window?.is_open && <span style={{ color: accent }}> · {d.window.label} {d.window.kr ?? ""} 이적시장 OPEN</span>}</div>
      </div>

      {/* 리그 스냅샷 */}
      <h3 className="hub-h">🏆 리그 스냅샷</h3>
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
      <h3 className="hub-h">💰 전 리그 빅딜 TOP</h3>
      <div className="hub-deals">
        {d.top_deals.map((x, i) => (
          <button className="hub-deal" key={i} onClick={() => onPick(x.to, x.league)}>
            {x.photo ? <img className="hub-deal-ph" src={x.photo} alt="" /> : <span className="hub-deal-ph ph" />}
            <div className="hub-deal-body">
              <div className="hub-deal-top"><b>{x.player}</b>{tag(x.league_name)}</div>
              <div className="hub-deal-mv">{x.from || "?"} → {x.to_logo && <img src={x.to_logo} alt="" />}{x.to}</div>
            </div>
            <div className="hub-deal-fee" style={{ color: accent }}>{fmtEur(x.fee_eur)}</div>
          </button>
        ))}
        {d.top_deals.length === 0 && <div className="mgr-meta">이번 창 빅딜 없음</div>}
      </div>

      {/* 이적 속보 + 감독 교체 */}
      <div className="hub-two">
        <div>
          <h3 className="hub-h">📰 전 리그 이적 속보</h3>
          <div className="card hub-list">
            {d.buzz.map((b, i) => (
              <a className="hub-buzz" href={b.link || undefined} target="_blank" rel="noopener noreferrer" key={i}>
                <span className={`hub-tier ${b.tier}`}>{b.tier === "agreed" ? "임박" : "루머"}</span>
                <span className="hub-buzz-t">{b.title}</span>
                <span className="hub-buzz-src">{tag(b.league_name)} {b.source}</span>
              </a>
            ))}
            {d.buzz.length === 0 && <div className="mgr-meta">이적 속보 없음</div>}
          </div>
        </div>
        <div>
          <h3 className="hub-h">🎓 전 리그 감독 교체</h3>
          <div className="card hub-list">
            {d.manager_changes.map((c, i) => (
              <button className="hub-mgr" key={i} onClick={() => onPick(c.team, c.league)}>
                {c.photo ? <img className="hub-mgr-ph" src={c.photo} alt="" /> : (c.logo && <img className="hub-mgr-ph" src={c.logo} alt="" />)}
                <div className="hub-mgr-body">
                  <div className="hub-mgr-team">{c.team} {tag(c.league_name)}</div>
                  <div className="hub-mgr-ch">{c.previous} → <b>{c.current}</b></div>
                </div>
              </button>
            ))}
            {d.manager_changes.length === 0 && <div className="mgr-meta">감지된 교체 없음</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
