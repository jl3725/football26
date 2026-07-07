"use client";
import { useEffect, useState } from "react";
import ScoutChat from "./ScoutChat";
import { hexA } from "@/lib/ui";

// 전역 AI 어시스턴트 — 우하단 플로팅 버블 → 우측 슬라이드 드로어.
// 어느 탭/팀을 보든 접근(컨텍스트=현재 팀). ScoutChat 은 계속 마운트되어 대화 유지.
export default function ScoutDock({ team, league, accent, onNavigate }:
  { team: string; league: string; accent: string; onNavigate?: (t: string, l?: string) => void }) {
  const [open, setOpen] = useState(false);
  // ⌘K / Ctrl+K 로 토글
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen((o) => !o); }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);
  const nav = (t: string, l?: string) => { onNavigate?.(t, l); setOpen(false); };

  return (
    <>
      {/* 백드롭 */}
      <div onClick={() => setOpen(false)} style={{
        position: "fixed", inset: 0, zIndex: 55, background: "rgba(0,0,0,0.35)",
        opacity: open ? 1 : 0, pointerEvents: open ? "auto" : "none", transition: "opacity .25s",
      }} />

      {/* 드로어 */}
      <aside style={{
        position: "fixed", top: 0, right: 0, height: "100vh", width: "min(430px, 100vw)", zIndex: 58,
        background: "rgba(14,14,20,0.98)", backdropFilter: "blur(10px)",
        borderLeft: `1px solid ${hexA(accent, 0.3)}`, boxShadow: "-10px 0 40px rgba(0,0,0,0.45)",
        transform: open ? "translateX(0)" : "translateX(103%)", transition: "transform .26s ease",
        display: "flex", flexDirection: "column",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "13px 16px", borderBottom: `1px solid ${hexA(accent, 0.2)}` }}>
          <b style={{ fontSize: 14 }}>💬 Ask Scout <span style={{ fontWeight: 400, opacity: 0.5, fontSize: 11 }}>· Chief Scout</span></b>
          <button onClick={() => setOpen(false)} title="닫기 (Esc)" style={{
            border: "none", background: hexA("#ffffff", 0.08), color: "inherit", cursor: "pointer",
            width: 28, height: 28, borderRadius: 8, fontSize: 14 }}>✕</button>
        </div>
        <div style={{ flex: 1, minHeight: 0, padding: "6px 14px 14px", display: "flex", flexDirection: "column" }}>
          {open && <ScoutChat team={team} league={league} accent={accent} onNavigate={nav} embedded />}
        </div>
      </aside>

      {/* 플로팅 버블 (FAB) */}
      <button onClick={() => setOpen((o) => !o)} title="Ask Scout (⌘K)" style={{
        position: "fixed", right: 22, bottom: 22, zIndex: 60,
        width: 56, height: 56, borderRadius: "50%", border: "none", cursor: "pointer",
        background: `linear-gradient(135deg, ${accent}, ${hexA(accent, 0.75)})`, color: "#0a0a0a",
        fontSize: 22, fontWeight: 800, boxShadow: `0 6px 22px ${hexA(accent, 0.55)}`,
        transition: "transform .15s", transform: open ? "scale(0.9)" : "scale(1)",
      }}>{open ? "✕" : "✨"}</button>
    </>
  );
}
