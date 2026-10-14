// 경기 카드·매치 프리뷰 공용 계산(화면 문구) — 데이터는 /api/fixtures(src/match_center.py).
import type { Fixture, FixtureSide } from "./api";

export const BIG = 35;   // 빅매치 기준 점수(서버 BIG_MIN 과 같음)

const LG_KO: Record<string, string> = {
  EPL: "EPL", LaLiga: "라리가", SerieA: "세리에 A", Bundesliga: "분데스리가", Ligue1: "리그 1",
  LigaPortugal: "포르투갈", Eredivisie: "에레디비시", BelgianProLeague: "벨기에",
};
export const lgKo = (lg?: string | null) => (lg && LG_KO[lg]) || "";

export const ddayLabel = (d: number) => (d <= 0 ? "오늘" : d === 1 ? "내일" : `D-${d}`);

// '10/15(목) 04:00' → 날짜·시각
export function splitKst(kst: string) {
  const [date = "", time = ""] = String(kst || "").split(" ");
  return { date, time };
}

export function compTone(code: string): "ucl" | "uel" | "neutral" {
  if (code === "uefa.champions") return "ucl";
  if (code === "uefa.europa" || code === "uefa.europa.conf") return "uel";
  return "neutral";
}

// 리그 경기는 '리그' 대신 리그 이름으로
export function compLabel(m: Fixture): string {
  if (m.comp_code.endsWith(".1")) return lgKo(m.home.league) || lgKo(m.away.league) || m.comp;
  return m.comp;
}

// 다른 리그 팀끼리면 '라리가 1위', 같은 리그면 '1위'
export function rankLabel(s: FixtureSide, other: FixtureSide): string {
  if (!s.rank) return "";
  return s.league && other.league && s.league !== other.league ? `${lgKo(s.league)} ${s.rank}위` : `${s.rank}위`;
}

// '왜 빅매치?' 한 줄 — 서버 점수(big_score)의 근거를 사람 말로
// short: 카드처럼 순위가 이미 팀 이름 아래 보이면 순위 대결은 빼고 나머지만
export function whyBig(m: Fixture, short = false): string {
  const h = m.home, a = m.away, parts: string[] = [];
  if (h.rank && a.rank && !short) parts.push(`${rankLabel(h, a)} vs ${rankLabel(a, h)}`);
  if (h.ovr && a.ovr) {
    const lo = Math.min(h.ovr, a.ovr);
    parts.push(lo >= 84 ? `두 팀 모두 OVR ${lo}+` : `전력 차 ${Math.abs(h.ovr - a.ovr)}`);
  }
  for (const t of m.tags) if (t !== "강팀 대결" && !parts.includes(t)) parts.push(t);
  return parts.join(" · ");
}

// 팀 OVR 비율(4제곱 — 차이를 눈에 보이게)
export function powerShare(m: Fixture): number | null {
  const ho = m.home.ovr, ao = m.away.ovr;
  return ho && ao ? Math.round((ho ** 4 / (ho ** 4 + ao ** 4)) * 100) : null;
}

const rgb = (h: string) => { const x = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(x.slice(i, i + 2), 16) || 0); };

// 두 팀 색이 비슷하면(노팅엄·아스날 모두 빨강) 원정 쪽을 중립색으로
export function colorsClose(a: string, b: string): boolean {
  const [p, q] = [rgb(a), rgb(b)];
  return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]) < 90;
}

// 어두운 팀 색(PSG 남색 등)은 어두운 배경에서 안 보여 밝힌다
export function liftHex(hex: string, k = 0.38): string {
  if (!/^#?[0-9a-f]{6}$/i.test(hex)) return hex;
  let [r, g, b] = rgb(hex);
  if ((0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.34) {
    r = Math.round(r + (255 - r) * k); g = Math.round(g + (255 - g) * k); b = Math.round(b + (255 - b) * k);
  }
  return `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

// 최근 결과 연속 — 오래된 → 최근 순서
export function streak(form: string[], r: "W" | "L"): number {
  let n = 0;
  for (let i = form.length - 1; i >= 0 && form[i] === r; i--) n++;
  return n;
}
