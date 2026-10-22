// 리그 등록부 — 화면의 리그 목록·이름·코드는 모두 여기 한 곳. 새 리그는 이 배열에 한 줄(백엔드는 src/leagues.py).
// 예전엔 사이드바·홈·검색·영입 풀·경기 카드가 리그 표를 저마다 들고 있어 리그 하나 추가에 파일 8개를 고쳤다(2026-10-22 1단계 확장).
//   tier: S 빅5 · A 유럽 강호 · TALENT 원석 발굴(셀링·유망주 공급) — 사이드바 묶음 순서
//   lite: 클라우드 수집만(FotMob·TM) — 일정 event_id 가 FotMob id 라 ESPN 라이브 스코어를 붙이지 않는다
export type LeagueInfo = {
  key: string;          // 백엔드 리그 키
  name: string;         // 'Premier League' — 사이드바 제목·출신 리그
  label: string;        // 'EPL' — 대문자 짧은 이름(탭·홈 라벨)
  short: string;        // 'La Liga' — 리그 선택 목록
  abbr: string;         // 검색 결과 배지
  ko: string;           // 경기 카드 한글
  flag: string;
  espn: string;         // 리그 경기 comp_code(ESPN 표기)
  team: string;         // 리그를 고르면 먼저 여는 팀
  tier: "S" | "A" | "TALENT";
  lite?: boolean;
  soon?: boolean;       // 준비 중(흐리게, 선택 불가)
};

export const LEAGUE_LIST: LeagueInfo[] = [
  { key: "EPL", name: "Premier League", label: "EPL", short: "EPL", abbr: "EPL", ko: "EPL", flag: "🏴", espn: "eng.1", team: "Arsenal", tier: "S" },
  { key: "LaLiga", name: "La Liga", label: "LA LIGA", short: "La Liga", abbr: "LaLiga", ko: "라리가", flag: "🇪🇸", espn: "esp.1", team: "Barcelona", tier: "S" },
  { key: "SerieA", name: "Serie A", label: "SERIE A", short: "Serie A", abbr: "Serie A", ko: "세리에 A", flag: "🇮🇹", espn: "ita.1", team: "Inter", tier: "S" },
  { key: "Bundesliga", name: "Bundesliga", label: "BUNDESLIGA", short: "Bundesliga", abbr: "Bundes", ko: "분데스리가", flag: "🇩🇪", espn: "ger.1", team: "Bayern Munich", tier: "S" },
  { key: "Ligue1", name: "Ligue 1", label: "LIGUE 1", short: "Ligue 1", abbr: "Ligue 1", ko: "리그 1", flag: "🇫🇷", espn: "fra.1", team: "PSG", tier: "S" },
  { key: "Eredivisie", name: "Eredivisie", label: "EREDIVISIE", short: "Eredivisie", abbr: "Erediv.", ko: "에레디비시", flag: "🇳🇱", espn: "ned.1", team: "PSV", tier: "A" },
  { key: "LigaPortugal", name: "Liga Portugal", label: "LIGA PORTUGAL", short: "Liga Portugal", abbr: "Liga POR", ko: "포르투갈", flag: "🇵🇹", espn: "por.1", team: "Sporting CP", tier: "A" },
  { key: "Championship", name: "EFL Championship", label: "CHAMPIONSHIP", short: "Championship", abbr: "Champ.", ko: "챔피언십", flag: "🏴", espn: "eng.2", team: "West Ham United", tier: "A", lite: true },
  { key: "SuperLig", name: "Süper Lig", label: "SÜPER LIG", short: "Süper Lig", abbr: "Süper Lig", ko: "쉬페르리그", flag: "🇹🇷", espn: "tur.1", team: "Galatasaray", tier: "A", lite: true },
  { key: "BelgianProLeague", name: "Belgian Pro League", label: "BELGIUM", short: "Belgian Pro", abbr: "Belg.", ko: "벨기에", flag: "🇧🇪", espn: "bel.1", team: "Club Brugge", tier: "TALENT" },
  { key: "AustrianBundesliga", name: "Austrian Bundesliga", label: "AUSTRIA", short: "Austria", abbr: "Austria", ko: "오스트리아", flag: "🇦🇹", espn: "aut.1", team: "Salzburg", tier: "TALENT", lite: true },
  { key: "DanishSuperliga", name: "Danish Superliga", label: "DENMARK", short: "Denmark", abbr: "Denmark", ko: "덴마크", flag: "🇩🇰", espn: "den.1", team: "FC København", tier: "TALENT", lite: true },
  { key: "SwissSuperLeague", name: "Swiss Super League", label: "SWITZERLAND", short: "Switzerland", abbr: "Swiss", ko: "스위스", flag: "🇨🇭", espn: "sui.1", team: "Young Boys", tier: "TALENT", lite: true },
  { key: "Brazil", name: "Brasileirão", label: "BRAZIL", short: "Brazil", abbr: "Brazil", ko: "브라질", flag: "🇧🇷", espn: "bra.1", team: "", tier: "TALENT", soon: true },
  { key: "Argentina", name: "Liga Profesional", label: "ARGENTINA", short: "Argentina", abbr: "Argentina", ko: "아르헨티나", flag: "🇦🇷", espn: "arg.1", team: "", tier: "TALENT", soon: true },
];

export const LEAGUES_ACTIVE = LEAGUE_LIST.filter((l) => !l.soon);
const BY_KEY = new Map(LEAGUE_LIST.map((l) => [l.key, l]));
const BY_CODE = new Map(LEAGUES_ACTIVE.map((l) => [l.espn, l.key]));

export const leagueInfo = (k?: string | null): LeagueInfo | undefined => (k ? BY_KEY.get(k) : undefined);
export const leagueName = (k?: string | null) => leagueInfo(k)?.name ?? "Premier League";
export const leagueLabel = (k?: string | null) => leagueInfo(k)?.label ?? "EPL";
export const leagueOfCode = (code?: string | null) => (code ? BY_CODE.get(code) : undefined);
// 리그 경기 대회 코드인가 — 예전 `endsWith(".1")` 은 2부 리그(eng.2 챔피언십)를 컵으로 봤다
export const isLeagueCode = (code?: string | null) => !!leagueOfCode(code);
export const DEFAULT_TEAM: Record<string, string> = Object.fromEntries(LEAGUES_ACTIVE.map((l) => [l.key, l.team]));
export const LEAGUE_TABS = LEAGUES_ACTIVE.map((l) => ({ key: l.key, label: l.label }));
export const TIER_LABEL: Record<LeagueInfo["tier"], string> = { S: "TIER S · 빅5", A: "TIER A · 유럽 강호", TALENT: "TALENT · 원석 발굴" };
