// AI 요약 한 칸 — 경기 리뷰 · 팀 뉴스 · WEEKLY DIGEST 공용(src/ai_notes.py, Gemini 무료 등급).
// 배치가 만들 때 숫자·영문 이름을 원자료와 대조해 통과한 문장만 내려온다 — 없으면 아무것도 안 그린다(규칙 기반 화면 그대로).
// 머리줄은 '이름 · 몇 시간 전'만, 검증 방식은 ⓘ 로(2026-10-21 '글이 너무 많다'). clamp = 긴 서술을 N줄만 보이고 '더 보기'.
import Info from "./Info";
import Clamp from "./Clamp";

const ago = (iso?: string) => {
  if (!iso) return "";
  const h = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 3.6e6));
  return h < 1 ? "방금" : h < 24 ? `${h}시간 전` : `${Math.round(h / 24)}일 전`;
};

const BODY = { fontSize: 14, lineHeight: 1.6, color: "var(--txt)", wordBreak: "keep-all", overflowWrap: "anywhere" } as const;

export default function AiNote({ text, lines, at, label = "AI SUMMARY", sub, check = "숫자·이름 원자료 대조", clamp }: {
  text?: string; lines?: string[]; at?: string; label?: string; sub?: string; check?: string; clamp?: number;
}) {
  if (!text && !lines?.length) return null;
  return (
    <div className="ai-note">
      <div className="ai-note-h">
        <b>{label}</b>
        <span>{sub ?? "AI 요약"}{at ? ` · ${ago(at)}` : ""}
          <Info label="AI 요약 검증">
            <p>AI 가 쓴 요약입니다.</p>
            <p>검증: {check} — 원자료와 맞는 문장만 보여 줍니다.</p>
          </Info>
        </span>
      </div>
      {text && (clamp ? <Clamp text={text} lines={clamp} style={BODY} /> : <p>{text}</p>)}
      {lines && lines.length > 0 && <ul>{lines.map((l) => <li key={l}>{l}</li>)}</ul>}
    </div>
  );
}
