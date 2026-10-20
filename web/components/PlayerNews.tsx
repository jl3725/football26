"use client";
import { useEffect, useState } from "react";
import { getPlayerNews, type PlayerNewsItem } from "@/lib/api";

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
      <div className="pd-sim-title">IN THE NEWS <span style={{ opacity: 0.6, fontWeight: 400, fontSize: 11, letterSpacing: 0 }}>· 기사에 나온 이름 기준{total > items.length ? ` · 최근 ${items.length}/${total}건` : ""}</span></div>
      <ul>
        {items.map((n) => (
          <li key={n.link}>
            <a href={n.link} target="_blank" rel="noreferrer">{n.headline}</a>
            <span>{n.source}{n.published ? ` · ${n.published.slice(5, 10).replace("-", "/")}` : ""}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
