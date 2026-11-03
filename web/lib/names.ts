// 짧은 이름(성) — 포메이션·벤치·순위·리더·네트워크·TRACKING 등 화면 곳곳이 쓰는 한 곳.
// 예전엔 화면마다 '마지막 낱말'만 떼어 'van Dijk' → 'Dijk', 'Mac Allister' → 'Allister', 'De Bruyne' → 'Bruyne' 였다(2026-10-27 사용자).
//   · 성 앞 낱말(van·de·da·dos·Mac·von·Ben …)은 성에 붙인다 — 첫 낱말(이름)은 빼고('Ben White' → 'White')
//   · 꼬리말(Jr.·II)이 붙은 두 낱말 이름은 그대로('Vinícius Júnior'), 세 낱말 이상이면 앞 성에 꼬리말을 붙인다
//   · 성이 앞에 오는 한국식 표기('Son Heung-min' · 'Kim Min-jae' — 하이픈 뒤 소문자)는 첫 낱말
const PARTICLES = new Set([
  "van", "von", "der", "den", "de", "del", "della", "dello", "degli", "dei", "di", "da", "das", "do", "dos", "du",
  "le", "la", "les", "ter", "ten", "te", "op", "het", "'t", "mac", "mc", "st", "st.", "san", "santa", "bin", "ibn",
  "ben", "al", "el", "ul", "abu", "y", "zu", "vom", "af", "av",
]);
const SUFFIX = new Set(["jr", "jr.", "junior", "júnior", "jnr", "ii", "iii", "iv"]);
const KOREAN_ORDER = /^[A-Z][a-z]+-[a-z]+$/;   // 'Heung-min' · 'Min-jae' · 'Kang-in'

export function surname(name?: string | null): string {
  const n = String(name ?? "").trim();
  if (!n || n === "—") return n;
  const t = n.split(/\s+/);
  if (t.length === 1) return n;
  if (t.length === 2 && KOREAN_ORDER.test(t[1])) return t[0];
  if (SUFFIX.has(t[t.length - 1].toLowerCase())) {
    if (t.length === 2) return n;
    return `${surname(t.slice(0, -1).join(" "))} ${t[t.length - 1]}`;
  }
  let s = t.length - 1;
  while (s - 1 >= 1 && PARTICLES.has(t[s - 1].toLowerCase())) s -= 1;
  return t.slice(s).join(" ");
}

// 짧은 구단 이름 — 좁은 표·차트 라벨. 예전엔 '14자 넘으면 마지막 낱말'이라 'Newcastle United' → 'United',
// 'Manchester City' → 'City' 였다(2026-11-03 팬 관점 점검: 예측 리그 '최근 결과'에 'United 0-1 Everton').
//   · 구단 약어 낱말(FC·AC·AS·SV·VfB·1. …)을 빼고, 그래도 길면 United → Utd, 끝의 흔한 구단 낱말(Hotspur·Albion·Town …)을 뺀다
//   · City 는 그대로(Manchester City 를 'Manchester' 로 줄이면 United 와 헷갈린다), 같이 보이는 구단(ctx)과 겹치면 빼지 않는다
const CLUB_AFFIX = new Set(["FC", "AFC", "CF", "SC", "AC", "AS", "SV", "SS", "US", "CD", "UD", "SD", "CA", "RC", "VfB", "VfL",
  "FK", "BK", "SK", "KV", "1.", "Club"]);
const CLUB_TAIL = new Set(["Town", "Hotspur", "Albion", "Athletic", "Wanderers", "Rovers", "County", "Calcio"]);

export function clubShort(name?: string | null, ctx: (string | null | undefined)[] = [], max = 12): string {
  const n = String(name ?? "").trim();
  const strip = (s: string) => s.split(/\s+/).filter((w) => !CLUB_AFFIX.has(w)).join(" ") || s;
  let base = strip(n);
  if (base.length <= max) return base;
  base = base.replace(/ United$/, " Utd");
  if (base.length <= max) return base;
  const w = base.split(" ");
  if (w.length > 1 && CLUB_TAIL.has(w[w.length - 1])) {
    const cut = w.slice(0, -1).join(" ");
    const clash = ctx.some((o) => o && o !== n && (strip(String(o)) === cut || strip(String(o)).startsWith(`${cut} `)));
    if (!clash) return cut;
  }
  return base;
}
