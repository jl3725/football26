"use client";
import type { Transfer } from "@/lib/api";

// 자동 슬라이드 이적 티커 — IN/OUT 최근 영입·방출을 한 줄로 흐르게.
export default function TransferTicker({ tin, tout, accent, label = "TRANSFERS" }: { tin: Transfer[]; tout: Transfer[]; accent: string; label?: string }) {
  const items = [
    ...tin.slice(0, 8).map((x) => ({ ...x, dir: "in" as const })),
    ...tout.slice(0, 6).map((x) => ({ ...x, dir: "out" as const })),
  ].filter((x) => x.fee_text && x.fee_text !== "-" && !x.fee_text.toLowerCase().includes("loan"));

  if (items.length === 0) return null;
  const track = [...items, ...items]; // 매끄러운 루프용 2배 트랙

  return (
    <div className="ticker">
      <div className="ticker-label" style={{ background: accent }}>{label}</div>
      <div className="ticker-mask">
        <div className="ticker-track" style={{ animationDuration: `${Math.max(18, items.length * 4)}s` }}>
          {track.map((x, i) => (
            <span className="tk-item" key={i}>
              <span className={`tk-ar ${x.dir}`}>{x.dir === "in" ? "▲" : "▼"}</span>
              <b>{x.player}</b>
              <span className="tk-club">{x.dir === "in" ? "←" : "→"} {x.club}</span>
              <span className="tk-fee" style={{ color: x.dir === "in" ? "#4fc27f" : "#e07070" }}>{x.fee_text}</span>
              <span className="tk-dot">·</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
