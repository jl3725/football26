"use client";
import type { Overview } from "@/lib/api";
import { feeLabel, fmtEur } from "@/lib/api";
import { tier, hexA, roleClass, futTier } from "@/lib/ui";
import Radar from "./Radar";
import RatingsBoard from "./RatingsBoard";
import TransferTicker from "./TransferTicker";
import LineupBoard from "./LineupBoard";
import CaptainBoard from "./CaptainBoard";
import OvrGuide from "./OvrGuide";
import OverviewSignals from "./OverviewSignals";
import IdentityCard from "./IdentityCard";
import { usePeek } from "./PlayerPeek";
import { Skel } from "./Skeleton";
import { phaseOf } from "@/lib/season";
import { useEffect, useState } from "react";
import { TrendArrow } from "./Trend";
import NextMatch from "./NextMatch";
import { usePins } from "@/lib/pins";
import SectionHead from "./SectionHead";
import { GoalMixCompare, SeasonProfile, SeasonSnapshot, useTeamSeason } from "./TeamSeason";

function repStars(rank?: number | null): string {
  if (!rank) return "★★★☆☆";
  const n = rank <= 2 ? 5 : rank <= 6 ? 4 : rank <= 11 ? 3 : rank <= 16 ? 2 : 1;
  return "★".repeat(n) + "☆".repeat(5 - n);
}

function Delta({ d }: { d?: number }) {
  if (!d) return null;
  const up = d > 0;
  return (
    <span className="delta" style={{ color: up ? "#4fc27f" : "#e07070" }} title="이번 이적시장 반영 변화">
      {up ? "▲" : "▼"}{Math.abs(d)}
    </span>
  );
}

type UnitWho = { player: string; strength: number; injured?: boolean; until?: string }[];
const shortName = (n: string) => { const p = n.split(" "); return p.length > 1 ? p.slice(1).join(" ") : n; };

function Unit({ label, value, color, delta, perf, who }: { label: string; value: number; color: string; delta?: number; perf?: number; who?: UnitWho }) {
  const t = tier(value);
  return (
    <div className="unit">
      <div className="unit-top"><b>{label}</b><span><Delta d={delta} />
        {perf != null && Math.abs(perf) >= 0.5 && (
          <em className={`unit-perf ${perf > 0 ? "up" : "down"}`} title="실적 보정 — 경기당 득점·실점(리그 안 상대값), 이번 시즌과 지난 시즌을 경기 수로 섞음">
            기록 {perf > 0 ? "+" : ""}{perf.toFixed(1)}
          </em>
        )}
        <span style={{ color: t.light }}>{value}</span></span></div>
      <div className="bar"><span style={{ width: `${value}%`, background: `linear-gradient(90deg, ${t.deep}, ${t.light})` }} /></div>
      {who && who.length > 0 && (
        <div className="unit-who">
          {who.map((w) => (
            <span key={w.player} className={w.injured ? "inj" : ""} title={`${w.player} ${w.strength}${w.injured ? ` · 부상${w.until ? `(${w.until} 복귀 예정)` : ""}` : ""}`}>
              {shortName(w.player)}{w.injured ? " ✚" : ""}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function OverviewTab({ ov, accent }: { ov: Overview; accent: string }) {
  const t = tier(ov.ovr.overall);
  const s = ov.standing;
  const info = ov.info || {};
  const snap = ov.snapshot;
  const peek = usePeek();
  const [more, setMore] = useState(false);
  useEffect(() => { try { setMore(localStorage.getItem("ov_more") === "1"); } catch { /* 저장소 차단 */ } }, []);
  const toggleMore = (v: boolean) => { setMore(v); try { localStorage.setItem("ov_more", v ? "1" : "0"); } catch { /* 무시 */ } };
  const season = useTeamSeason(ov.team, ov.league);   // 시즌 현황·프로필(순위·근거 포함)
  const leagueCap = (ov.league || "EPL").replace(/([a-z])([A-Z])/g, "$1 $2").replace(/([a-zA-Z])(\d)/g, "$1 $2").toUpperCase();

  return (
    <div className="fade">
      <TransferTicker tin={ov.transfers.in} tout={ov.transfers.out} accent={accent}
        label={ov.window?.is_open ? `${ov.window.label} ${ov.window.kr ?? ""} 이적` : `${ov.data_season} 이적`} />
      {/* 이적시장이 열렸을 때만 — 닫혀 있으면 상단 상태 줄과 같은 말의 반복이었다 */}
      {ov.window?.is_open && (
        <div className="season-note">
          <b>{ov.data_season} 시즌 {phaseOf(ov.window) === "in_season" ? "진행 중" : "종료"}</b>
          {ov.window.is_open
            ? <> · <span style={{ color: accent }}>{ov.window.label} {ov.window.kr} 이적시장 진행 중</span> — 아래 이적 정보는 이번 창(window) 기준</>
            : <> · 현재 이적시장 마감</>}
        </div>
      )}

      {/* HERO */}
      <div className="hero" style={{ background: `linear-gradient(120deg, ${hexA(ov.color, 0.30)}, ${hexA(ov.color, 0.03)} 55%, transparent)` }}>
        <div className="hero-glow" style={{ background: `radial-gradient(circle, ${hexA(accent, 0.5)}, transparent 70%)` }} />
        {ov.logo && <img className="hero-mark" src={ov.logo} alt="" aria-hidden="true" />}
        {ov.logo && <img className="hero-logo" src={ov.logo} alt="" />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="hero-rank">#{s.rank} · {leagueCap} · {info.nick || ""}</div>
          <h1>{ov.team}</h1>
          <div className="full">{ov.fullName} · {info.stadium || ""} · {ov.capacity.toLocaleString()}석</div>
          <div className="form-row">
            {ov.form.length === 0 && <span className="full">최근 경기 없음</span>}
            {ov.form.map((f, i) => <div key={i} className={`dot ${f}`}>{f}</div>)}
            <PinButton team={ov.team} league={ov.league} logo={ov.logo} />
          </div>
        </div>
        <div className="ovr-badge" style={{ borderColor: hexA(t.light, 0.5) }}>
          <div className="teko ovr-n" style={{ color: t.light }}>{ov.ovr.overall}</div>
          <div className="ovr-cap" style={{ color: t.light }}>{t.name}</div>
          <div className="ovr-sub">OVERALL{ov.ovr_delta?.overall ? <Delta d={ov.ovr_delta.overall} /> : null}</div>
        </div>
      </div>

      {/* 지금 이 팀이 어떤가 — 순위·승점 흐름·최근 5경기(리뷰). 바뀌지 않는 구단 정보는 아래 CLUB 카드로 */}
      <div className="ov5-top"><SeasonSnapshot d={season} team={ov.team} league={ov.league} color={ov.color} /></div>

      {/* 다음 경기(전 대회) — 상대 순위·최근 폼·전력 비교 */}
      <NextMatch team={ov.team} />

      {/* 최근 감지 변화(시장가치 급등·급락 등) */}
      <OverviewSignals team={ov.team} accent={accent} />

      {/* GRID */}
      <div className="grid">
        <div className="card">
          <SectionHead title="SQUAD STRENGTH" kr="선수 평점 기반 전력"
            meta={(ov.ovr_delta && (ov.ovr_delta.attack || ov.ovr_delta.midfield || ov.ovr_delta.defense || ov.ovr_delta.overall))
              ? <>{ov.window?.label ?? ""} 이적 반영 <b style={{ color: "#4fc27f" }}>▲</b>/<b style={{ color: "#e07070" }}>▼</b></> : "라인별 주전 OVR"} />
          <div className="unit-list">
            <Unit label="ATTACK" value={ov.ovr.attack} color={accent} delta={ov.ovr_delta?.attack} perf={ov.ovr.perf_adj?.attack} who={ov.ovr.units?.attack} />
            <Unit label="MIDFIELD" value={ov.ovr.midfield} color={accent} delta={ov.ovr_delta?.midfield} perf={ov.ovr.perf_adj?.midfield} who={ov.ovr.units?.midfield} />
            <Unit label="DEFENSE" value={ov.ovr.defense} color={accent} delta={ov.ovr_delta?.defense} perf={ov.ovr.perf_adj?.defense} who={ov.ovr.units?.defense} />
          </div>
          <p className="sp5-note">라인별 상위 선수 평점(OVR + 출전 비례 이번 시즌 폼) + 기록 보정(경기당 득점·실점의 리그 안 상대값,
            이번 시즌과 지난 시즌을 경기 수로 섞어 ±2.5). 부상자(✚)도 &apos;가진 전력&apos;이라 포함합니다.</p>
        </div>

        <div className="card">
          <SectionHead title="SEASON PROFILE" kr="경기 내용 · 리그 순위" />
          {season === undefined ? <Skel h={220} r={10} /> : season?.profile.length ? <SeasonProfile axes={season.profile} />
            : <Radar data={ov.radar} color={accent} />}
        </div>

        {snap && (
          <div className="card">
            <SectionHead title="SCORING · DISCIPLINE" kr="득점 유형 · 규율" meta="리그 · Statbunker" />
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
            {season?.goal_mix && <GoalMixCompare mix={season.goal_mix} />}
          </div>
        )}

        {/* 득점 유형 카드가 없으면(시즌 초) 감독 카드가 홀로 반 칸만 차지해 오른쪽이 비었다 → 전체 폭 */}
        <div className={`card${snap ? "" : " span-all mgr-wide"}`}>
          <SectionHead title="MANAGER" kr="감독" />
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

        <div className="card span-all">
          <SectionHead title="CLUB" kr="구단 정보" />
          <div className="info-strip">
            <div className="info-item"><span className="l">평판</span><span className="v" style={{ color: "#f9dd7e", letterSpacing: 1 }}>{repStars(info.value_rank)}</span></div>
            <div className="info-item"><span className="l">연고지</span><span className="v">{info.city || "-"}</span></div>
            <div className="info-item"><span className="l">창단</span><span className="v">{info.founded || "-"}</span></div>
            <div className="info-item"><span className="l">스쿼드 가치</span><span className="v">{info.squad_value ? fmtEur(info.squad_value) : "-"}<em> ({info.value_rank ? info.value_rank + "위" : "-"})</em></span></div>
          </div>
          {info.desc && <div className="info-desc" style={{ borderColor: hexA(accent, 0.3) }}>{info.desc}</div>}
        </div>
      </div>



      {/* 포메이션 (시즌평균 / 최근5 / 26/27예상 토글) */}
      <LineupBoard team={ov.team} accent={accent} departed={ov.departed} />

      {/* 핵심 선수 */}
      {ov.stars.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <SectionHead title="KEY PLAYERS" kr="핵심 선수" meta="평점(OVR) TOP 5" right={<OvrGuide />} />
          <div className="stars-row">
            {ov.stars.map((st, i) => {
              const tt = tier(st.ovr);
              return (
                <div className={`star-card hoverable fut ${futTier(st.ovr)}`} key={i} style={{ cursor: "pointer" }}
                  onClick={(e) => peek(e, { name: st.player, club: ov.team, hint: { photo: st.photo, ovr: st.ovr, pos: st.pos, role: st.role, big_match: st.big_match } })}>
                  {st.big_match && <span className="star-bm" title="UCL/UEL 급 무대 검증">⚡</span>}
                  {st.photo ? <img src={st.photo} alt="" /> : <span className="star-ph" />}
                  <div className="star-ovr" style={{ color: tt.light }}>
                    {st.ovr}<TrendArrow t={st.trend} ovr={st.ovr} />{st.pot && st.pot > st.ovr ? <span className="star-pot">↗{st.pot}</span> : null}
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

      {/* 주장단 — 더 보기 밖으로(사용자 요청: 강조). 영향력 지도·리더십 코어는 NETWORK 탭 */}
      <CaptainBoard team={ov.team} accent={accent} />

      {/* 더 보기 — 정체성 · 스쿼드 평가 · 리더 · 부상/이적. 첫 화면은 '지금 이 팀이 어떤가'에 집중하고
          나머지는 요청 시 펼친다(선택은 이 브라우저에 기억). */}
      <button type="button" className="more-btn" aria-expanded={more} onClick={() => toggleMore(!more)}>
        {more ? "간단히 보기 ↑" : "더 보기 · 정체성 · 연령 구조 · 리더 · 부상/이적 ↓"}
      </button>
      {more && (
        <>
      {/* 팀 정체성 — 감독 전술 블렌드 · 영입 성향 · 예산 */}
      <IdentityCard team={ov.team} league={ov.league} accent={accent} />
      {/* 스쿼드 절대 평가 — OVR/POT 산점도 */}
      <RatingsBoard ov={ov} accent={accent} />
      {/* 팀 리더 */}
      {ov.leaders.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <SectionHead title="TEAM LEADERS" kr="부문별 1위" />
          <div className="leaders-row">
            {ov.leaders.map((ld, i) => (
              <div className="leader peekable" key={i}
                onClick={(e) => peek(e, { name: ld.player, club: ov.team, hint: { photo: ld.photo } })}>
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
          <SectionHead title="INJURIES" kr="현재 부상자" meta={`${ov.injuries.length}명`} />
          <div className="tf2-list">
            {ov.injuries.map((x, i) => (
              <div className="tf2-row peekable" key={i}
                onClick={(e) => peek(e, { name: x.player, club: ov.team, hint: { photo: x.photo, pos: x.pos } })}>
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
          <SectionHead title="TRANSFERS" kr="이적 In / Out" />
          <div className="tf-list">
            {ov.transfers.in.slice(0, 4).map((x, i) => (
              <div key={"i" + i} className="tf-row tf-in peekable"
                onClick={(e) => peek(e, { name: x.player, club: ov.team, hint: { pos: x.pos } })}>
                <span className="tf-ar">▲</span><span className="tf-name">{x.player}</span>
                <span className="tf-pos">{x.pos}</span><span className="tf-fee">{feeLabel(x.fee_eur, x.fee_text)}</span>
              </div>
            ))}
            {ov.transfers.out.slice(0, 3).map((x, i) => (
              <div key={"o" + i} className="tf-row tf-out peekable"
                onClick={(e) => peek(e, { name: x.player, hint: { pos: x.pos } })}>
                <span className="tf-ar">▼</span><span className="tf-name">{x.player}</span>
                <span className="tf-pos">{x.pos}</span><span className="tf-fee">{feeLabel(x.fee_eur, x.fee_text)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
        </>
      )}
    </div>
  );
}

// 내 팀 고정 — 사이드바 '내 팀'·홈 주의 보드가 먼저 보여 준다(이 브라우저에만 저장)
function PinButton({ team, league, logo }: { team: string; league: string; logo?: string }) {
  const { isPinned, toggle } = usePins();
  const on = isPinned(team);
  return (
    <button className={`pin-btn${on ? " on" : ""}`} aria-pressed={on} onClick={() => toggle({ team, league, logo })}
      title={on ? "내 팀에서 빼기" : "내 팀으로 고정 — 사이드바와 홈에서 먼저 보여 줍니다"}>
      {on ? "★ 내 팀" : "☆ 내 팀 고정"}
    </button>
  );
}
