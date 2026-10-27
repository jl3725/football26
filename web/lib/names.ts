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
