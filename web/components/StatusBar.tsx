"use client";
import { useEffect, useState } from "react";
import { getCalendar, getOpsStatus, type CalEvent, type Context, type OpsState } from "@/lib/api";
import { seasonChip } from "@/lib/season";
import { TONE } from "@/lib/meaning";

// DATA 칩 — 수집 에이전트 상태 한 줄 요약(지연 > 일부 실패 > 정상), 누르면 /status
const DATA_CHIP: Record<OpsState, { c: string; t: string }> = {
  late: { c: TONE.bad.c, t: "데이터 지연 있음" }, warn: { c: TONE.weak.c, t: "일부 수집 실패" },
  ok: { c: TONE.best.c, t: "수집 정상" }, nodata: { c: TONE.avg.c, t: "실행 기록 대기" },
};

function daysBetween(a: Date, b: Date) {
  return Math.round((b.getTime() - a.getTime()) / 86400000);
}

export default function StatusBar({ accent, ctx, league = "EPL" }: { accent: string; ctx: Context | null; league?: string }) {
  const [now, setNow] = useState<Date | null>(null);
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [data, setData] = useState<OpsState | null>(null);

  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 15000);   // 분 단위 시계
    getCalendar(league).then((d) => setEvents(d.events)).catch(() => {});
    return () => clearInterval(t);
  }, [league]);
  useEffect(() => {
    getOpsStatus().then((d) => {
      const c = d.counts;
      setData(c.late ? "late" : c.warn ? "warn" : c.ok ? "ok" : "nodata");
    }).catch(() => {});
  }, []);

  const today = now ?? new Date();
  const chips = events.map((e) => {
    // 날짜는 KST 하루로 — 'YYYY-MM-DD' 를 UTC 자정으로 읽어 오늘 밤 챔스 매치데이가 오전 9시에 사라졌다(2026-10-20 점검).
    // 유럽 저녁 경기는 한국 다음 날 아침에 끝나므로 끝 날짜 + 8시간까지 '진행 중'으로 둔다
    const s = new Date(`${e.start.slice(0, 10)}T00:00:00+09:00`);
    const en = new Date(new Date(`${e.end.slice(0, 10)}T23:59:59+09:00`).getTime() + 8 * 3600e3);
    const total = Math.max(1, daysBetween(s, en));
    if (today >= s && today <= en) {
      const pct = Math.round((daysBetween(s, today) / total) * 100);
      return { ...e, state: "live" as const, pct };
    }
    if (today < s) return { ...e, state: "soon" as const, dday: daysBetween(today, s) };
    return { ...e, state: "past" as const };
  }).filter((c) => c.state !== "past").slice(0, 1);   // 가장 가까운 일정 하나만(2026-10-23 글 줄이기)

  // 시:분 · '10/23 금' — 예전엔 초 단위 시계·'2026년 10월 23일 금'까지 모든 화면 맨 위에 99자가 깔렸다
  const timeStr = now ? now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "--:--";
  const dateStr = now ? `${now.getMonth() + 1}/${now.getDate()} ${now.toLocaleDateString("ko-KR", { weekday: "short" })}` : "";

  return (
    <div className="statusbar">
      <div className="sb-clock">
        <span className="livedot" />
        <span className="teko sb-time">{timeStr}</span>
        <span className="sb-date">{dateStr}</span>
      </div>
      {ctx && (
        <div className="sb-season">
          <span className="sb-season-done" title={seasonChip(ctx.window, ctx.data_season)}>{seasonChip(ctx.window, ctx.data_season, true)}</span>
          {/* 이적시장은 열렸을 때만 — '마감'은 대부분의 날에 붙는 기본 상태라 뺐다 */}
          {ctx.window.is_open && <span className="sb-season-open" style={{ background: accent }}>{ctx.window.kr} 이적시장 OPEN</span>}
        </div>
      )}
      {data && (
        <a className="sb-data" href="/status" title={`${DATA_CHIP[data].t} — DATA STATUS 열기`}>
          <i style={{ background: DATA_CHIP[data].c }} />DATA
        </a>
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
