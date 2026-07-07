"use client";
import type { Overview } from "@/lib/api";
import { fmtEur } from "@/lib/api";
import { tier, hexA, roleClass } from "@/lib/ui";
import Radar from "./Radar";
import RatingsBoard from "./RatingsBoard";
import TransferTicker from "./TransferTicker";
import LineupBoard from "./LineupBoard";
import CaptainBoard from "./CaptainBoard";
import OverviewSignals from "./OverviewSignals";
import IdentityCard from "./IdentityCard";

function repStars(rank?: number | null): string {
  if (!rank) return "★★★☆☆";
  const n = rank <= 2 ? 5 : rank <= 6 ? 4 : rank <= 11 ? 3 : rank <= 16 ? 2 : 1;
  return "★".repeat(n) + "☆".repeat(5 - n);
}

function Delta({ d }: { d?: number }) {
  if (!d) return null;
  const up = d > 0;
  return (
    <span className="delta" style={{ color: up ? "#4fc27f" : "#e07070" }} title="26/27 이적 반영 변화">
      {up ? "▲" : "▼"}{Math.abs(d)}
    </span>
  );
}

function Unit({ label, value, color, delta }: { label: string; value: number; color: string; delta?: number }) {
  const t = tier(value);
  return (
    <div className="unit">
      <div className="unit-top"><b>{label}</b><span><Delta d={delta} /><span style={{ color: t.light }}>{value}</span></span></div>
      <div className="bar"><span style={{ width: `${value}%`, background: `linear-gradient(90deg, ${t.deep}, ${t.light})` }} /></div>
    </div>
  );
}

export default function OverviewTab({ ov, accent }: { ov: Overview; accent: string }) {
  const t = tier(ov.ovr.overall);
  const s = ov.standing;
  const info = ov.info || {};
  const snap = ov.snapshot;

  return (
    <div className="fade">
      <TransferTicker tin={ov.transfers.in} tout={ov.transfers.out} accent={accent}
        label={ov.window?.is_open ? `${ov.window.label} ${ov.window.kr ?? ""} 이적` : `${ov.data_season} 이적`} />
      {ov.window && (
        <div className="season-note">
          <b>{ov.data_season} 시즌 종료</b>
          {ov.window.is_open
            ? <> · <span style={{ color: accent }}>{ov.window.label} {ov.window.kr} 이적시장 진행 중</span> — 아래 이적 정보는 이번 창(window) 기준</>
            : <> · 현재 이적시장 마감</>}
        </div>
      )}

      {/* HERO */}
      <div className="hero" style={{ background: `linear-gradient(120deg, ${hexA(ov.color, 0.30)}, ${hexA(ov.color, 0.03)} 55%, transparent)` }}>
        <div className="hero-glow" style={{ background: `radial-gradient(circle, ${hexA(accent, 0.5)}, transparent 70%)` }} />
        {ov.logo && <img className="hero-logo" src={ov.logo} alt="" />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="hero-rank">#{s.rank} · PREMIER LEAGUE · {info.nick || ""}</div>
          <h1>{ov.team}</h1>
          <div className="full">{ov.fullName} · {info.stadium || ""} · {ov.capacity.toLocaleString()}석</div>
          <div className="form-row">
            {ov.form.length === 0 && <span className="full">최근 경기 없음</span>}
            {ov.form.map((f, i) => <div key={i} className={`dot ${f}`}>{f}</div>)}
          </div>
        </div>
        <div className="ovr-badge" style={{ borderColor: hexA(t.light, 0.5) }}>
          <div className="teko ovr-n" style={{ color: t.light }}>{ov.ovr.overall}</div>
          <div className="ovr-cap" style={{ color: t.light }}>{t.name}</div>
          <div className="ovr-sub">OVERALL{ov.ovr_delta?.overall ? <Delta d={ov.ovr_delta.overall} /> : null}</div>
        </div>
      </div>

      {/* 구단 정보 배너 */}
      <div className="info-strip">
        <div className="info-item"><span className="l">평판</span><span className="v" style={{ color: "#f9dd7e", letterSpacing: 1 }}>{repStars(info.value_rank)}</span></div>
        <div className="info-item"><span className="l">연고지</span><span className="v">{info.city || "-"}</span></div>
        <div className="info-item"><span className="l">창단</span><span className="v">{info.founded || "-"}</span></div>
        <div className="info-item"><span className="l">스쿼드 가치</span><span className="v">{info.squad_value ? fmtEur(info.squad_value) : "-"}<em> ({info.value_rank ? info.value_rank + "위" : "-"})</em></span></div>
      </div>
      {info.desc && <div className="info-desc" style={{ borderColor: hexA(accent, 0.3) }}>{info.desc}</div>}

      {/* 최근 감지 변화 */}
      <OverviewSignals team={ov.team} accent={accent} />

      {/* GRID */}
      <div className="grid">
        <div className="card">
          <h3>Unit Ratings{(ov.ovr_delta && (ov.ovr_delta.attack || ov.ovr_delta.midfield || ov.ovr_delta.defense || ov.ovr_delta.overall))
            ? <span className="rating-note">· {ov.window?.label ?? ""} 이적 반영 <b style={{ color: "#4fc27f" }}>▲</b>/<b style={{ color: "#e07070" }}>▼</b></span> : null}</h3>
          <div className="unit-list">
            <Unit label="ATTACK" value={ov.ovr.attack} color={accent} delta={ov.ovr_delta?.attack} />
            <Unit label="MIDFIELD" value={ov.ovr.midfield} color={accent} delta={ov.ovr_delta?.midfield} />
            <Unit label="DEFENSE" value={ov.ovr.defense} color={accent} delta={ov.ovr_delta?.defense} />
          </div>
          <div className="stat-strip">
            <div className="stat"><div className="v">{s.points}</div><div className="l">Points</div></div>
            <div className="stat"><div className="v">{s.gf}</div><div className="l">Goals</div></div>
            <div className="stat"><div className="v">{s.gd > 0 ? "+" : ""}{s.gd}</div><div className="l">Diff</div></div>
            <div className="stat"><div className="v">{s.ga}</div><div className="l">Conceded</div></div>
          </div>
        </div>

        <div className="card">
          <h3>Team Profile</h3>
          <Radar data={ov.radar} color={accent} />
        </div>

        {snap && (
          <div className="card">
            <h3>득점 유형 · 규율</h3>
            <div className="stat-strip" style={{ marginTop: 0 }}>
              <div className="stat"><div className="v" style={{ color: accent }}>{snap.open_play}</div><div className="l">오픈플레이</div></div>
              <div className="stat"><div className="v" style={{ color: accent }}>{snap.set_piece}</div><div className="l">세트피스</div></div>
              <div className="stat"><div className="v" style={{ color: accent }}>{snap.penalty}</div><div className="l">페널티</div></div>
              <div className="stat"><div className="v">{snap.yellow_per_match}</div><div className="l">경고/경기</div></div>
            </div>
            <div className="disc-row">
              <span className="disc yellow">🟨 {snap.yellows}</span>
              <span className="disc red">🟥 {snap.reds}</span>
            </div>
            {(ov.edge.strengths.length > 0 || ov.edge.weaknesses.length > 0) && (
              <div className="edge-box">
                <div className="edge-col">
                  <div className="edge-h" style={{ color: "#4fc27f" }}>강점</div>
                  {ov.edge.strengths.map((e, i) => <span className="edge-chip s" key={i}>{e.label} <b>{e.value}</b></span>)}
                </div>
                <div className="edge-col">
                  <div className="edge-h" style={{ color: "#e07070" }}>보강</div>
                  {ov.edge.weaknesses.map((e, i) => <span className="edge-chip w" key={i}>{e.label} <b>{e.value}</b></span>)}
                </div>
              </div>
            )}
          </div>
        )}

        <div className="card">
          <h3>Manager</h3>
          {ov.manager ? (
            <>
              <div className="mgr">
                {ov.manager.photo ? (
                  <img className="mgr-photo" src={ov.manager.photo} alt={ov.manager.name}
                    style={{ borderColor: hexA(accent, 0.4) }} />
                ) : (
                  <div className="mgr-avatar" style={{ background: `linear-gradient(135deg, ${hexA(accent, 0.5)}, ${hexA(accent, 0.15)})` }}>
                    {ov.manager.name.split(" ").map((w) => w[0]).slice(0, 2).join("")}
                  </div>
                )}
                <div style={{ minWidth: 0 }}>
                  <div className="mgr-name">{ov.manager.name}</div>
                  <div className="mgr-meta">
                    {[ov.manager.nationality, ov.manager.formation, ov.manager.appointed ? "부임 " + ov.manager.appointed : ""].filter(Boolean).join(" · ")}
                  </div>
                  {ov.manager.previous && (
                    <div className="mgr-change" style={{ color: accent }}>
                      ⟲ {ov.manager.previous.name} → {ov.manager.name.replace(/\s*\(interim\)/i, "")}
                      {ov.manager.changed_at ? <em> · {ov.manager.changed_at} 교체</em> : null}
                    </div>
                  )}
                </div>
              </div>
              {ov.manager.bio && <div className="mgr-bio">{ov.manager.bio}</div>}
              <div className="mgr-src">출처: Wikipedia</div>
            </>
          ) : <div className="mgr-meta">감독 정보 없음</div>}
        </div>
      </div>

      {/* 팀 정체성 — 감독 전술 블렌드 · 영입 성향 · 예산 */}
      <IdentityCard team={ov.team} league={ov.league} accent={accent} />

      {/* 주장단 */}
      <CaptainBoard team={ov.team} accent={accent} />

      {/* 포메이션 (시즌평균 / 최근5 / 26/27예상 토글) */}
      <LineupBoard team={ov.team} accent={accent} departed={ov.departed} />

      {/* 핵심 선수 */}
      {ov.stars.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>핵심 선수 · Top 5 (평점 기준)</h3>
          <div className="stars-row">
            {ov.stars.map((st, i) => {
              const tt = tier(st.ovr);
              return (
                <div className="star-card" key={i}>
                  {st.big_match && <span className="star-bm" title="UCL/UEL 급 무대 검증">⚡</span>}
                  {st.photo ? <img src={st.photo} alt="" /> : <span className="star-ph" />}
                  <div className="star-ovr" style={{ color: tt.light }}>
                    {st.ovr}{st.pot && st.pot > st.ovr ? <span className="star-pot">↗{st.pot}</span> : null}
                  </div>
                  <div className="star-name">{st.player}</div>
                  <div className="star-meta">{st.pos}{st.form ? <> · 폼 <b style={{ color: st.form >= 85 ? "#4fc27f" : st.form >= 75 ? "#f4cf5e" : "#e0707a" }}>{st.form}</b></> : ""}</div>
                  <div className="star-ga">{st.goals}G {st.assists}A</div>
                  {st.role && <span className={"role-tag sm " + roleClass(st.role)}>{st.role}</span>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 스쿼드 절대 평가 — OVR/POT 산점도 */}
      <RatingsBoard ov={ov} accent={accent} />

      {/* 팀 리더 */}
      {ov.leaders.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>팀 리더 · 부문별 1위</h3>
          <div className="leaders-row">
            {ov.leaders.map((ld, i) => (
              <div className="leader" key={i}>
                <div className="leader-lbl" style={{ color: accent }}>{ld.label}</div>
                {ld.photo ? <img src={ld.photo} alt="" /> : <span className="leader-ph" />}
                <div className="leader-name">{ld.player.split(" ").slice(-1)[0]}</div>
                <div className="leader-val teko">{ld.value}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 부상 + 이적 2열 */}
      <div className="grid" style={{ marginTop: 16 }}>
        <div className="card">
          <h3>현재 부상자 · {ov.injuries.length}명</h3>
          <div className="tf2-list">
            {ov.injuries.map((x, i) => (
              <div className="tf2-row" key={i}>
                {x.photo ? <img className="tf2-photo" src={x.photo} alt="" /> : <span className="tf2-photo ph" />}
                <div className="tf2-info">
                  <div className="tf2-name">{x.player}</div>
                  <div className="tf2-meta">{x.pos} · {x.injury || "부상"}</div>
                </div>
                <span className="inj-until">~{x.until?.slice(0, 5) || "?"}</span>
              </div>
            ))}
            {ov.injuries.length === 0 && <div className="mgr-meta">부상자 없음 ✓</div>}
          </div>
        </div>

        <div className="card">
          <h3>이적 · In / Out</h3>
          <div className="tf-list">
            {ov.transfers.in.slice(0, 4).map((x, i) => (
              <div key={"i" + i} className="tf-row tf-in">
                <span className="tf-ar">▲</span><span className="tf-name">{x.player}</span>
                <span className="tf-pos">{x.pos}</span><span className="tf-fee">{x.fee_text || "-"}</span>
              </div>
            ))}
            {ov.transfers.out.slice(0, 3).map((x, i) => (
              <div key={"o" + i} className="tf-row tf-out">
                <span className="tf-ar">▼</span><span className="tf-name">{x.player}</span>
                <span className="tf-pos">{x.pos}</span><span className="tf-fee">{x.fee_text || "-"}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
