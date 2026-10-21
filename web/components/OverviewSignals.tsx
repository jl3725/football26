"use client";
import { useEffect, useState } from "react";
import SectionHead from "./SectionHead";
import { getInbox, type InboxMsg } from "@/lib/api";
import { usePeek } from "./PlayerPeek";

// BRIEFING — Inbox 의 중요도 상위 3건(다음 경기·결장·일정 과밀·핵심 부상…)을 Overview 에도 그대로.
// 예전 SIGNALS 칩은 같은 원천(/api/signals)을 리그 EPL 로 고정해 읽어 다른 리그 팀은 비었고, 시장가치 칩이
// 대부분이라 '지금 무엇이 중요한지'가 안 보였다(2026-10-20 점검). 자세한 목록은 Inbox 탭.
const SHOWN_ABOVE = new Set(["match_next", "congestion"]);
const TONE: Record<string, string> = { good: "#4fc27f", bad: "#e07070", warn: "#e0a53a", info: "#6aa6e0" };

export default function OverviewSignals({ team, accent = "#ff4d5e" }: { team: string; accent?: string }) {
  const [msgs, setMsgs] = useState<InboxMsg[] | null>(null);
  const peek = usePeek();
  // 다음 경기·일정 과밀은 바로 위 THIS WEEK 가 보여 주므로 빼고, 나머지에서 중요도 상위 3건
  useEffect(() => {
    let a = true; setMsgs(null);
    getInbox(team).then((d) => a && setMsgs([...d.messages].filter((m) => !SHOWN_ABOVE.has(m.type)).sort((x, y) => y.prio - x.prio).slice(0, 3)))
      .catch(() => a && setMsgs([]));
    return () => { a = false; };
  }, [team]);
  if (!msgs || msgs.length === 0) return null;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <SectionHead title="BRIEFING" kr="지금 중요한 3가지" meta="자세히는 Inbox"
        info={<>
          <p>Inbox 메시지 중 중요도 상위 3건(결장·핵심 부상 등).</p>
          <p className="muted">다음 경기·일정 과밀은 위 THIS WEEK 에 있어 뺐습니다. 전체 목록은 Inbox 탭.</p>
        </>} />
      <div className="ov-brief">
        {msgs.slice(0, 3).map((m) => (
          <div key={m.id} className={`ov-brief-i${m.action?.kind === "player" ? " peekable" : ""}`} style={{ borderLeftColor: TONE[m.tone] || accent }}
            onClick={m.action?.kind === "player" ? (e) => peek(e, { name: (m.action as { name: string }).name, club: team }) : undefined}>
            <b>{m.icon} {m.title}{m.player ? ` · ${m.player}` : ""}</b>
            <span>{m.detail}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
