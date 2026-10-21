"use client";
import { useState } from "react";
import type { OvrPart, RatingSources } from "@/lib/api";
import { TONE, ovrBand, ssMeaning } from "@/lib/meaning";
import { MeaningTag } from "./Meaning";
import Info from "./Info";

// OVR 이 어떻게 나왔나 — 시장가치 기준점에서 경기력·나이·포지션 등이 몇 점씩 더해졌는지(src/ratings_v3.ovr_parts_of_row).
// 2026-10-19 사용자: '기준이 어떤 건지 애매할 때가 있다'(Groß 76 · Vušković 84 = Konsa 84). 평점은 Sofascore·FotMob 평균.
// 공식은 ⓘ 로(2026-10-21 '글이 너무 많다') — 화면엔 숫자만(출처별·이전 시즌 평점 포함, 한 줄).
// 접힌 줄 요약은 짧게 — 한글 이름이 길면(예: '어린 선수 몸값의 잠재력 몫 빼기') 영어 약칭으로
const shortName = (p: OvrPart) => {
  const k = p.ko.split(" — ")[0].split("(")[0].trim();
  return k.length > 8 || k.includes("→") ? p.en : k;
};

export default function OvrBreakdown({ ovr, parts, ratings }: { ovr: number; parts?: OvrPart[]; ratings?: RatingSources }) {
  const [open, setOpen] = useState(false);
  if (!parts?.length) return null;
  const base = parts[0];
  const rest = parts.slice(1);
  const top = [...rest].sort((a, b) => Math.abs(b.value) - Math.abs(a.value)).slice(0, 2);
  const r = ratings;
  const fmt = (v: number) => `${v > 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}`;
  return (
    <div className="ob5">
      <button type="button" className="ob5-toggle" onClick={() => setOpen((x) => !x)} aria-expanded={open}>
        <b>OVR 구성</b>
        <span>{shortName(base)} {base.value.toFixed(1)}{top.map((p) => ` · ${shortName(p)} ${fmt(p.value)}`).join("")} → {ovr}</span>
        <i>{open ? "▴" : "▾"}</i>
      </button>
      {open && (
        <div className="ob5-body">
          <div className="ob5-row base"><em>{base.en}</em><span>{base.ko}</span><b>{base.value.toFixed(1)}</b></div>
          {rest.map((p) => (
            <div className="ob5-row" key={p.key}>
              <em>{p.en}</em><span>{p.ko}</span>
              <b style={{ color: p.value > 0 ? TONE.good.c : TONE.weak.c }}>{fmt(p.value)}</b>
            </div>
          ))}
          <div className="ob5-row total"><em>OVR</em>
            <span>{ovrBand(ovr).ko} · {ovrBand(ovr).desc}
              <Info wide label="OVR 계산 방식">
                <p><b>OVR</b> = 시장가치로 정한 기준점 + 경기력·나이·포지션 보정.</p>
                <p>30세 이상은 몸값이 나이로 깎여 실력을 덜 말해 주므로 나이만큼 &apos;평점이 말하는 수준&apos;을 섞고,
                  21세 이하는 출전이 쌓이기 전까지 기준점 쪽으로 당깁니다.</p>
              </Info>
            </span>
            <b>{ovr}</b></div>
          {r && (r.sofascore || r.fotmob) && (
            <div className="ob5-rate">
              <b>평점(경기력 입력)
                <Info wide label="평점 출처">
                  <p><b>이번 시즌</b> = Sofascore · FotMob 평균{r.fotmob != null && r.fotmob_scaled != null ? ` · FotMob ${r.fotmob.toFixed(2)} → 같은 척도 ${r.fotmob_scaled.toFixed(2)}` : ""}</p>
                  <p className="muted">OVR 경기력은 이번·지난·2시즌 전을 출전 시간으로 섞고(오래될수록 덜), 폼은 이번 시즌만</p>
                </Info>
              </b>
              <span>
                이번 시즌 <strong>{r.blend?.toFixed(2) ?? "—"}</strong>{r.blend ? <> <MeaningTag sm m={ssMeaning(r.blend)} /></> : null}
              </span>
              {/* 출처별·이전 시즌 평점은 이 패널을 연 이유라 화면에 그대로(공식만 ⓘ) */}
              <span>
                {[
                  r.sofascore != null ? `Sofascore ${r.sofascore.toFixed(2)}` : null,
                  r.fotmob != null ? `FotMob ${r.fotmob.toFixed(2)}` : null,
                  r.prev_blend ? `지난 시즌 ${r.prev_blend.toFixed(2)}${r.prev_minutes ? ` (${r.prev_minutes.toLocaleString()}분)` : ""}` : null,
                  r.hist ? `2시즌 전 ${r.hist.toFixed(2)}` : null,
                ].filter(Boolean).join(" · ")}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
