"use client";
import { useEffect, useRef, useState } from "react";

// OVR 기준표 — 숫자가 무엇을 뜻하는지(등급), 어떻게 계산되는지, 상한이 어디인지. 사용자 요청(2026-10-15 '기준점').
const BANDS: [string, string, string, string][] = [
  ["90+", "WORLD CLASS", "세계 최정상 — 8개 리그 통틀어 10명 안팎", "#f6c945"],
  ["86–89", "ELITE", "빅클럽 핵심 주전 · 대표팀 주축", "#4fc27f"],
  ["82–85", "TOP STARTER", "상위권 팀 주전", "#7fd1d8"],
  ["77–81", "STARTER", "리그 주전급", "#6aa6e0"],
  ["72–76", "ROTATION", "로테이션 · 중하위권 주전", "#8a94a8"],
  ["65–71", "SQUAD", "백업 · 성장 중인 유망주", "#6b7482"],
  ["~64", "FRINGE", "출전이 적거나 검증 전", "#4d5562"],
];

export default function OvrGuide() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  return (
    <div className="ovrg" ref={ref}>
      <button className="ovrg-btn" onClick={() => setOpen((v) => !v)} aria-expanded={open}>OVR GUIDE <span>기준</span></button>
      {open && (
        <div className="ovrg-pop" role="dialog" aria-label="OVR 기준">
          <b className="ovrg-t">OVR SCALE <span>현재 기량(커리어 클래스) · 45~99</span></b>
          {BANDS.map(([r, en, ko, c]) => (
            <div key={r} className="ovrg-row"><i style={{ background: c }} /><em>{r}</em><strong>{en}</strong><span>{ko}</span></div>
          ))}
          <p className="ovrg-p">
            <b>계산</b> 시장가치 기준점 + 포지션(수비 +0.5 · 미드 −0.5) + 경기력(이번·지난 시즌 평점, 리그 보정, ±3.5 상한)
            + 나이(유망주 잠재력 몫 −, 30대 검증 베테랑 +) + 유럽대항전(최대 +0.7).
          </p>
          <p className="ovrg-p">
            <b>상한</b> 88을 넘는 부분은 0.6배로 눌러(90 = 원래 91.3) 계속 잘해도 100을 넘지 않고, 최고 99에서 멈춘다.
            21세 이하는 나이별 천장(19세 92 · 20세 93)이 있다. 폼(FORM)은 이번 시즌 리그 내 순위로 OVR 과 따로 본다.
          </p>
        </div>
      )}
    </div>
  );
}
