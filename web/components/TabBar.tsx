"use client";

export const TABS = [
  { key: "overview", label: "Overview", icon: "⚡", ready: true },
  { key: "signals", label: "Inbox", icon: "📥", ready: true },
  { key: "analytics", label: "Analytics", icon: "📊", ready: true },
  { key: "squad", label: "Squad", icon: "📋", ready: true },
  { key: "schedule", label: "Schedule", icon: "📅", ready: true },
  { key: "player", label: "Player", icon: "👤", ready: true },
  { key: "database", label: "Database", icon: "🔎", ready: true },
  { key: "transfer", label: "Recruit", icon: "🧭", ready: true },
  { key: "news", label: "News", icon: "📰", ready: true },
] as const;

export type TabKey = (typeof TABS)[number]["key"];

export default function TabBar({
  active, onChange, accent,
}: { active: TabKey; onChange: (k: TabKey) => void; accent: string }) {
  return (
    <div className="tabbar">
      {TABS.map((t) => (
        <button key={t.key}
          className={`tab${active === t.key ? " active" : ""}`}
          onClick={() => onChange(t.key)}
          style={active === t.key ? { ["--tc" as any]: accent } : undefined}>
          <span className="ti">{t.icon}</span>
          <span>{t.label}</span>
        </button>
      ))}
    </div>
  );
}
