"use client";
import { useEffect, useState } from "react";
import SectionHead from "./SectionHead";
import { getCaptains, type Captain } from "@/lib/api";
import { usePeek } from "./PlayerPeek";

// Overview LEADERSHIP — 주장단(위키백과 스쿼드 표: 주장·부주장·3·4번째, 8개 리그). 주장이 결장하면 완장을 찬 선수를 표시.
// 깊은 내용(영향력 지도·리더십 코어)은 NETWORK 탭. 예전엔 EPL 만, '더 보기' 안에 숨어 있었다(2026-10-15).
const LABEL: Record<number, string> = { 1: "C", 2: "VC", 3: "3C", 4: "4C", 5: "5C", 6: "6C" };

export default function CaptainBoard({ team, accent }: { team: string; accent: string }) {
  const peek = usePeek();
  const [caps, setCaps] = useState<Captain[]>([]);
  const [src, setSrc] = useState<string | undefined>();
  useEffect(() => {
    let a = true;
    setCaps([]);
    getCaptains(team).then((d) => { if (a) { setCaps(d.captains); setSrc(d.source); } }).catch(() => {});
    return () => { a = false; };
  }, [team]);
  if (caps.length === 0) return null;
  const main = caps.find((c) => c.is_main) ?? caps[0];
  const rest = caps.filter((c) => c !== main);
  const wearing = main.injured ? rest.find((c) => !c.injured)?.name : main.name;

  return (
    <div className="card" style={{ marginTop: 16, ["--ac" as string]: accent }}>
      <SectionHead title="LEADERSHIP" kr="주장단"
        meta={src === "wikipedia" ? "Wikipedia 스쿼드 표 · 영향력 지도는 NETWORK 탭" : "공식 주장 · 경기 기록"} />
      <div className="lead-strip">
        <button className={`net-cap-hero hoverable${main.injured ? " off" : ""}`}
          onClick={(e) => peek(e, { name: main.name, club: team, hint: { photo: main.photo, ovr: main.ovr ?? undefined, pos: main.pos } })}>
          {main.no != null && <span className="net-cap-no">{main.no}</span>}
          {main.photo ? <img src={main.photo} alt="" /> : <span className="net-cap-ph" />}
          <span className="net-band">C</span>
          <div className="net-cap-txt">
            <em>CAPTAIN · 주장</em>
            <b>{main.name}</b>
            <span>{[main.pos, main.ovr ? `OVR ${main.ovr}` : ""].filter(Boolean).join(" · ")}</span>
            {main.injured && <div className="net-chips"><i className="bad">결장 — 완장: {wearing ?? "미정"}</i></div>}
          </div>
        </button>
        {rest.map((c) => (
          <button key={c.name} className={`net-cap-mini hoverable${wearing === c.name ? " wearing" : ""}`}
            onClick={(e) => peek(e, { name: c.name, club: team, hint: { photo: c.photo, ovr: c.ovr ?? undefined, pos: c.pos } })}>
            <span className="net-band sm">{c.rank ? LABEL[c.rank] : "VC"}</span>
            {c.photo ? <img src={c.photo} alt="" /> : <span className="net-cap-ph sm" />}
            <b>{c.name}</b>
            <span>{c.role}{c.no != null ? ` · #${c.no}` : ""}{c.injured ? " · 결장" : ""}</span>
            {wearing === c.name && <em className="net-wear">오늘 완장</em>}
          </button>
        ))}
      </div>
    </div>
  );
}
