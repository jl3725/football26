"use client";
import { useEffect, useState } from "react";
import { getNews, type News } from "@/lib/api";

export default function NewsTab({ team, accent }: { team: string; accent: string }) {
  const [data, setData] = useState<News | null>(null);
  useEffect(() => { let a = true; getNews(team).then((d) => a && setData(d)).catch(() => {}); return () => { a = false; }; }, [team]);
  if (!data) return <div className="loading">불러오는 중…</div>;
  if (data.articles.length === 0)
    return <div className="placeholder"><div className="ph-icon">📰</div><div className="ph-title">뉴스 없음</div><div className="ph-sub">이 구단의 최근 기사가 아직 없습니다</div></div>;

  return (
    <div className="fade">
      {data.sparse && <div className="season-note" style={{ marginTop: 0, marginBottom: 14 }}>이 팀 전용 기사가 적어 표시가 제한적일 수 있습니다.</div>}
      <div className="news-grid">
        {data.articles.map((a, i) => (
          <a className="news-card" key={i} href={a.link} target="_blank" rel="noreferrer">
            {a.image
              ? <div className="news-img" style={{ backgroundImage: `url(${a.image})` }} />
              : <div className="news-img noimg">📰</div>}
            <div className="news-body">
              <div className="news-src">
                {a.is_new && <span className="news-new" style={{ background: accent }}>NEW</span>}
                {a.source} · {a.published?.slice(0, 10)}
              </div>
              <div className="news-head">{a.headline}</div>
              {a.headline_en && a.headline_en !== a.headline && <div className="news-head-en">{a.headline_en}</div>}
              {a.descr && <div className="news-desc">{a.descr}</div>}
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}
