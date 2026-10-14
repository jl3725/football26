"use client";
import { useEffect, useRef } from "react";
import Icon from "./Icon";

export const TABS = [
  { key: "overview", label: "Overview", icon: "activity", ready: true },
  { key: "signals", label: "Inbox", icon: "inbox", ready: true },
  { key: "analytics", label: "Analytics", icon: "bars", ready: true },
  { key: "squad", label: "Squad", icon: "users", ready: true },
  { key: "schedule", label: "Schedule", icon: "calendar", ready: true },
  { key: "player", label: "Player", icon: "user", ready: true },
  { key: "transfer", label: "Recruit", icon: "target", ready: true },
  { key: "news", label: "News", icon: "file", ready: true },
] as const;

export type TabKey = (typeof TABS)[number]["key"];

export default function TabBar({
  active, onChange, accent,
}: { active: TabKey; onChange: (k: TabKey) => void; accent: string }) {
  // 모바일에선 탭 줄이 가로 스크롤 — 주소로 바로 연 탭(?tab=news 등)이 화면 밖에 있지 않게 보이는 곳으로
  const bar = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = bar.current?.querySelector<HTMLElement>(".tab.active");
    el?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [active]);
  return (
    <div className="tabbar" role="tablist" aria-label="구단 분석 메뉴" ref={bar}>
      {TABS.map((t) => (
        <button key={t.key}
          className={`tab${active === t.key ? " active" : ""}`}
          onClick={() => onChange(t.key)}
          role="tab"
          aria-selected={active === t.key}
          style={active === t.key ? { ["--tc" as any]: accent } : undefined}>
          <span className="ti" style={{ display: "inline-flex", alignItems: "center" }}>
            <Icon name={t.icon} size={16} color={active === t.key ? accent : "currentColor"} />
          </span>
          <span>{t.label}</span>
        </button>
      ))}
    </div>
  );
}
