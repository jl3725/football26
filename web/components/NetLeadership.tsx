"use client";
import type { NetCaptain, NetCore, NetworkData } from "@/lib/api";
import { hexA } from "@/lib/ui";
import { usePeek } from "./PlayerPeek";
import { LINE_COLOR, SvgAvatar, lastName } from "./NetShared";

// LEADERSHIP — 주장단(위키 스쿼드 표: 주장·부주장·3·4번째) + 영향력 지도(출전 비중·연결 중심성·근속·경험·대표팀·완장).
// 영향력 0~100 = 6요소(각 0~1) 가중합 × 100 — 출전·연결은 팀 안 최고 대비라 다른 팀과 비교하는 값이 아니다(src/team_network.leadership)
const INF_NOTE = "영향력 0~100 · 팀 안 상대값 — 출전·연결 중심성(팀 최고 대비)·근속·완장·경험·대표팀을 가중합, 100 = 모든 요소 만점";
const COMP: [string, string][] = [["minutes", "출전"], ["hub", "연결"], ["tenure", "근속"], ["experience", "경험"],
  ["international", "대표팀"], ["armband", "완장"]];

function CaptainHero({ c, team, accent, armband }: { c: NetCaptain; team: string; accent: string; armband: string | null }) {
  const peek = usePeek();
  const off = c.injured || (armband && armband !== c.name);
  return (
    <button className={`net-cap-hero hoverable${off ? " off" : ""}`} style={{ ["--ac" as string]: accent }}
      onClick={(e) => peek(e, { name: c.name, club: team, hint: { photo: c.photo, ovr: c.ovr ?? undefined, pos: c.pos } })}>
      {c.no != null && <span className="net-cap-no">{c.no}</span>}
      {c.photo ? <img src={c.photo} alt="" /> : <span className="net-cap-ph" />}
      <span className="net-band">C</span>
      <div className="net-cap-txt">
        <em>CAPTAIN · 주장</em>
        <b>{c.name}</b>
        <span>{[c.pos, c.ovr ? `OVR ${c.ovr}` : "", c.age ? `${c.age}세` : ""].filter(Boolean).join(" · ")}</span>
        <div className="net-chips">
          {c.tenure != null && <i>입단 {Math.max(1, Math.round(c.tenure))}년차</i>}
          {c.minutes > 0 && <i>{c.minutes.toLocaleString()}분</i>}
          {c.wc && <i>월드컵 명단</i>}
          {c.injured && <i className="bad">결장 · {c.injury || "부상"}</i>}
        </div>
      </div>
      <span className="net-cap-inf" title={`영향력 지수 ${c.influence} — ${INF_NOTE}`}>{c.influence}</span>
    </button>
  );
}

function CapMini({ c, team, armband }: { c: NetCaptain; team: string; armband: string | null }) {
  const peek = usePeek();
  return (
    <button className={`net-cap-mini hoverable${armband === c.name ? " wearing" : ""}`}
      onClick={(e) => peek(e, { name: c.name, club: team, hint: { photo: c.photo, ovr: c.ovr ?? undefined, pos: c.pos } })}>
      <span className="net-band sm">{c.label}</span>
      {c.photo ? <img src={c.photo} alt="" /> : <span className="net-cap-ph sm" />}
      <b>{c.name}</b>
      <span>{c.role_ko}{c.no != null ? ` · #${c.no}` : ""}{c.injured ? " · 결장" : ""}</span>
      {armband === c.name && <em className="net-wear">오늘 완장</em>}
    </button>
  );
}

function InfluenceMap({ d, accent }: { d: NetworkData; accent: string }) {
  const peek = usePeek();
  const W = 400, H = 400, cx = W / 2, cy = H / 2;
  const core = [...d.leadership.core];
  const rest = d.players.filter((p) => !core.some((c) => c.name === p.name))
    .map((p) => ({ ...p, influence: d.leadership.influence[p.name] ?? 0 }))
    .sort((a, b) => b.influence - a.influence).slice(0, 8);
  const all = [...core, ...rest] as (NetCore | (typeof rest)[number])[];
  const rings = [{ r: 68, n: 3, s: 22 }, { r: 124, n: 6, s: 17 }, { r: 176, n: 99, s: 13 }];
  const placed: { p: (typeof all)[number]; x: number; y: number; s: number }[] = [];
  let k = 0;
  rings.forEach((rg, ri) => {
    const take = all.slice(k, k + rg.n);
    k += take.length;
    take.forEach((p, i) => {
      const a = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(1, take.length) + ri * 0.45;
      placed.push({ p, x: cx + rg.r * Math.cos(a), y: cy + rg.r * Math.sin(a), s: rg.s });
    });
  });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="net-svg" role="img" aria-label="영향력 지도 — 가운데일수록 영향력이 크다">
      {rings.map((rg, i) => (
        <g key={i}>
          <circle cx={cx} cy={cy} r={rg.r} fill="none" stroke={hexA("#ffffff", 0.07 - i * 0.015)} strokeDasharray={i ? "3 5" : undefined} />
          <text x={cx - rg.r * 0.707 + 4} y={cy + rg.r * 0.707 + 3} textAnchor="end" fontSize="8.5" fill={hexA("#ffffff", 0.32)} letterSpacing="1.5">
            {["CORE", "INNER", "OUTER"][i]}
          </text>
        </g>
      ))}
      {placed.slice(0, 3).map((q, i) => (
        <line key={i} x1={cx} y1={cy} x2={q.x} y2={q.y} stroke={hexA(accent, 0.35)} strokeWidth={1.2} />
      ))}
      {d.logo ? <image href={d.logo} x={cx - 22} y={cy - 22} width={44} height={44} preserveAspectRatio="xMidYMid meet" />
        : <circle cx={cx} cy={cy} r={18} fill={hexA(accent, 0.4)} />}
      {placed.map((q) => {
        const cap = q.p.captain_rank;
        return (
          <SvgAvatar key={q.p.name} x={q.x} y={q.y} r={q.s} photo={q.p.photo} name={`${q.p.name} · 영향력 ${q.p.influence}`}
            ring={cap ? "#f6c945" : LINE_COLOR[q.p.line] || "#8a94a8"} ringW={cap ? 3 : 2}
            onClick={(e) => peek(e, { name: q.p.name, club: d.team, hint: { photo: q.p.photo, ovr: q.p.ovr ?? undefined, pos: q.p.pos } })}>
            {cap ? <g transform={`translate(${q.s * 0.72},${-q.s * 0.72})`}>
              <circle r={7.5} fill="#f6c945" /><text textAnchor="middle" dy="0.35em" fontSize="7.5" fontWeight={800} fill="#151515">
                {cap === 1 ? "C" : cap === 2 ? "VC" : `${cap}C`}</text></g> : null}
            <text y={q.s + 11} textAnchor="middle" fontSize="9.5" fill={hexA("#ffffff", 0.82)} style={{ pointerEvents: "none" }}>
              {lastName(q.p.name)}</text>
          </SvgAvatar>
        );
      })}
    </svg>
  );
}

export default function NetLeadership({ d, accent }: { d: NetworkData; accent: string }) {
  const peek = usePeek();
  const caps = d.leadership.captains;
  const main = caps[0];
  const arm = d.leadership.armband;
  return (
    <div className="net-lead">
      <div className="net-lead-l">
        <h4 className="net-h">ARMBAND <span>주장단 · Wikipedia 스쿼드 표</span></h4>
        {main ? <CaptainHero c={main} team={d.team} accent={accent} armband={arm} />
          : <p className="net-empty">위키 스쿼드 표에 주장 표시가 없는 팀입니다 — 오른쪽 영향력 지도로 리더 그룹을 봅니다.</p>}
        {caps.length > 1 && <div className="net-cap-row">{caps.slice(1).map((c) => <CapMini key={c.name} c={c} team={d.team} armband={arm} />)}</div>}
        {main && arm && arm !== main.name && (
          <div className="net-alert">© 지금 완장은 <b>{arm}</b> — 주장 {main.name} 결장</div>
        )}
      </div>
      <div className="net-lead-r">
        <h4 className="net-h">INFLUENCE MAP <span>가운데일수록 영향력 큼 · 금색 테두리 = 주장단</span></h4>
        <InfluenceMap d={d} accent={accent} />
      </div>
      <div className="net-core">
        <h4 className="net-h">LEADERSHIP CORE <span>출전 비중 28 · 연결 중심성 24 · 근속 16 · 완장 12 · 경험 10 · 대표팀 10</span></h4>
        <p className="net-note" style={{ fontSize: 11, color: "var(--muted-2)", marginTop: -4 }} title={INF_NOTE}>
          오른쪽 숫자 = 영향력 0~100 · 팀 안 상대값(위 비중으로 합산, 100 = 모든 요소 만점)
        </p>
        {d.leadership.core.map((c, i) => (
          <button key={c.name} className="net-core-row hoverable"
            onClick={(e) => peek(e, { name: c.name, club: d.team, hint: { photo: c.photo, ovr: c.ovr ?? undefined, pos: c.pos } })}>
            <span className="net-rank">{i + 1}</span>
            {c.photo ? <img src={c.photo} alt="" /> : <span className="net-cap-ph sm" />}
            <span className="net-core-name"><b>{c.name}</b><em>{c.pos}{c.captain_rank ? ` · ${["", "주장", "부주장", "3번째 주장", "4번째 주장"][c.captain_rank]}` : ""}</em></span>
            <span className="net-comp">
              {COMP.map(([k, l]) => (
                <span key={k} title={`${l} ${Math.round((c.components[k] ?? 0) * 100)}`}>
                  <i style={{ height: `${Math.max(6, (c.components[k] ?? 0) * 100)}%`, background: k === "armband" ? "#f6c945" : accent }} />
                  <em>{l}</em>
                </span>
              ))}
            </span>
            <span className="net-why">{c.why.slice(0, 3).map((w) => <i key={w}>{w}</i>)}</span>
            <span className="net-inf" title={`영향력 ${c.influence} / 100 — ${INF_NOTE}`}><b>{c.influence}</b><i style={{ width: `${c.influence}%`, background: accent }} /></span>
          </button>
        ))}
      </div>
    </div>
  );
}
