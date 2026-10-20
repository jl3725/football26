// AI 요약 한 칸 — 경기 리뷰 · 팀 뉴스 · WEEKLY DIGEST 공용(src/ai_notes.py, Gemini 무료 등급).
// 배치가 만들 때 숫자·영문 이름을 원자료와 대조해 통과한 문장만 내려온다 — 없으면 아무것도 안 그린다(규칙 기반 화면 그대로).
const ago = (iso?: string) => {
  if (!iso) return "";
  const h = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 3.6e6));
  return h < 1 ? "방금" : h < 24 ? `${h}시간 전` : `${Math.round(h / 24)}일 전`;
};

export default function AiNote({ text, lines, at, label = "AI SUMMARY", sub, check = "숫자·이름 원자료 대조" }: {
  text?: string; lines?: string[]; at?: string; label?: string; sub?: string; check?: string;
}) {
  if (!text && !lines?.length) return null;
  return (
    <div className="ai-note">
      <div className="ai-note-h">
        <b>{label}</b>
        <span>{sub ?? "AI 요약"} · {check}{at ? ` · ${ago(at)}` : ""}</span>
      </div>
      {text && <p>{text}</p>}
      {lines && lines.length > 0 && <ul>{lines.map((l) => <li key={l}>{l}</li>)}</ul>}
    </div>
  );
}
