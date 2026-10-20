"use client";
import { useEffect, useMemo, useState } from "react";
import { getNews, type Article, type News, type NewsStory } from "@/lib/api";
import AiNote from "./AiNote";
import SectionHead from "./SectionHead";
import { SkelCards } from "./Skeleton";

// 종류·이적 단계 이름 — 영어 위주 + 작은 한글(src/news_classify.py 의 kind·stage)
const KIND: Record<string, [string, string]> = {
  transfer: ["TRANSFER", "이적"], injury: ["INJURY", "부상"], match: ["MATCH", "경기"],
  interview: ["QUOTES", "인터뷰"], official: ["OFFICIAL", "구단 발표"], other: ["NEWS", "기타"],
};
const STAGES = ["interest", "talks", "agreed", "done"] as const;
const STAGE: Record<string, [string, string]> = {
  interest: ["INTEREST", "관심"], talks: ["TALKS", "협상"], agreed: ["AGREED", "합의"], done: ["DONE", "확정"], denied: ["DENIED", "부인"],
};
const md = (d?: string) => (d ? d.slice(5, 10).replace("-", "/") : "");

function KindTag({ k }: { k: string }) {
  const [en, ko] = KIND[k] ?? KIND.other;
  return <span className={`nw-kind k-${k}`} title={ko}>{en}</span>;
}

// 이적 단계 막대 — 관심 → 협상 → 합의 → 확정(부인은 빨간 표시)
function StageMeter({ stage }: { stage: string }) {
  if (!stage) return null;
  if (stage === "denied") return <span className="nw-stage s-denied">DENIED <em>부인</em></span>;
  const at = STAGES.indexOf(stage as (typeof STAGES)[number]);
  return (
    <span className={`nw-stage s-${stage}`} title="관심 → 협상 → 합의 → 확정">
      <span className="nw-meter">{STAGES.map((s, i) => <i key={s} className={i <= at ? "on" : ""} />)}</span>
      {STAGE[stage][0]} <em>{STAGE[stage][1]}</em>
    </span>
  );
}

function StoryCard({ s, byLink }: { s: NewsStory; byLink: Map<string, Article> }) {
  const [open, setOpen] = useState(false);
  const arts = s.links.map((l) => byLink.get(l)).filter(Boolean) as Article[];
  const more = s.sources.length - 4;
  return (
    <div className={`nw-story k-${s.kind}`}>
      <div className="nw-story-top">
        <KindTag k={s.kind} />
        <StageMeter stage={s.stage} />
        <span className="nw-story-n">매체 {s.sources.length}곳</span>
      </div>
      <b className="nw-story-t">{s.title}</b>
      {s.title_en && s.title_en !== s.title && <em className="nw-story-en">{s.title_en}</em>}
      <div className="nw-story-meta">
        {s.first === s.last ? md(s.last) : `${md(s.first)}–${md(s.last)}`} · {s.sources.slice(0, 4).join(" · ")}{more > 0 ? ` 외 ${more}` : ""}
      </div>
      {(s.journalists.length > 0 || s.players.length > 0) && (
        <div className="news-tags">
          {s.journalists.map((j) => <span key={j} className="nw-j" title="기사에 인용된 기자·인사이더">🎙 {j}</span>)}
          {s.players.map((p) => <span key={p}>{p}</span>)}
        </div>
      )}
      <button className="nw-story-more" onClick={() => setOpen(!open)}>{open ? "접기" : `기사 ${arts.length}건 보기`}</button>
      {open && (
        <ul className="nw-story-list">
          {arts.map((a) => (
            <li key={a.link}>
              <a href={a.link} target="_blank" rel="noreferrer">{a.headline}</a>
              <span>{a.source} · {md(a.published)}{a.stage ? ` · ${STAGE[a.stage]?.[1] ?? ""}` : ""}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ArticleCard({ a, accent }: { a: Article; accent: string }) {
  return (
    <a className={`news-card${a.image ? "" : " slim"} k-${a.kind ?? "other"}`} href={a.link} target="_blank" rel="noreferrer">
      {a.image && <div className="news-img" style={{ backgroundImage: `url(${a.image})` }} />}
      <div className="news-body">
        <div className="news-src">
          {a.is_new && <span className="news-new" style={{ background: accent }}>NEW</span>}
          {a.source} · {a.published?.slice(0, 10)}
        </div>
        <div className="nw-tags-row">
          <KindTag k={a.kind ?? "other"} />
          {a.kind === "transfer" && <StageMeter stage={a.stage ?? ""} />}
        </div>
        <div className="news-head">{a.headline}</div>
        {a.headline_en && a.headline_en !== a.headline && <div className="news-head-en">{a.headline_en}</div>}
        {a.descr && <div className="news-desc">{a.descr}</div>}
        {((a.players?.length ?? 0) > 0 || (a.journalists?.length ?? 0) > 0) && (
          <div className="news-tags" title="기사에 나온 이 팀 선수(이름 전체, 또는 성 + 클럽 이름) · 인용된 기자">
            {(a.journalists ?? []).map((j) => <span key={j} className="nw-j">🎙 {j}</span>)}
            {(a.players ?? []).slice(0, 4).map((p) => <span key={p}>{p}</span>)}
          </div>
        )}
      </div>
    </a>
  );
}

export default function NewsTab({ team, accent }: { team: string; accent: string }) {
  const [data, setData] = useState<News | null>(null);
  const [kind, setKind] = useState("all");
  const [src, setSrc] = useState("");
  useEffect(() => {
    let a = true; setData(null); setKind("all"); setSrc("");
    getNews(team).then((d) => a && setData(d)).catch(() => {});
    return () => { a = false; };
  }, [team]);
  const byLink = useMemo(() => new Map((data?.articles ?? []).map((a) => [a.link, a])), [data]);
  if (!data) return <div className="skel-wrap"><SkelCards n={6} cols="repeat(auto-fill, minmax(280px, 1fr))" face={false} /></div>;
  if (data.articles.length === 0)
    return <div className="placeholder"><div className="ph-icon">📰</div><div className="ph-title">뉴스 없음</div><div className="ph-sub">이 구단의 최근 기사가 아직 없습니다</div></div>;

  const kinds = Object.keys(KIND).filter((k) => (data.kinds?.[k] ?? 0) > 0);
  const sources = data.sources ?? [];
  const shown = data.articles.filter((a) => (kind === "all" || (a.kind ?? "other") === kind) && (!src || a.source === src));
  const stories = data.stories ?? [];

  return (
    <div className="fade">
      {data.ai && <AiNote lines={data.ai.lines} at={data.ai.at} label="TODAY'S BRIEF" sub={`최근 48시간 기사 ${data.ai.n ?? ""}건 AI 요약`} />}
      {stories.length > 0 && (
        <>
          <SectionHead title="STORIES" kr="여러 매체가 다룬 이야기" meta={`최근 14일 · ${stories.length}건 · 같은 선수·같은 제목으로 묶음`} />
          <div className="nw-stories">{stories.map((s) => <StoryCard key={s.id} s={s} byLink={byLink} />)}</div>
        </>
      )}
      <SectionHead title="ALL NEWS" kr="전체 기사" meta={`${shown.length}건 · 매체 ${sources.length}곳`} />
      <div className="it-chips nw-filter">
        <button className={kind === "all" ? "on" : ""} onClick={() => setKind("all")}>ALL <em>{data.articles.length}</em></button>
        {kinds.map((k) => (
          <button key={k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>
            {KIND[k][0]} <span className="nw-ko">{KIND[k][1]}</span> <em>{data.kinds?.[k]}</em>
          </button>
        ))}
      </div>
      {sources.length > 1 && (
        <div className="it-chips nw-filter nw-src">
          <span className="nw-lbl">SOURCES</span>
          <button className={!src ? "on" : ""} onClick={() => setSrc("")}>전체</button>
          {sources.slice(0, 12).map((s) => (
            <button key={s.name} className={src === s.name ? "on" : ""} onClick={() => setSrc(src === s.name ? "" : s.name)}>{s.name} <em>{s.n}</em></button>
          ))}
        </div>
      )}
      {data.sparse && <div className="season-note" style={{ marginTop: 0, marginBottom: 14 }}>이 팀 전용 기사가 적어 표시가 제한적일 수 있습니다.</div>}
      {shown.length === 0
        ? <div className="season-note">이 조건의 기사가 없습니다.</div>
        : <div className="news-grid">{shown.map((a) => <ArticleCard key={a.link} a={a} accent={accent} />)}</div>}
    </div>
  );
}
