"use client";
import { useEffect, useState } from "react";
import { getCalendar, type CalEvent, type Context } from "@/lib/api";

function daysBetween(a: Date, b: Date) {
  return Math.round((b.getTime() - a.getTime()) / 86400000);
}

export default function StatusBar({ accent, ctx }: { accent: string; ctx: Context | null }) {
  const [now, setNow] = useState<Date | null>(null);
  const [events, setEvents] = useState<CalEvent[]>([]);

  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 1000);
    getCalendar().then((d) => setEvents(d.events)).catch(() => {});
    return () => clearInterval(t);
  }, []);

  const today = now ?? new Date();
  const chips = events.map((e) => {
    const s = new Date(e.start), en = new Date(e.end);
    const total = Math.max(1, daysBetween(s, en));
    if (today >= s && today <= en) {
      const pct = Math.round((daysBetween(s, today) / total) * 100);
      return { ...e, state: "live" as const, pct };
    }
    if (today < s) return { ...e, state: "soon" as const, dday: daysBetween(today, s) };
    return { ...e, state: "past" as const };
  }).filter((c) => c.state !== "past").slice(0, 2);

  const timeStr = now ? now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "--:--:--";
  const dateStr = now ? now.toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric", weekday: "short" }) : "";

  return (
    <div className="statusbar">
      <div className="sb-clock">
        <span className="livedot" />
        <span className="teko sb-time">{timeStr}</span>
        <span className="sb-date">{dateStr}</span>
      </div>
      {ctx && (
        <div className="sb-season">
          <span className="sb-season-done">{ctx.data_season} 시즌 종료</span>
          {ctx.window.is_open
            ? <span className="sb-season-open" style={{ background: accent }}>{ctx.window.label} {ctx.window.kr} 이적시장 OPEN</span>
            : <span className="sb-season-closed">이적시장 마감</span>}
        </div>
      )}
      <div className="sb-events">
        {chips.map((c, i) => (
          <div className="sb-chip" key={i} style={c.state === "live" ? { borderColor: accent } : undefined}>
            <span className="sb-ico">{c.icon || "📅"}</span>
            <div className="sb-chip-body">
              <div className="sb-chip-name">{c.name}</div>
              {c.state === "live" ? (
                <div className="sb-prog"><span style={{ width: `${c.pct}%`, background: accent }} /></div>
              ) : (
                <div className="sb-dday">D-{c.dday}</div>
              )}
            </div>
            {c.state === "live" && <span className="sb-livetag" style={{ color: accent }}>LIVE</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
