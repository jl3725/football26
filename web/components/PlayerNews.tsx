"use client";
import { useEffect, useState } from "react";
import { getPlayerNews, type PlayerNewsItem } from "@/lib/api";
import EnOriginal from "./EnOriginal";

// IN THE NEWS — 이 선수가 나온 최근 기사(뉴스 선수 태그: 이름 전체, 또는 성 + 같은 기사 속 클럽 이름).
export default function PlayerNews({ player, club }: { player: string; club: string }) {
  const [items, setItems] = useState<PlayerNewsItem[] | null>(null);
  const [total, setTotal] = useState(0);
  useEffect(() => {
    let a = true; setItems(null);
    getPlayerNews(player, club).then((d) => { if (a) { setItems(d.articles); setTotal(d.total ?? d.articles.length); } }).catch(() => a && setItems([]));
    return () => { a = false; };
  }, [player, club]);
  if (!items || items.length === 0) return null;
  return (
    <div className="pd-news">
      <div className="pd-sim-title">IN THE NEWS <span style={{ opacity: 0.6, fontWeight: 400, fontSize: 11, letterSpacing: 0 }}>{total > items.length ? `최근 ${items.length}/${total}건` : `${items.length}건`}</span></div>
      <ul>
        {items.map((n) => (
          <li key={n.link}>
            <a href={n.link} target="_blank" rel="noreferrer" title={n.headline_en || undefined}>{n.headline}</a>
            {/* 원제 — 기계 번역이 승패·주어를 뒤집을 때가 있어(아스날 승리 → '선더랜드에게 승리') 대조용, EN 칩을 누르면 펼침 */}
            <EnOriginal text={n.headline_en} ko={n.headline} />
            <span>{n.source}{n.published ? ` · ${n.published.slice(5, 10).replace("-", "/")}` : ""}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
