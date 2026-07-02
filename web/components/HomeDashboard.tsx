"use client";
import { useEffect, useState, type ReactNode } from "react";
import { getHome, type Home } from "@/lib/api";

const eurM = (v: number) => (v >= 1e6 ? `€${Math.round(v / 1e6)}M` : v > 0 ? `€${Math.round(v / 1e3)}K` : "€0");

function Sec({ en, kr, accent, right }: { en: string; kr: string; accent: string; right?: ReactNode }) {
  return (
    <div className="sec-head">
      <span className="sec-bar" style={{ background: accent }} />
      <div className="sec-txt">
        <div className="sec-en">{en}</div>
        <div className="sec-kr">{kr}</div>
      </div>
      {right && <div className="sec-right">{right}</div>}
    </div>
  );
}

export default function HomeDashboard({ accent, onPickTeam }: { accent: string; onPickTeam: (t: string) => void }) {
  const [h, setH] = useState<Home | null>(null);
  useEffect(() => { let a = true; getHome().then((d) => a && setH(d)).catch(() => {}); return () => { a = false; }; }, []);
  if (!h) return <div className="loading">불러오는 중…</div>;

  const nextLabel = h.roster_next?.season_label || "26/27";
  const deals = h.transfers.top_deals;
  const feat = deals[0];
  const maxSpend = Math.max(1, ...h.transfers.net_spend.map((n) => n.spend));

  return (
    <div className="fade home">
      {/* ── HERO ── */}
      <div className="hx" style={{ ["--tc" as any]: accent }}>
        <div className="hx-glow" style={{ background: `radial-gradient(60% 120% at 85% 0%, ${accent}44, transparent 70%)` }} />
        <div className="hx-top">
          <div className="comp-seg">
            <button className="active">EPL</button>
            <button className="soon wc" title="2026 월드컵 진행 중 · 데이터 연동 예정"><span className="wc-dot" />WC 26</button>
            <button className="soon">OTHER<em>SOON</em></button>
          </div>
          <div className="hx-live">
            <span className="livedot" />
            {h.window.is_open ? `${h.window.label} ${h.window.kr ?? ""} 이적시장 OPEN` : `${h.season} 시즌`}
          </div>
        </div>

        <div className="hx-kicker">{nextLabel} SEASON · TRANSFER WINDOW</div>
        <h1 className="hx-title">PREMIER LEAGUE</h1>
        <div className="hx-meta">{h.season} 시즌 종료 · {nextLabel} 개막 전{h.window.is_open ? " · 여름 이적시장 진행 중" : ""}</div>

        <div className="kpis">
          <div className="kpi"><div className="kpi-n teko" style={{ color: accent }}>{eurM(h.kpi.spend)}</div><div className="kpi-l">이적 총지출</div></div>
          <div className="kpi"><div className="kpi-n teko">{h.kpi.deals}</div><div className="kpi-l">영입 건수</div></div>
          <div className="kpi"><div className="kpi-n teko">{h.kpi.mgr_changes}</div><div className="kpi-l">감독 교체</div></div>
          <div className="kpi"><div className="kpi-n teko">{h.kpi.injuries}</div><div className="kpi-l">부상 변동</div></div>
        </div>
      </div>

      {/* ── 이적 속보 (LIVE 피드) ── */}
      {h.buzz && h.buzz.length > 0 && (
        <>
          <Sec en="TRANSFER WIRE" kr="이적 속보" accent={accent}
            right={<span className="wire-live"><span className="wc-dot" />LIVE</span>} />
          <div className="card">
            <div className="wire">
              {h.buzz.slice(0, 12).map((b, i) => (
                <a className="wire-row" key={i} href={b.link || undefined} target="_blank" rel="noreferrer">
                  <span className={`wire-tag ${b.tier}`}>{b.tier === "agreed" ? "합의" : "루머"}</span>
                  <div className="wire-mid">
                    <b>{b.title}</b>
                    <span>{[b.source, b.published ? b.published.slice(5) : ""].filter(Boolean).join(" · ")}</span>
                  </div>
                </a>
              ))}
            </div>
          </div>
        </>
      )}

      {/* ── 이적시장 ── */}
      <Sec en="TRANSFER MARKET" kr="이적 시장" accent={accent} />
      <div className="home-grid">
        <div className="card">
          {feat && (
            <button className="feat" onClick={() => onPickTeam(feat.to)} style={{ ["--tc" as any]: accent }}>
              <div className="feat-tag">최대어</div>
              <div className="feat-row">
                {feat.to_logo && <img className="feat-logo" src={feat.to_logo} alt="" />}
                <div className="feat-mid">
                  <div className="feat-name">{feat.player}</div>
                  <div className="feat-move">{feat.from} <span className="feat-arr">→</span> {feat.to}</div>
                </div>
                <div className="feat-fee teko" style={{ color: accent }}>{feat.fee_text}</div>
              </div>
            </button>
          )}
          <div className="rows">
            {deals.slice(1, 6).map((d, i) => (
              <button className="row2" key={i} onClick={() => onPickTeam(d.to)}>
                <span className="row2-idx">{i + 2}</span>
                {d.to_logo ? <img src={d.to_logo} alt="" /> : <span className="ph22" />}
                <div className="row2-mid"><b>{d.player}</b><span>{d.from} → {d.to}</span></div>
                <span className="row2-r teko">{d.fee_text}</span>
              </button>
            ))}
            {deals.length === 0 && <div className="mgr-meta">이번 창 영구이적 없음</div>}
          </div>
        </div>

        <div className="card">
          <div className="card-h">순지출 랭킹</div>
          <div className="rows">
            {h.transfers.net_spend.slice(0, 7).map((n) => (
              <button className="netx" key={n.team} onClick={() => onPickTeam(n.team)}>
                {n.logo ? <img src={n.logo} alt="" /> : <span className="ph22" />}
                <span className="netx-team">{n.team}</span>
                <span className="netx-track"><span className="netx-fill" style={{ width: `${(n.spend / maxSpend) * 100}%`, background: accent }} /></span>
                <span className="netx-val teko">{eurM(n.spend)}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── 자동 감지 ── */}
      <Sec en="LIVE SIGNALS" kr="자동 감지" accent={accent}
        right={<span className="sec-count">{h.signals.length}</span>} />
      <div className="card">
        <div className="sig-grid">
          {h.signals.slice(0, 8).map((s, i) => (
            <button className={`sigx ${s.tone}`} key={i} onClick={() => s.team && onPickTeam(s.team)}>
              <span className="sigx-ic">{s.icon}</span>
              <div className="sigx-mid">
                <b>{s.title}</b>
                <span>{[s.player, s.detail].filter(Boolean).join(" · ")}</span>
              </div>
              {s.logo && <img className="sigx-logo" src={s.logo} alt="" />}
            </button>
          ))}
        </div>
      </div>

      {/* ── 감독 교체 ── */}
      {h.manager_changes.length > 0 && (
        <>
          <Sec en="THE DUGOUT" kr="감독 교체" accent={accent}
            right={<span className="sec-count">{h.manager_changes.length}</span>} />
          <div className="mgr-rail">
            {h.manager_changes.map((c, i) => (
              <button className="mgx" key={i} onClick={() => onPickTeam(c.team)}>
                {c.photo ? <img className="mgx-photo" src={c.photo} alt="" /> : <span className="mgx-ph" />}
                {c.logo && <img className="mgx-logo" src={c.logo} alt="" />}
                <div className="mgx-name">{c.current.replace(/\s*\(interim\)/i, "")}</div>
                <div className="mgx-prev">← {c.previous.replace(/\s*\(interim\)/i, "")}</div>
                <div className="mgx-meta">{[c.formation, c.changed_at].filter(Boolean).join(" · ")}</div>
              </button>
            ))}
          </div>
        </>
      )}

      {/* ── 뉴스 · 순위 ── */}
      <Sec en="LATEST" kr="뉴스 · 순위" accent={accent} />
      <div className="home-grid">
        <div className="card">
          <div className="card-h">헤드라인</div>
          <div className="rows">
            {h.news.length === 0 && <div className="mgr-meta">뉴스 없음</div>}
            {h.news.slice(0, 6).map((n, i) => (
              <a className="newx" key={i} href={n.link || undefined} target="_blank" rel="noreferrer">
                {n.image ? <img src={n.image} alt="" /> : <span className="newx-ph" />}
                <div className="newx-mid"><b>{n.headline}</b><span>{[n.team, n.source].filter(Boolean).join(" · ")}</span></div>
              </a>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-h">{h.season} 최종 순위</div>
          <div className="rows">
            {h.standings.slice(0, 10).map((t) => (
              <button className="stx" key={t.name} onClick={() => onPickTeam(t.name)}>
                <span className={`stx-rank${t.rank <= 5 ? " ucl" : t.rank >= h.standings.length - 2 ? " rel" : ""}`}>{t.rank}</span>
                {t.logo ? <img src={t.logo} alt="" /> : <span className="ph22" />}
                <span className="stx-name">{t.name}</span>
                <span className="stx-pts teko">{t.points}</span>
              </button>
            ))}
          </div>
          <div className="stx-foot">
            {nextLabel} 승격 <b style={{ color: "#4fc27f" }}>{h.roster_next?.promoted?.join(", ") || "-"}</b>
            <br />강등 <b style={{ color: "#e0556b" }}>{h.roster_next?.relegated?.join(", ") || "-"}</b>
          </div>
        </div>
      </div>
    </div>
  );
}
