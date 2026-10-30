// API 타입 + fetch 헬퍼. next.config rewrites 로 /api/* → FastAPI(8000) 프록시.

export type Team = {
  name: string;
  color: string;
  logo: string;
  rank: number;
  points: number;
};

export type Transfer = {
  player: string;
  club: string;
  fee_eur: number;
  fee_text: string;
  pos: string;
};

// 평점 추이 — ovr_d·form_d: 2주 전 대비(기록 2주치 쌓인 뒤), ovr_prev: 지난 시즌 OVR(300분+)
export type Trend = { ovr_d: number | null; form_d: number | null; ovr_prev: number | null };
// 최근 경기 평점(FotMob, 전 대회) — 선수 화면 LAST 5 막대
export type RecentMatch = { date: string; comp_code: string; opponent: string; home_away: string; minutes: number; rating: number; goals: number; assists: number };
export type RecentForm = { score: number | null; n: number; avg5: number; avg3: number; matches: RecentMatch[] };
export type Star = { trend?: Trend; player: string; pos: string; ovr: number; pot?: number; form?: number | null;
  form_recent?: number | null; recent_avg?: number | null; recent_n?: number | null; rating: number; goals: number; assists: number; photo: string; role?: string; big_match?: boolean };
// source: transfermarkt | fotmob(다음 경기 결장 명단·경기 중 부상 교체 — TM 보다 빠름)
export type Injury = { player: string; injury: string; until: string; pos: string; photo: string; source?: string };
export type Window = {
  season_id: number; window: string; label: string; state: string; is_open: boolean; kr: string | null;
  phase?: "in_season" | "offseason" | "stale"; data_season_id?: number;
};

export type Overview = {
  team: string;
  league: string;
  color: string;
  logo: string;
  fullName: string;
  capacity: number;
  info: { city?: string; stadium?: string; founded?: number; nick?: string; desc?: string; value_rank?: number | null; squad_value?: number };
  standing: {
    rank: number; played: number; won: number; drawn: number; lost: number;
    gf: number; ga: number; gd: number; points: number;
  };
  ovr: { overall: number; attack: number; midfield: number; defense: number; top_xi?: number;
    perf_adj?: Partial<Record<"attack" | "midfield" | "defense", number>>;
    units?: Partial<Record<"attack" | "midfield" | "defense", { player: string; strength: number; injured?: boolean; until?: string }[]>>;
    unit_rank?: Partial<Record<"overall" | "attack" | "midfield" | "defense", { rank: number; n: number }>>;
    record?: { current: TeamRecordRow | null; past: TeamRecordRow[] } };
  ovr_delta?: { overall: number; attack: number; midfield: number; defense: number };
  radar: { axis: string; value: number }[];
  form: string[];
  manager: {
    name: string; nationality: string; style: string; formation: string; appointed: string; focus: string;
    formation_used?: { formation: string; n: number; total: number } | null; formation_pref?: string;   // 실제 최빈 · 위키 선호
    photo?: string; bio?: string; tactics?: string;
    previous?: { name: string; left_date: string };
    changed_at?: string;
  } | null;
  edge: { strengths: { label: string; value: number }[]; weaknesses: { label: string; value: number }[] };
  snapshot: { open_play: number; set_piece: number; penalty: number; yellows: number; reds: number; yellow_per_match: number; source?: string } | null;
  stars: Star[];
  squad_ratings: { player: string; ovr: number; pot: number; form: number | null; age: number; minutes: number; line: string; photo?: string }[];
  age_summary?: { wavg: number; rank_young: number; n: number; league_wavg: number; u23: number; prime: number; vet: number } | null;
  leaders: { label: string; player: string; photo: string; value: number }[];
  leaders_asof?: string | null;   // 골·도움 기준일(FotMob 리그 경기 합 — 경기 20분 뒤 갱신)
  departed: { player: string; left_for: string; pos: string; photo: string }[];
  injuries: Injury[];
  injury_returns?: { player: string; date: string; since: string | null }[];   // TM 미갱신 · 부상 뒤 출전 → 복귀로 봄
  transfers: { in: Transfer[]; out: Transfer[] };
  window: Window;
  data_season: string;
};

export type CalEvent = { name: string; start: string; end: string; icon: string; kind: string };

export type Placement = { slot: string; player: string; x: number; y: number; kind: string; ovr: number | null; photo: string; changed?: boolean; in?: boolean; out?: string; club?: string; injured?: boolean };
// FORMATION 대회 — league · 대회 코드 하나(uefa.champions·eng.league_cup …) · euro·cup(묶음) · all(전 대회) · last(가장 최근 한 경기)
export type LineupComp = "league" | "euro" | "cup" | "all" | "last" | (string & {});
export type Lineup = {
  team: string; color: string;
  season: { formation: string; placements: Placement[]; matches?: number };
  recent: { formation: string; placements: Placement[]; matches?: number } | null;
  bench: { player: string; pos: string; ovr: number; photo: string }[];
  last_match?: { date: string; opponent: string; home_away: string; kind?: string; code?: string; comp?: string } | null;   // 마지막으로 반영된 경기(고른 대회)
  comp?: LineupComp;
  comps?: Partial<Record<"league" | "euro" | "cup", number>>;   // 묶음별 선발 기록 경기 수
  comp_list?: { key: string; kind: "league" | "euro" | "cup"; name: string; n: number }[];   // 대회 하나하나(리그 → 유럽 → 컵)
};

// 응답 상한 — 넘기면 실패로 처리해 화면이 스켈레톤에 영원히 머물지 않게 한다(Render 콜드스타트 ~60s 감안).
const FETCH_TIMEOUT_MS = 70_000;

// 서버 데이터 버전(모델 버전 + DB 빌드 시각) — 바뀌면(배포·데이터 갱신) 오래 들고 있던 캐시를 버린다.
// 예전엔 열어 둔 화면의 선수 DB(선수 카드 OVR)가 배포 뒤에도 옛 값이었다(하베르츠 84 vs 포메이션 83).
let _dataVer = "";
function noteDataVersion(v: string | null) {
  if (!v) return;
  if (_dataVer && v !== _dataVer) _dbCache = null;
  _dataVer = v;
}

async function once<T>(url: string): Promise<T> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(url, { cache: "no-store", signal: ctl.signal });
    if (!res.ok) throw Object.assign(new Error(`${res.status} ${url}`), { status: res.status });
    noteDataVersion(res.headers.get("x-data-version"));
    return res.json();
  } finally {
    clearTimeout(timer);
  }
}

// 서버가 깨는 중·다시 뜨는 중(Render 무료: 잠들면 30~60초, 데이터 커밋마다 재배포)엔 프록시가 502/503/504·연결 끊김·
// 시간 초과를 준다 — 5초 뒤 한 번만 다시. 예전엔 한 번 실패하면 화면이 스켈레톤에 멈췄다(2026-10-25 뉴스 탭 '안 열림').
const transient = (e: unknown) => {
  const s = (e as { status?: number })?.status;
  return s === undefined ? true : s === 502 || s === 503 || s === 504;   // status 없음 = 네트워크 오류·시간 초과
};
async function j<T>(url: string): Promise<T> {
  try {
    return await once<T>(url);
  } catch (e) {
    if (!transient(e)) throw e;
    await new Promise((r) => setTimeout(r, 5000));
    return once<T>(url);
  }
}

// 활성 리그 — 사이드바에서 전환. 아래 모든 fetcher 기본값이 이 값을 참조(호출 시점 평가).
let _league: string = "EPL";
export const setActiveLeague = (l: string) => { _league = l; };
export const activeLeague = (): string => _league;

export const getTeams = (league = _league) =>
  j<Team[]>(`/api/teams?league=${encodeURIComponent(league)}`);

export type NextTeam = { name: string; color: string; logo: string; promoted: boolean };
export type NextSeason = {
  season_label: string; source_title: string; detected_at: string;
  teams: NextTeam[]; promoted: string[]; relegated: string[]; meta_missing: string[];
};
export const getNextTeams = (league = _league) =>
  j<NextSeason>(`/api/teams/next?league=${encodeURIComponent(league)}`);

export const getOverview = (team: string, league = _league) =>
  j<Overview>(`/api/overview/${encodeURIComponent(team)}?league=${encodeURIComponent(league)}`);

// ── 팀 정체성 (감독 전술 블렌드 · 영입 성향 · 예산 프록시) ──
export type Identity = {
  team: string; league: string;
  tactics: {
    manager: string; formation: string | null;
    current_tags: string[]; tendency_tags: string[];
    vector: Record<string, number>;
    role_usage: { role: string; share: number }[];
    tenure: { appointed: string | null; months: number | null; is_new: boolean; w_current: number; w_tendency: number };
  } | null;
  recruitment: {
    age_profile: string; spend_profile: string; profile: string;
    avg_age: number | null; u21_ratio: number | null; u23_ratio: number | null;
    prime_ratio: number | null; veteran_ratio: number | null;
    n_signings: number; avg_fee_eur: number | null;
  } | null;
  budget: {
    spend_tier: string; squad_value_eur: number; net_spend_eur: number; gross_spend_eur: number;
    max_fee_paid_eur: number; price_ceiling_eur: number; value_pct: number;
  } | null;
};
export const getIdentity = (t: string, l = _league) =>
  j<Identity>(`/api/identity/${encodeURIComponent(t)}?league=${encodeURIComponent(l)}`);

// ── Transfer Fit Evaluator (로컬 전용 · Qdrant/Neo4j 필요) ──
export type FitComponents = {
  RoleFit: number; TacticalFit: number; TeamNeed: number; Translation: number;
  Potential: number; Value: number; RecruitFit: number; PriceRealism: number; Risk: number; Euro: number;
};
export type Fit = {
  available: boolean; reason?: string; error?: string;
  candidate: string; club?: string; role: string; natural_role?: string | null; role_note?: string;
  source_league?: string; target_club?: string; target_league?: string;
  base_ovr?: number; proj_ovr?: number;
  components?: FitComponents;
  fit_score?: number; signing_type?: string; risk_level?: string;
  tactical_detail?: {
    current_fit: number; tendency_fit: number; blended: number;
    w_current: number; w_tendency: number; is_new_manager: boolean;
    appointed: string | null; descriptor_tags: string[];
  };
  affordability?: {
    verdict: string; likely_fee_eur: number | null; ceiling_eur: number | null;
    spend_tier?: string; club_recruit_profile?: string; club_avg_signing_age?: number | null;
  };
  manager?: { name: string | null; formation: string | null; style_tags: string[] | null };
  team_need_detail?: { depth: number; best_ss: number | null; avg_age: number | null };
  similar_players?: string[]; euro_experience?: boolean;
  precedent_transfers?: number | null; notes?: string;
};
export const getFit = (candidate: string, club: string, role: string, sourceLeague = "", l = _league) =>
  j<Fit>(`/api/fit?candidate=${encodeURIComponent(candidate)}&club=${encodeURIComponent(club)}`
    + `&role=${encodeURIComponent(role)}&source_league=${encodeURIComponent(sourceLeague)}`
    + `&league=${encodeURIComponent(l)}`);

// ── Manager Change Simulator (로컬 전용) ──
export type SimChange = { axis: string; from: number; to: number; delta: number };
export type SimMisfit = { player: string; role: string; sys_fit: number };
export type SimPriority = { role: string; share: number; depth: number; candidates: string[] };
export type ManagerSim = {
  available: boolean; reason?: string; error?: string;
  target_club?: string; new_manager?: string; new_from_club?: string;
  current?: { manager: string; formation: string | null; style_tags: string[] };
  new?: { manager: string; formation: string | null; style_tags: string[] };
  vector_changes?: SimChange[]; squad_misfit?: SimMisfit[]; priorities?: SimPriority[];
};
export const getManagerSim = (club: string, manager: string, l = _league) =>
  j<ManagerSim>(`/api/managersim?club=${encodeURIComponent(club)}&manager=${encodeURIComponent(manager)}&league=${encodeURIComponent(l)}`);

// ── Ask Scout — 무료: 규칙 라우터(키 없음) 또는 Gemini 무료 등급 · 유료 OpenAI 는 서버가 허용할 때만 ──
// result 는 intent 에 따라 Recommend|Fit|ManagerSim|{results}|Identity 중 하나(느슨하게).
export type Scout = {
  available: boolean; reason?: string; error?: string; auth_required?: boolean;
  intent?: string | null; args?: Record<string, unknown>;
  answer?: string; engine?: "rules" | "gemini" | "openai"; note?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  result?: any;
};
export type ScoutTurn = { role: "user" | "assistant"; content: string };
export const getScout = (q: string, team = "", l = _league, token = "", history: ScoutTurn[] = []) =>
  fetch(`/api/scout`, {
    method: "POST", cache: "no-store",
    headers: { "Content-Type": "application/json", ...(token ? { "X-Scout-Token": token } : {}) },
    body: JSON.stringify({ q, team, league: l, history }),
  }).then((r) => r.json() as Promise<Scout>);

// ── 탭별 타입 ─────────────────────────────
export type SquadPlayer = {
  player: string; pos: string; age: number; minutes: number;
  value_eur: number; ovr: number; photo: string; goals: number; assists: number; trend?: Trend;
  roster_only?: boolean;   // 이번 시즌 출전 없음(TM 스쿼드 명단에서 보강 — 지난 시즌 기록 기준)
  roles?: string[];          // [주포지션, 2포지션, 3포지션] — 실제로 선 자리(src/positions.py)
};
export type DepthPlayer = { player: string; ovr: number; minutes: number; age: number; photo: string };
// 포지션 뎁스 옵션 — kind: primary(주포지션) · secondary(2·3포지션 = 멀티), injured: 현재 부상
export type DepthOption = DepthPlayer & { kind?: "primary" | "secondary"; primary?: string; secondary?: string[]; injured?: boolean };
export type Bucket = { pos: string; count: number; multi?: number; depth: number; starter: DepthOption; rotation: DepthOption[] };
// Best XI 빌더(/api/builder) — 전체 스쿼드 + 주·2·3포지션(실제로 선 자리, src/positions.py) + 부상
export type BuilderPlayer = { player: string; ovr: number; photo: string; age: number; minutes: number; primary: string; secondary: string[];
  line: string; starts: number; injured: { injury: string; until: string } | null; roster_only: boolean };
export const getBuilder = (t: string, l = _league) => j<{ team: string; color: string; players: BuilderPlayer[]; formation?: string | null }>(`/api/builder/${q(t, l)}`);
export type LoanOut = { player: string; club: string; pos: string; nat: string; photo: string; source: string; minutes: number | null; ovr: number | null };
export type Squad = { team: string; color: string; lines: Record<string, SquadPlayer[]>; buckets: Bucket[]; loans?: LoanOut[] };

export type Match = {
  gw?: number; comp: string; date: string; kst?: string | null; home_away: string; opponent: string; opp_logo: string;
  gf: number | null; ga: number | null; score: string; result: string; status: string;
  event_id: string | null; formation: string | null; has_lineup: boolean;
};
export type Schedule = { team: string; color: string; season: string; seasons: string[]; matches: Match[] };
export type MatchDetail = {
  team: string; color: string; event_id: string; formation: string; home_away: string;
  placements: Placement[]; subs: { minute: string; player_in: string; player_out: string }[]; bench: string[];
};

export type CompUse = { key: string; label: string; starts: number; apps: number };
export type CompProfile = { role: string; role_evidence: string; big_match: boolean; league_min: number; comps: CompUse[] };
export type PlayerCard = {
  player: string; pos: string; line: string; age: number;
  nationality: string; value_eur: number; ovr: number; photo: string;
  role: string; big_match: boolean; comps: CompUse[]; trend?: Trend;
};
export type Players = { team: string; color: string; players: PlayerCard[] };

// low = 시도 10회 미만(표본 부족, 회색·평균 제외) · att = 시도 수(성공률 지표) · inv = 낮을수록 좋음(실수·파울)
export type MetricBar = { label: string; pct: number; raw: number; low?: boolean; att?: number | null; inv?: boolean; key?: string };
export type MetricCat = { name: string; avg: number | null; metrics: MetricBar[] };   // avg null = 묶음 전부 표본 부족
export type Badge = { label: string; rank: number; medal: string; scope?: string; tie?: boolean };   // scope: 리그 · 미드필더 450′+
// SCOUT TAKE — AI 한줄평(검증 통과분만, 없으면 l1 없음) + 강점·약점·역할 칩(src/scout_take.py)
export type ScoutTake = { l1?: string; l2?: string; src?: "ai"; at?: string; scene?: string;
  strengths?: string[]; weaks?: string[]; thin?: boolean; role?: string; role_evidence?: string };

export type PlayerDetail = {
  player: string; team: string; color: string; pos: string; line: string;
  age: number; nationality: string; value_eur: number; photo: string;
  ovr: number; ss_rating: number; minutes: number; goals: number; assists: number;
  contract_until: string; joined?: string | null; is_gk: boolean; trend?: Trend;
  ovr_parts?: OvrPart[]; ratings?: RatingSources; form?: number | null; recent?: RecentForm | null;
  categories: MetricCat[];
  radar: { axis: string; value: number; low?: boolean; full?: string }[];
  // 포지션 템플릿(src/position_templates.py) — GK·CB·FB·DM·CM·AM·W·ST, 같은 템플릿 비교 대상 수·범위(리그 | 8개 리그)
  template?: { key: string; en: string; ko: string; n: number; scope: string;
    basis?: "blend" | "season"; cur_minutes?: number; prior_minutes?: number; prior_share?: number; possession?: number | null; padj?: number;
    comps?: "all" | "league"; league_minutes?: number; x_minutes?: number; x_comps?: { code: string; name: string; minutes: number; weight: number }[];
    topup_minutes?: number;
    eff_minutes?: number; enough?: boolean };
  league?: string; league_level?: number; rating_epl?: number | null; proj?: Record<string, number>;
  categories_line?: MetricCat[]; radar_line?: { axis: string; value: number }[];   // 라인 공통 축(포지션 다른 선수 비교용)
  badges: Badge[];
  comp_usage: CompProfile;
  value_history: { date: string; value_eur: number }[];
  peers: { line: string; n: number };
  season_log?: SeasonLog;
  scout_take?: ScoutTake | null;
  fotmob_id?: number | null;   // FotMob 선수 번호 — 방금 경기 실시간 평점(JUST PLAYED)에서 이 선수 찾기
};
// 선수 시즌 기록 — 경기별(대회·출전 분·골·도움) + 대회별 합계 + 전체 합산(리그·컵·유럽 분리)
export type SeasonLogMatch = { date: string; comp: string; comp_code: string; opponent: string; home_away: string; score: string;
  result: string; status: "start" | "sub" | "bench" | "out"; minutes: number; goals: number; pens: number; assists: number;
  yellow: number; red: number; has_events: boolean ; shots?: number; sot?: number; saves?: number; conceded?: number; has_stats?: boolean;
  rating?: number | null };   // FotMob 경기 평점
export type SeasonLogComp = { comp: string; matches: number; apps: number; starts: number; minutes: number; goals: number;
  assists: number; yellow: number; red: number ; shots?: number; sot?: number; saves?: number; conceded?: number; g90?: number | null; shots90?: number | null;
  rating?: number | null; code?: string };   // rating = FotMob 경기 평점 평균 · code = 대회 코드
export type SeasonLog = { available: boolean; espn_name?: string | null; matches: SeasonLogMatch[]; by_comp: SeasonLogComp[];
  total: SeasonLogComp; events_coverage: number; is_gk?: boolean; stats_coverage?: number };

export type TransferItem = {
  player: string; club: string; pos: string; age: number; nat: string;
  fee_eur: number; fee_text: string; photo: string; window: string;
};
export type Transfers = {
  team: string; color: string; in: TransferItem[]; out: TransferItem[];
  window: Window; data_season: string; window_has_data: boolean;
  summary: { spend: number; income: number; net: number; in_count: number; out_count: number };
};

export type Context = { today: string; data_season: string; window: Window };

export type Article = {
  headline: string; headline_en: string; descr: string;
  source: string; published: string; image: string; link: string; is_new: boolean;
  players?: string[];   // 기사에 나온 이 팀 선수(뉴스 선수 태그)
  // 분류(src/news_classify.py) — 종류·이적 단계·인용된 기자, 수집 경로(gnews = Google News 검색)
  kind?: string; stage?: string; journalists?: string[]; via?: string; first_seen?: string;
};
// 여러 매체가 다룬 같은 이야기(src/news_stories.py)
export type NewsStory = { id: string; kind: string; stage: string; title: string; title_en: string; players: string[];
  sources: string[]; journalists: string[]; first: string; last: string; links: string[] };
export type News = { team: string; color: string; articles: Article[]; sparse: boolean;
  ai?: { lines: string[]; at: string; n?: number } | null;   // 최근 48시간 AI 요약 1~3줄
  stories?: NewsStory[]; kinds?: Record<string, number>; sources?: { name: string; n: number }[];
  track?: NewsTrack | null };
// 매체·기자 적중률(src/news_reliability.py) — 이적 루머 vs 실제 이적(닫힌 시장), 단계별 실제 성사율
export type NewsTrackRow = { n: number; hits: number; rate: number; score: number; few: boolean };
export type NewsTrack = { outlets: Record<string, NewsTrackRow>; journalists: Record<string, NewsTrackRow>;
  stages: Record<string, { hits: number; n: number; rate: number }>; all: { n: number; hits: number } | null };

export type AuditItem = { player: string; fee_text: string; fee_eur: number; pos: string; minutes: number; goals: number; assists: number; verdict: string; tone: string; photo: string };
export type ManagerEvo = { name: string; style: string; formation: string; focus: string; tactics?: string; appointed: string; previous?: { name: string; style: string; formation: string } };
export type FactorPlayer = { player: string; photo: string; ovr: number };
export type Factor = { label: string; value: number; line: string; players: FactorPlayer[] };
export type Analytics = {
  team: string; color: string;
  ovr: { overall: number; form: number; attack: number; midfield: number; defense: number; set_piece: number };
  radar: { axis: string; value: number }[];
  injuries: { player: string; games_missed: number; days_out: number; injury: string; line: string; photo: string }[];
  line_missed: Record<string, number>;
  line_share: Record<string, number>;
  context: { home_ppg: number; away_ppg: number; tier_ppg: { top: number; mid: number; bottom: number } };
  factors: { strengths: Factor[]; weaknesses: Factor[] };
  transfer_summary: { spend: number; income: number; in_count: number; out_count: number };
  audit: AuditItem[];
  manager_evo: ManagerEvo | null;
};

export type SimilarResult = { player: string; squad: string; pos: string; age: number; value_eur: number; logo: string; score: number; style: number; perf: number;
  cheaper?: boolean;   // 스카우팅 리포트 — 이 선수 가치의 70% 미만이면 '더 싼 대안'
  league?: string; cross_league?: boolean };   // 유사 선수는 8개 리그 전체(성적 점수만 리그 수준 보정)
// 스카우팅 리포트 한 장(/api/scout-report, src/scout_report.py) — 판단 문장은 규칙, 숫자는 원자료 그대로
export type ScoutMetric = { cat: string; label: string; pct: number; raw: number | null };
export type ScoutReport = {
  player: PlayerDetail; strengths: ScoutMetric[]; weaknesses: ScoutMetric[]; enough: boolean;
  availability: { risk: "low" | "mid" | "high"; current: { injury: string; until: string; source: string } | null;
    seasons: { season: string; games_missed: number; days_out: number; spells: number; injuries: string[] }[] };
  contract: { until: string | null; months_left: number | null; status: "expiring" | "short" | "long" | "unknown" };
  market: { value_eur: number; change_12m_pct: number | null; peak_eur: number; points: number };
  talk: { to_club: string; date: string; source: string; stage: string; probability: number | null; headline: string; outlet_rate?: number | null }[];
  similar: SimilarResult[]; news: PlayerNewsItem[]; stage_rates: Record<string, { hits: number; n: number; rate: number }>;
  fair?: FairPrice | null;   // FAIR PRICE — 사는 구단(지금 보는 팀) 기준 적정 이적료 + 비슷한 이적 5건
  verdict: string[]; generated: string;
};
// buyer = 사는 구단(지금 보는 팀) — 적정 이적료의 사는 리그 배수. 자기 팀 선수면 비워 둔다(리그 평균)
export const getScoutReport = (team: string, player: string, l = _league, buyer = "") =>
  j<ScoutReport>(`/api/scout-report/${encodeURIComponent(team)}/${encodeURIComponent(player)}?league=${encodeURIComponent(l)}`
    + (buyer ? `&buyer=${encodeURIComponent(buyer)}&buyer_league=${encodeURIComponent(_league)}` : ""));
export type Recommendation = { player: string; squad: string; logo: string; pos: string; age: number; ovr: number; value_eur: number; photo: string; rating: number; tactical_fit: number; squad_match: number; why_fit: string[]; why_risk: string[]; confidence: string; role: string; role_evidence: string; big_match: boolean; bucket?: string; bucket_label?: string; cross_league?: boolean; source_league?: string; current_ovr?: number; projected_ovr?: number };
export type LostTarget = { player: string; from: string; to: string; ovr: number; pos: string; photo: string; role: string; top_loss?: boolean };
export type Longshot = { player: string; squad: string; logo: string; ovr: number; pos: string; photo: string; role: string; bucket_label: string; reason: string; cross_league?: boolean; source_league?: string; current_ovr?: number ; style_fit?: number | null };
export type Recommend = { team: string; color: string; weakest: { line: string; label: string; fit_label: string; bucket?: string; bucket_label?: string } | null; addressed: boolean; recommendations: Recommendation[]; longshots?: Longshot[]; lost_targets: LostTarget[] };

const q = (team: string, league: string) =>
  `${encodeURIComponent(team)}?league=${encodeURIComponent(league)}`;

export const getSquad = (t: string, l = _league) => j<Squad>(`/api/squad/${q(t, l)}`);

// ── 스쿼드 네트워크 (KG TEAMMATE_OF) ──
export type SGNode = { id: string; name: string; pos: string; line: string; rating: number | null };
export type SGEdge = { a: string; b: string; matches: number };
export type SquadGraphData = { available: boolean; reason?: string; error?: string; team?: string; nodes: SGNode[]; edges: SGEdge[] };
export const getSquadGraph = (t: string, l = _league) => j<SquadGraphData>(`/api/squad-graph/${q(t, l)}`);
// 케미스트리 — KG TEAMMATE_OF 기반 최고의 듀오·삼각편대
export type ChemCard = { name: string; line: string; pos: string; rating: number | null; photo: string };
// basis=minutes: 실제로 함께 그라운드에 있던 시간(분) · chem=팀 전체 시간 대비 % / matches: KG 경기 수 폴백
export type ChemDuo = { a: ChemCard; b: ChemCard; matches: number; chem: number; minutes?: number };
export type ChemTrio = { players: ChemCard[]; score: number; minutes?: number };
export type ChemistryData = { available: boolean; reason?: string; team?: string; basis?: "minutes" | "matches"; games?: number; duos: ChemDuo[]; trios: ChemTrio[] };
export const getChemistry = (t: string, l = _league) => j<ChemistryData>(`/api/chemistry/${q(t, l)}`);
export const getSchedule = (t: string, season = "", l = _league) => j<Schedule>(`/api/schedule/${q(t, l)}${season ? `&season=${season}` : ""}`);
export const getMatch = (t: string, eid: string, l = _league) =>
  j<MatchDetail>(`/api/match/${encodeURIComponent(t)}/${encodeURIComponent(eid)}?league=${encodeURIComponent(l)}`);
export const getPlayers = (t: string, l = _league) => j<Players>(`/api/players/${q(t, l)}`);
// basis — blend(기본: 시즌 초 안정화 + 점유율 보정) | season(이번 시즌만, 점유율 보정은 유지)
// comps — all(기본: 리그 + 유럽·컵) | league(리그만) · peers=all — 8개 리그 같은 템플릿과 비교(리그 간 비교)
export const getPlayerDetail = (t: string, p: string, l = _league, basis: "blend" | "season" = "blend",
  comps: "all" | "league" = "all", peers: "auto" | "all" = "auto") =>
  j<PlayerDetail>(`/api/player/${encodeURIComponent(t)}/${encodeURIComponent(p)}?league=${encodeURIComponent(l)}${basis === "season" ? "&basis=season" : ""}${comps === "league" ? "&comps=league" : ""}${peers === "all" ? "&peers=all" : ""}`);
export const getTransfers = (t: string, l = _league) => j<Transfers>(`/api/transfers/${q(t, l)}`);
export const getNews = (t: string, l = _league) => j<News>(`/api/news/${q(t, l)}`);
export const getAnalytics = (t: string, l = _league) => j<Analytics>(`/api/analytics/${q(t, l)}`);
export const getCalendar = (league: string = _league) => j<{ events: CalEvent[] }>(`/api/calendar?league=${encodeURIComponent(league)}`);
export const getLineup = (t: string, l = _league, comp: LineupComp = "league") =>
  j<Lineup>(`/api/lineup/${q(t, l)}${comp === "league" ? "" : `&comp=${encodeURIComponent(comp)}`}`);
export type Diag = { kind: string; severity: string; player: string; slot: string; line: string; to?: string; fee?: string; replacement: string; note: string; photo: string };
export type Projection = {
  team: string; color: string; current_label: string; next_label: string; phase?: "in_season" | "offseason" | "stale";
  current: { formation: string; placements: Placement[] };
  projected: { formation: string; placements: Placement[] };
  diagnosis: Diag[];
};
export const getProjection = (t: string, l = _league) => j<Projection>(`/api/projection/${q(t, l)}`);
export type Captain = { name: string; photo: string; ovr: number | null; pos: string; role: string; is_main: boolean;
  no?: number | null; rank?: number; injured?: boolean };
export const getCaptains = (t: string, l = _league) =>
  j<{ team: string; color: string; captains: Captain[]; source?: string }>(`/api/captains/${q(t, l)}`);

// ── 팀 지식그래프(NETWORK 탭) — /api/network: 주장단·관계망·스쿼드 구성·국적·클럽 연결 + 근거 인사이트 ──
export type NetNation = { name: string; code: string; flag: string; rank: number | null };
export type NetOrigin = { acq: string; from_club: string | null; fee_text: string | null; fee_eur: number | null; year: number | null };
export type NetPlayer = {
  name: string; photo: string; line: string; pos: string; ovr: number | null; age: number | null; minutes: number;
  joined: string | null; prev_squad: string | null; no: number | null; captain_rank: number | null;
  injured: boolean; injury?: string | null; wc: boolean; nation: NetNation | null; origin: NetOrigin;
  tenure: number | null; unplayed?: boolean;
};
export type NetCore = NetPlayer & { influence: number; components: Record<string, number>; why: string[] };
export type NetCaptain = NetCore & { label: string; role_ko: string };
export type NetMove = { player: string; fee_text?: string | null; photo?: string; window?: string; ovr?: number | null; prob?: number | null };
export type NetLink = { club: string; logo: string; league: string | null; in: NetMove[]; out: NetMove[]; alumni: NetMove[];
  rumor_in: NetMove[]; rumor_out: NetMove[]; weight: number };
export type NetInsight = { lens: string; icon: string; tone: string; title: string; text: string; evidence: string[];
  big?: string; unit?: string; line?: string; who?: string[]; club?: string; flag?: string };
export type NetworkData = {
  available: boolean; reason?: string; team: string; league: string; color: string; logo: string; games: number;
  players: NetPlayer[];
  leadership: { captains: NetCaptain[]; armband: string | null; core: NetCore[]; influence: Record<string, number>; weights?: Record<string, number> };
  chemistry: { nodes: { name: string; minutes: number; degree: number; hub_rank: number }[];
    edges: { a: string; b: string; minutes: number; matches: number }[]; duos: ChemDuo[]; trios: ChemTrio[] };
  origins: { timeline: { year: number; players: string[] }[]; acq: Record<string, number>;
    sources: { league: string; n: number; fee_eur: number; players: string[] }[] };
  nations: { countries: (NetNation & { players: string[]; wc: number })[]; n: number; wc_total: number };
  links: { clubs: NetLink[]; n_clubs: number };
  insights: NetInsight[];
  sources: { captains: string | null };
  national: Record<string, NetNational>;
  ties: NetTies;
  manager: NetManager;
};
// 대표팀 동료(2026 월드컵 명단) — 같은 대표팀 선수가 어느 클럽에
export type NetNational = {
  players: { player: string; pos: string; club: string | null; league: string | null; photo: string; ovr: number | null; ours: boolean }[];
  clubs: { club: string; n: number; players: string[]; logo: string }[]; n_ours: number; flag: string; rank: number | null; fifa_name: string;
};
// 전 소속 동료(지난 시즌 라인업) — former: 영입생의 전 소속 동료 · alumni: 작년 우리 팀 동료가 떠남 · reunion: 다른 팀에서 함께 뛰다 재회
export type NetTie = { ours: string; ours_photo: string; mate: string; mate_photo: string; mate_ovr: number | null; from_club: string;
  starts: number; now_club: string; now_league: string | null; kind: "former" | "alumni" | "reunion"; links?: number };
export type NetTies = { clubs: { club: string; league: string | null; logo: string; ties: NetTie[]; weight: number }[];
  n_ties: number; n_clubs: number; reunions: NetTie[]; players: string[] };
// 감독 커리어 그래프
export type NetSpell = { club: string; start: number | null; end: number | null; role?: string; loan?: boolean; canon: string | null; logo: string };
export type NetManager = {
  available: boolean; name?: string; photo?: string; nationality?: string; appointed?: string;
  managed?: NetSpell[]; played?: NetSpell[]; n_network?: number; brought?: string[];
  network?: { manager: string; team: string; league: string; photo: string; logo: string; shared: { club: string; mine: string; theirs: string }[] }[];
};
export const getNetwork = (t: string, l = _league) => j<NetworkData>(`/api/network/${q(t, l)}`);
// 이적설 지도(NETWORK RUMOURS 렌즈) — TM 루머 + 열린 시장 뉴스 루머(매체 적중률 가중), src/rumor_map.py
export type RumorStage = "denied" | "rumour" | "interest" | "talks" | "agreed" | "done";
export type RumorNews = { outlet: string; journalists: string; stage: RumorStage; date: string; link?: string; headline?: string; trust: number };
export type RumorClub = { club: string; logo: string; league: string | null };
export type RumorWhere = { name: string; club: string; league: string; photo: string; ovr: number; age: number | null; minutes: number };
export type RumorLink = { player: string; from: string; to: string; heat: number; stage: RumorStage;
  tm: { prob: number | null; date: string } | null; news: RumorNews[]; n_news: number; outlets: string[]; last: string | null;
  info: { age?: number; pos?: string; value?: number } };
export type RumorIn = RumorLink & { where: RumorWhere | null; from_meta: RumorClub | null;
  rivals: (RumorClub & { heat: number; stage: RumorStage })[] };
export type RumorOut = { player: string; key: string; heat: number; where: RumorWhere | null; suitors: (RumorLink & { to_meta: RumorClub })[] };
export type RumorMap = { available: boolean; reason?: string | null; team: string; logo: string; color: string;
  in: RumorIn[]; out: RumorOut[]; n_in: number; n_out: number;
  competition: (RumorClub & { players: string[]; score: number })[];
  outlets: { outlet: string; n: number; trust: number }[];
  stages: Record<string, { hits: number; n: number; rate: number }>; sources: { links: number; with_news: number } };
export const getRumorMap = (t: string, l = _league) => j<RumorMap>(`/api/rumor-map/${q(t, l)}`);
export const getSimilar = (p: string, l = _league, scope: "all" | "league" = "all") =>
  j<{ player: string; results: SimilarResult[]; league?: string; scope?: string }>(`/api/similar/${encodeURIComponent(p)}?league=${encodeURIComponent(l)}&scope=${scope}`);
export const getRecommend = (t: string, l = _league) => j<Recommend>(`/api/recommend/${q(t, l)}`);

// ── 벡터(Qdrant) 스타일-핏 교차리그 발굴 + KG 신호 (로컬 전용) ──
export type DiscoverPick = {
  player: string; squad: string; pos: string; ovr: number; current_ovr: number; projected_ovr: number;
  cross_league: boolean; source_league: string; value_eur: number | null; style_fit: number;
  euro: boolean; age: number | null; photo: string; why_fit: string[];
  goals?: number; assists?: number; rating?: number;
  price_verdict?: string; likely_fee_eur?: number | null; recruit_fit?: number; contract_until?: string;
  fair?: FairBrief | null;   // 적정 이적료(사는 구단 = 이 팀)
  kg_rumored?: boolean; kg_rumor_prob?: number | null; kg_precedent?: number;
  policy_ok?: boolean | null; policy_notes?: string[];   // 구단 이적 정책(나이·이적료) 대조
  realistic?: boolean;   // 경쟁 팀·강팀 핵심 주전·라이벌 소속이면 false(영입 가능성 낮음)
  rival?: boolean;       // 위키 라이벌·더비(같은 리그) 구단 소속(src/club_rivals.py)
  level?: "starter" | "rotation" | "prospect" | "below" | null;   // 팀 OVR 대비 수준(주전급 −4 · 로테이션 −9 · 21세 이하 유망주)
  minutes?: number;
};
export type Discover = {
  available: boolean; reason?: string; error?: string;
  team?: string; target_league?: string; target_roles?: string[];
  kpi?: { count: number; avg_age: number | null; avg_value: number | null; leagues: string[] };
  recommendations: DiscoverPick[];
  policy?: TransferPolicy | null;
  needs?: { role: string; label: string; urgency: number; level: string }[];   // 자동 대상 포지션(니즈 v2 상위)
  team_ovr?: number | null;
};
// TRANSFER WORKSPACE(/api/workspace) — 예산(최근 두 창·가격 상한·정책) + 라이벌 + 고정 후보의 최신 사실
export type WorkspacePick = { player: string; club: string; league: string; found: boolean; pos?: string; tm_position?: string;
  age?: number | null; photo?: string; ovr?: number; current_ovr?: number; cross_league?: boolean; value_eur?: number | null;
  likely_fee_eur?: number | null; price_verdict?: string; contract_until?: string | null; months_left?: number | null; fair?: FairBrief | null;
  contract_status?: "expiring" | "short" | "long" | "unknown"; minutes?: number; goals?: number; assists?: number; rating?: number | null;
  policy_ok?: boolean | null; policy_notes?: string[]; realistic?: boolean; rival?: boolean; logo?: string };
export type Workspace = { team: string; team_ovr: number; avg_spend: number | null; ceiling_eur: number | null; spend_tier?: string;
  windows: { season_id: number; window: string; label: string; spend: number; income: number; n_in: number; n_out: number }[];
  policy: TransferPolicy | null; rivals: string[]; shortlist: WorkspacePick[] };
// TRACKING(/api/tracking) — SHORTLIST 후보의 최근 14일 변화(이적 완료·우리 팀 연결·부상·다른 구단 관심·경기·폼)
export type TrackType = "moved" | "linked" | "injury" | "return" | "rivals" | "value" | "match" | "form" | "absent";
export type TrackAlert = { id: string; type: TrackType; prio: number; date: string; title: string; detail: string;
  player: string; club: string; league: string; photo: string; logo: string };
export type TrackPlayer = { player: string; club: string; league: string; photo: string; logo: string;
  requested: { player: string; club: string; league: string };
  status: { k: "out" | "contract"; label: string; tip: string }[]; n: number; top: string | null };
export type Tracking = { team: string; since: string; players: TrackPlayer[]; alerts: TrackAlert[] };
export const getTracking = (team: string, items: { player: string; club: string; league: string }[], l = _league) =>
  j<Tracking>(`/api/tracking/${encodeURIComponent(team)}?league=${encodeURIComponent(l)}&players=${encodeURIComponent(JSON.stringify(items))}`);
export const getWorkspace = (team: string, items: { player: string; club: string; league: string }[], l = _league) =>
  j<Workspace>(`/api/workspace/${encodeURIComponent(team)}?league=${encodeURIComponent(l)}&players=${encodeURIComponent(JSON.stringify(items))}`);
export type DiscoverOpts = { role?: string; top?: number };
export const getDiscover = (t: string, opts: DiscoverOpts = {}, l = _league) => {
  const p = new URLSearchParams({ league: l });
  if (opts.role) p.set("role", opts.role);
  if (opts.top) p.set("top", String(opts.top));
  return j<Discover>(`/api/discover/${encodeURIComponent(t)}?${p.toString()}`);
};

// ── 스카우트 데스크 (Needs Board) ──
export type NeedItem = { line: string; line_label: string; kind: string; title: string; severity: string; reason: string; status: string; player: string | null };
export type NeedsWindow = { is_open: boolean; label: string; kr: string | null; signings: { player: string; line: string; pos: string; fee: string }[]; departures: { player: string; line: string; pos: string }[] };
// 포지션 니즈 v2(api _position_needs) — 뎁스·지금 가용(부상)·이번 창 순증감·주전 폼·나이·계약
export type PositionNeed = {
  role: string; label: string; demand: number; urgency: number; level: "urgent" | "need" | "watch" | "ok"; when: string;
  reasons: string[]; options: number; need_n: number;
  depth: { player: string; ovr: number; kind: "primary" | "secondary"; injured: boolean; until: string; recent: number | null; age: number; photo: string }[];
  window: { out: NeedMove[]; in: NeedMove[]; verdict: string };
  signals?: NeedSignals;   // 근거 구조화(화면 아이콘 칩) — reasons 는 같은 내용의 문장
};
export type NeedMove = { player: string; ovr: number | null; fee: string; age: number | null; photo?: string };
export type NeedSignals = {
  depth: { have: number; need: number }; unreplaced?: number;
  injury?: { drop: number; players: { player: string; weeks: number; photo: string }[] };
  cold?: { player: string; recent: number; photo: string }[];
  aging?: { player: string; age: number }[]; contract?: { player: string; until: string }[];
};
// 구단 이적 정책(최근 두 시즌 영입) — 나이·이적료·국내 비율·출신 리그
export type TransferPolicy = {
  team: string; n: number; age_med: number | null; age_lo: number | null; age_hi: number | null; u23_share: number | null;
  fee_med: number | null; fee_max: number | null; paid_share: number; domestic_share: number;
  sources: { league: string; n: number }[]; big: { player: string; fee: number; age: number | null; from: string }[];
};
export type Needs = { team: string; color: string; mode: string; window: NeedsWindow; needs: NeedItem[];
  positions?: PositionNeed[]; team_ovr?: number | null; policy?: TransferPolicy | null };
export const getNeeds = (t: string, l = _league) => j<Needs>(`/api/needs/${q(t, l)}`);
export const getContext = () => j<Context>(`/api/context`);

export type DbPlayer = { player: string; squad: string; league: string; logo: string; pos: string; line: string; age: number; nationality: string; value_eur: number; ovr: number; photo: string; role: string; big_match: boolean };
type DbResp = { league: string; players: DbPlayer[]; nationalities: string[]; leagues: string[] };
// 세션 내 캐시 — DB 는 세션 중 불변. 탭 재방문 시 재요청 없이 즉시(대용량 전리그 목록).
let _dbCache: Promise<DbResp> | null = null;
// 한글 이름 사전(전역 검색 한글 검색) — 선수 키 'Declan Rice|Arsenal'
let _koCache: Promise<{ players: Record<string, string>; clubs: Record<string, string> }> | null = null;
export const getNamesKo = () => (_koCache ??= j<{ players: Record<string, string>; clubs: Record<string, string> }>(`/api/names-ko`)
  .catch((e) => { _koCache = null; throw e; }));
// 검색용 접기 — 악센트·대소문자 무시(Mbappé = mbappe, Ødegaard = odegaard). 한글은 그대로
export const foldName = (s: string) => s.toLowerCase().replace(/ø/g, "o").replace(/æ/g, "ae").replace(/ß/g, "ss")
  .replace(/[łđ]/g, (c) => (c === "ł" ? "l" : "d")).normalize("NFD").replace(/[̀-ͯ]/g, "").normalize("NFC");
export const getDatabase = () => (_dbCache ??= j<DbResp>(`/api/database`).catch((e) => { _dbCache = null; throw e; }));

export type Signal = { date: string; team: string; logo: string; type: string; tone: string; icon: string; player: string; photo: string; title: string; detail: string };
export type Signals = { team: string; window: Window; counts: Record<string, number>; signals: Signal[] };
// 팀 인박스(/api/inbox) — 자동 감지 + 경기 브리핑 + 팀·선수 폼 + 선발 제외. prio 상위 3 = briefing
export type InboxMsg = { id: string; cat: string; type: string; tone: string; icon: string; title: string; detail: string; prio: number;
  date: string; player: string; photo: string; action: { kind: "match"; fixture: unknown } | { kind: "player"; name: string } | null };
export type Inbox = { team: string; briefing: InboxMsg[]; messages: InboxMsg[]; counts: Record<string, number>; league_events: Signal[]; opponents?: string[]; generated: string };   // opponents 있으면 OPPONENT WATCH
// THIS WEEK(감독용, Overview 맨 위 — /api/this-week, src/this_week.py)
export type WeekAbsence = { player: string; injury: string; until: string; ovr: number | null; photo: string; starter: boolean };
export type ThisWeek = { team: string; today: string; week: Fixture[]; congestion: number; absences: WeekAbsence[];
  opponent: { team: string; league: string | null; logo: string; rank: number | null; absences: WeekAbsence[]; covered: boolean } | null;
  xi: { formation: string | null; placements: Placement[]; basis: string;
    changes: { slot: string; out: string; in: string | null; reason: string; until?: string; ovr_out?: number | null; ovr_in?: number | null }[] };
  rotation: { player: string; minutes14: number; full_streak: number; level: "high" | "mid"; ovr: number | null }[]; games14: number;
  intl: { label: string; days_to: number; kind?: string; n: number; squad_state?: string; players: string[] } | null };
export const getThisWeek = (team: string, l = _league) => j<ThisWeek>(`/api/this-week/${encodeURIComponent(team)}?league=${encodeURIComponent(l)}`);
export const getInbox = (team: string, l = _league) => j<Inbox>(`/api/inbox/${encodeURIComponent(team)}?league=${encodeURIComponent(l)}`);
export const getSignals = (team = "", l = _league, limit = 60) =>
  j<Signals>(`/api/signals?team=${encodeURIComponent(team)}&league=${encodeURIComponent(l)}&limit=${limit}`);

// ── 홈 대시보드 ──
export type HomeDeal = { player: string; to: string; to_logo: string; from: string; pos: string; fee_eur: number; fee_text: string; photo: string };
export type HomeNet = { team: string; logo: string; spend: number; income: number; net: number };
export type HomeMgr = { team: string; logo: string; previous: string; current: string; photo: string; previous_photo: string; formation: string; changed_at: string };
export type HomeNews = { headline: string; team: string; source: string; image: string; link: string };
export type BuzzItem = { title: string; title_en: string; source: string; tier: string; link: string; published: string };
export type Home = {
  season: string; window: Window;
  kpi: { spend: number; deals: number; mgr_changes: number; injuries: number };
  buzz: BuzzItem[];
  transfers: { top_deals: HomeDeal[]; net_spend: HomeNet[] };
  signals: Signal[]; signal_counts: Record<string, number>;
  manager_changes: HomeMgr[]; news: HomeNews[];
  standings: Team[]; roster_next: NextSeason;
};
export const getHome = (league = _league) =>
  j<Home>(`/api/home?league=${encodeURIComponent(league)}`);

// ── 월드컵 2026 ──
export type WCMatch = { date: string; group: string; home: string; home_abbr: string; home_logo: string; home_score: number | null; away: string; away_abbr: string; away_logo: string; away_score: number | null; status: string; completed: boolean };
export type WCRound = { round: string; label: string; matches: WCMatch[] };
export type WCGroupRow = { team: string; logo: string; P: number; W: number; D: number; L: number; GF: number; GA: number; GD: number; Pts: number };
export type WCGroup = { group: string; table: WCGroupRow[] };
export type WCScorer = { player: string; nation: string; goals: number; pens: number; logo: string };
export type WCAssist = { player: string; nation: string; assists: number; logo: string };
export type WCImpact = { player: string; nation: string; age: number; goals: number; assists: number; ga: number; logo: string; club: string; photo: string };
export type WCHeroTeam = { team: string; logo: string; group: string; P: number; W: number; D: number; L: number; GD: number; Pts: number; stars: { player: string; goals: number; assists: number }[] };
export type WCClubPlayer = { player: string; nation: string; pos: string; photo: string; goals: number };
export type WCClub = { club: string; league: string; logo: string; count: number; players: WCClubPlayer[] };
export type WCNation = { nation: string; logo: string; count: number };
export type WCFifaRank = { rank: number; team: string; code: string; points: number; official_rank: number; rank_change: number; points_change: number; confederation: string; flag: string };
export type WorldCupData = { matches: WCRound[]; groups: WCGroup[]; scorers: WCScorer[]; assists: WCAssist[]; rising_stars: WCImpact[]; veterans: WCImpact[]; group_heroes: WCHeroTeam[]; club_callups: WCClub[]; nations: WCNation[]; fifa_ranking: WCFifaRank[]; fifa_updated: string; fifa_live: boolean };
export const getWC = () => j<WorldCupData>(`/api/wc`);

// ── 전 리그 통합 대시보드 ──
export type HubDeal = { player: string; to: string; to_logo: string; from: string; pos: string; fee_eur: number; fee_text: string; photo: string; league: string; league_name: string };
export type HubBuzz = { title: string; source: string; tier: string; link: string; published: string; league: string; league_name: string };
export type HubChange = { team: string; logo: string; previous: string; current: string; photo: string; changed_at: string; when_label?: string; in_season?: boolean; league: string; league_name: string };
export type HubSnapRow = { rank: number; team: string; logo: string; points: number };
export type HubSnapshot = { league: string; league_name: string; color: string; table: HubSnapRow[];
  rank_group?: number };   // 0 = TIER 1 · 1 = TIER 2 · 2 = 2부·TIER 3(리그 집중 탭의 '+N' 메뉴)
export type HubForm = { player: string; club: string; club_logo: string; rating: number; ovr: number; pos: string; age: number; photo: string; league: string; league_name: string;
  rating_adj?: number };   // 리그 수준만큼 뺀 평점(리그를 넘나드는 순위 기준)
// VALUE PICKS — 나이·포지션·시장가치로 기대되는 OVR 보다 얼마나 높은가(ovr_gap)
export type HubValue = HubForm & { value_eur: number; ovr_expected?: number; ovr_gap?: number };
// 시장가치 상승 — 선수마다 가장 최근 TM 갱신(prev_eur → value_eur, date). 옛 스냅샷엔 prev_eur·date 가 없을 수 있음
export type HubRiser = { player: string; club: string; club_logo: string; value_eur: number; delta_eur: number; pct: number; photo: string; league: string; league_name: string;
  prev_eur?: number; date?: string };
export type HubGoal = { player: string; club: string; club_logo: string; goals: number; assists: number; ovr: number; age: number; photo: string; league: string; league_name: string };
export type HubContract = { player: string; club: string; club_logo: string; until: string; value_eur: number; ovr: number; age: number; photo: string; league: string; league_name: string };
export type HubInjury = { player: string; club: string; club_logo: string; event: string; injury: string; date: string; photo: string; league: string; league_name: string };
// 리그 집중 보드 — 득점왕 레이스 · 시즌 베스트 XI(4-3-3, 시즌 평균 평점) · 부상으로 줄어든 베스트 XI 평균 전력
export type HubBoot = { player: string; club: string; club_logo: string; goals: number; assists: number; minutes: number; mpg: number | null; ovr: number; photo: string; league: string; xg?: number; shots?: number };
// 리그 분석 랩(/api/league-lab/{league}) — Sofascore 시즌 기록
export type LabPlaymaker = { player: string; club: string; club_logo: string; photo: string; minutes: number; assists: number; xa: number; bcc: number; kp: number };
export type LabFinish = { player: string; club: string; goals: number; xg: number; shots: number };
export type LabCreate = { player: string; club: string; assists: number; xa: number; kp: number };
export type LabBallWinner = { player: string; club: string; club_logo: string; photo: string; minutes: number; tackles: number; inter: number; recov: number; score: number };
export type TeamStyle = { team: string; logo: string; rank: number; xg_pg: number; gf_pg: number; ga_pg: number };
export type TableRow = { rank: number; team: string; logo: string; played: number; won: number; drawn: number; lost: number; gf: number; ga: number; gd: number;
  points: number; form: string[]; xg_pg: number | null; ovr: number | null; str_rank: number | null; manager: string };
export type LeagueLab = { league: string; playmakers: LabPlaymaker[]; finishing: LabFinish[]; creating: LabCreate[]; ball_winners: LabBallWinner[]; team_style: TeamStyle[];
  table?: TableRow[]; race?: RaceTeam[]; over?: TableGap[]; under?: TableGap[]; results?: ResultMatch[]; watch?: WatchMatch[];
  tots?: TotsPlayer[]; tots_formation?: string | null; tots_subs?: TotsSub[]; golden_boot?: HubBoot[]; injury_impact?: InjuryImpactRow[];
  // 아직 결과가 반영되지 않은 최근·오늘 리그 경기(event_id → 우리 표기 팀) — 라이브 스코어로 잠정 순위를 만든다
  pending?: Record<string, { home: string; away: string }> };
export const getLeagueLab = (league: string) => j<LeagueLab>(`/api/league-lab/${encodeURIComponent(league)}`);
export type TotsAlt = { player: string; club: string; rating: number; minutes: number; goals: number; assists: number };
// 시즌 베스트 XI 교체 명단(SUBS) — role = 실제로 선 주포지션(GK·CB·LB·DM·CM·AM·LW·RW·ST)
export type TotsSub = { player: string; club: string; club_logo: string; rating: number; ovr: number; photo: string; minutes: number;
  goals: number; assists: number; pos?: string; role: string };
export type TotsPlayer = { slot: string; kind: string; x: number; y: number; player: string; club: string; club_logo: string; rating: number; ovr: number; photo: string; minutes: number;
  goals?: number; assists?: number; pos?: string; alts?: TotsAlt[]; role?: string };
export type InjuryImpactRow = { team: string; logo: string; league: string; n: number; loss: number; key: string[]; ovr: number };
// 선수 동향 — OVR 변화. basis 2w = 2주 전 대비(기록 2주+ 쌓인 뒤), season = 지난 시즌 대비
export type HubMover = HubForm & { delta: number; ovr_prev: number; basis: "2w" | "season"; minutes: number };
export type HomeAll = { window: Context["window"]; leagues: { key: string; name: string }[]; top_deals: HubDeal[]; buzz: HubBuzz[]; manager_changes: HubChange[]; snapshots: HubSnapshot[]; injuries: HubInjury[]; hot_form: HubForm[]; goal_leaders: HubGoal[]; prospects: HubForm[]; veterans: HubForm[]; value_picks: HubValue[]; risers: HubRiser[]; contracts: HubContract[];
  movers_up?: HubMover[]; movers_down?: HubMover[]; movers_basis?: "2w" | "season";
  golden_boot?: Record<string, HubBoot[]>; tots?: Record<string, TotsPlayer[]>; injury_impact?: InjuryImpactRow[];
  // 리그 전체 집계(목록은 리그별 상위 몇 건뿐) — 예전 스냅샷엔 없을 수 있음
  summary?: { spend_eur: number; signings: number; manager_changes: number; manager_changes_inseason?: number; injured: number }; generated_at?: string };
export const getHomeAll = () => j<HomeAll>(`/api/home/all`);

// ── 홈 리그 지도(/api/league-map) — 티어(리그 수준 92·86)·2부 리그 부모·순위 1~3위·빅5로 보낸 이적료 ──
export type LeagueMapTop = { team: string; pts: number | null; logo: string };
export type LeagueMapExports = { n: number; fee_eur: number; avg_age: number | null };
export type LeagueMapItem = {
  key: string; name: string; tier: 1 | 2 | 3 | null; parent: string | null; level: number;
  top: LeagueMapTop[]; exports: LeagueMapExports | null;
};
export type LeagueMapData = {
  leagues: LeagueMapItem[]; cuts: number[];
  soon: { key: string; name: string; tier: 3; exports: LeagueMapExports | null }[];
};
export const getLeagueMap = () => j<LeagueMapData>(`/api/league-map`);
// 매치 센터 — 다가오는 경기·빅매치(src/match_center.py). kst 는 한국 시간 표기, d_day 는 오늘 기준.
export type FixtureSide = { team: string; league: string | null; rank: number | null; points: number | null;
  logo: string; color: string; ovr: number | null; form: string[] };
// 승리 확률 — 팀 OVR 차이 + 경기당 골득실 → 포아송 모델(src/match_center.win_prob). 베팅 배당 아님.
export type WinProb = { h: number; d: number; a: number; xg_h: number; xg_a: number };
// 외부 예측 — fans = Sofascore 팬 투표(n 표, BTTS·선제골 투표 포함), elo = Elo 기준(우리 Elo 만으로 낸 단순 예측)
export type FanVote = { h: number; d: number; a: number; n: number; btts: number | null; first_h: number | null; first_a: number | null };
export type EloProb = { h: number; d: number; a: number };
// 우리 예측 모델 v2(src/predict_model.py) — xG·골 공격/수비 강도 + 선수 평점(OVR) 사전값 + Dixon-Coles. 백테스트 scripts/backtest_model.py
// inputs(v3) — elo_d: 홈 Elo − 원정 Elo · miss_h/miss_a: 부상·출장정지로 빠진 베스트 11 평균 OVR 손실
export type ModelProb = { h: number; d: number; a: number; xg_h: number; xg_a: number; score: string; btts: number; o25: number; n_h: number; n_a: number;
  // intl_*: A매치 휴식기 직후 첫 경기 — 돌아오는 대표 선수 수 · intl_far_*: 그중 유럽 밖 대표팀(참고 표시, 확률엔 안 넣음)
  inputs?: { elo_d?: number; elo_h?: number; elo_a?: number; miss_h?: number; miss_a?: number;
    intl_h?: number; intl_a?: number; intl_far_h?: number; intl_far_a?: number } };
export type Fixture = { event_id: string | null; comp_code: string; comp: string; kickoff: string; kst: string;
  date: string; d_day: number; home: FixtureSide; away: FixtureSide; big: number; tags: string[]; prob?: WinProb | null;
  fans?: FanVote; elo?: EloProb; model?: ModelProb };
export const getFixtures = (days = 7, league = "", limit = 6) =>
  j<{ days: number; count: number; big: Fixture[]; today: Fixture[]; matches?: Fixture[] }>(
    `/api/fixtures?days=${days}&limit=${limit}${league ? `&league=${encodeURIComponent(league)}` : ""}`);
// 홈 '지금' 정보 — 최근 결과(이변)·리그별 주목할 매치·우승 경쟁 승점 추이·전력 대비 성적(/api/hub/pulse)
export type ResultSide = FixtureSide & { goals: number };
export type ResultMatch = Omit<Fixture, "home" | "away"> & { home: ResultSide; away: ResultSide; upset: string };
export type WatchMatch = Fixture & { watch: number; why: string[]; league: string };
export type RaceTeam = { team: string; logo: string; color: string; points: number[]; rank: number };
export type TableGap = { team: string; logo: string; league: string; rank: number; str_rank: number; gap: number; ovr: number;
  points: number; n: number; manager: string; hot_seat: boolean };
export type HubPulse = { results: ResultMatch[]; watch: WatchMatch[]; race: { league: string; teams: RaceTeam[] }[]; over: TableGap[]; under: TableGap[] };
export const getHubPulse = () => j<HubPulse>(`/api/hub/pulse`);
// 예측 성적표 — 팬 투표 vs 우리 모델 vs Elo 기준(/api/prediction-league, 원천 data/predictions_log.csv)
export type PredScore = { key: "fans" | "model" | "elo"; en: string; kr: string; n: number; acc: number | null; brier: number | null; logloss: number | null; hits: number };
export type PredPick = { pick: "H" | "D" | "A"; p: number } | null;
export type PredRecent = { event_id: string; date: string; home: string; away: string; home_logo: string; away_logo: string; hg: number; ag: number;
  result: "H" | "D" | "A"; fans: PredPick; model: PredPick; elo: PredPick; outside?: boolean };
export type PredSplit = { event_id: string; date: string; home: string; away: string; home_logo: string; away_logo: string; fans: PredPick; model: PredPick; gap: number ; kind?: "pick" | "confidence"; model_on_fan_pick?: number };
type PredStat = Omit<PredScore, "key" | "en" | "kr">;
// common: 세 출처가 모두 예측한 같은 경기 맞대결(rank = 적중률 → 브라이어) · v3: 같은 경기를 모델 v3 로(이전 경기는 재계산, 참고)
export type PredictionLeague = { available: boolean; since?: string; sources: PredScore[];
  h2h: { n: number; fans: PredStat; model: PredStat } | null; recent: PredRecent[]; split: PredSplit[];
  common?: { n: number; scores: Record<string, PredStat>; rank: string[]; v3: PredStat | null; v3_live: number } | null;
  model_versions?: Record<string, number>; v3_since?: string | null;
  legacy_clubelo?: { n: number; acc: number | null; brier: number | null } | null };   // 예전 ClubElo(10/15~10/24, 사이트 차단으로 중단)
export const getPredictionLeague = () => j<PredictionLeague>(`/api/prediction-league`);
// 경기 리뷰 — ESPN 경기 상세로 만든 규칙 기반 리포트(src/match_review.py). 종료 하루·진행 중 1분 캐시
export type ReviewSide = "home" | "away";
export type ReviewGoal = { minute: string; m: number; side: ReviewSide; scorer: string; assist: string; kind: "" | "pen" | "og" | "header" };
export type ReviewCard = { minute: string; m: number; side: ReviewSide; player: string; color: "yellow" | "red" };
export type ReviewPen = { minute: string; m: number; side: ReviewSide; player: string; result: "saved" | "missed" };
export type ReviewStat = { key: string; label: string; h: number; a: number; fmt: "pct" | "int" | "ratio" };
export type ReviewTeam = { team: string; league: string | null; logo: string; color: string };
export type MatchReview = { event_id: string; comp: string; date: string; state: "pre" | "in" | "post"; detail: string;
  score: { home: number; away: number }; headline: string; lines: string[]; goals: ReviewGoal[]; cards: ReviewCard[]; pens: ReviewPen[];
  stats: ReviewStat[]; star: { player: string; side: ReviewSide; goals: number; assists: number } | null;
  predictions: { source: string; pick: string; p: number; hit: boolean }[]; venue: string; attendance: number | null;
  ht: { home: number; away: number } | null; home: ReviewTeam; away: ReviewTeam;
  ai?: { text: string; at: string } | null };   // AI 경기 리포트(배치 생성·검증 통과분, 종료 경기만)
export const getReview = (eventId: string, comp = "") =>
  j<MatchReview>(`/api/review/${encodeURIComponent(eventId)}${comp ? `?comp=${encodeURIComponent(comp)}` : ""}`);
// 팀 시즌 현황(/api/team-season) — 순위·승점 흐름(1위·4위 비교)·최근 5경기(전 대회)·시즌 프로필(지표별 리그 순위·근거)
export type PointsPath = { team: string; path: number[]; logo: string; color: string; label?: string };
export type ProfileAxis = { key: string; en: string; kr: string; value: number; rank: number; n: number; hint: string ; prev?: number | null; prev_rank?: number | null; prev_hint?: string };
export type TeamSeason = { team: string; league: string; n: number;
  standing: { rank: number; played: number; won: number; drawn: number; lost: number; gf: number; ga: number; gd: number; points: number } | null;
  xg_pg: number | null; str_rank: number | null; xg_rank?: number | null; xg_avg?: number | null; path: PointsPath; refs: PointsPath[]; recent: ResultMatch[]; profile: ProfileAxis[]; goal_mix?: GoalMix | null;
  // 실시간 반영 재료 — 공식 결과 전 라이브 스코어로 덮어쓴다(lib/liveTable · SeasonSnapshot)
  table?: TableRow[]; pending?: Record<string, { home: string; away: string }>; team_pending?: Fixture[] };
// 분석 탭 — 경기별 흐름·득실 시간대·리그 백분위(/api/team-trends, 원천 match_stats: ESPN 경기 기록 + 5대 리그 Understat xG)
export type TrendMatch = { event_id: string; date: string; comp_code: string; opponent: string; opp_logo: string; home_away: string;
  gf: number; ga: number; result: string; xg: number | null; xga: number | null; shots: number | null; opp_shots: number | null;
  sot: number | null; opp_sot: number | null; poss: number | null; ppda: number | null; xpts: number | null };
export type TrendPct = { key: string; en: string; kr: string; value: number; fmt: "f1" | "f2" | "pct"; pct: number; rank: number; n: number;
  high_good: boolean; league_avg: number };
export type TeamTrends = { team: string; league: string; available: boolean; has_xg: boolean; matches: TrendMatch[];
  timing: { buckets: string[]; scored: number[]; conceded: number[]; games: number; league_games?: number } | null; percentiles: TrendPct[] };
export const getTeamTrends = (team: string, l = _league) =>
  j<TeamTrends>(`/api/team-trends/${encodeURIComponent(team)}?league=${encodeURIComponent(l)}`);
export const getTeamSeason = (team: string, l = _league) =>
  j<TeamSeason>(`/api/team-season/${encodeURIComponent(team)}?league=${encodeURIComponent(l)}`);
export const getTeamFixtures = (team: string, l = _league, n = 3) =>
  j<{ team: string; next: Fixture[] }>(`/api/fixtures/${encodeURIComponent(team)}?league=${encodeURIComponent(l)}&n=${n}`);
// 선수 시즌 히트맵(Sofascore) — analytics 포지셔널 히트맵
export type HeatmapPlayer = { player: string; pos: string; line: string; minutes: number; ovr: number; photo: string; n_points: number; grid: number[] };
export type HeatmapData = { available: boolean; team: string; gw: number; gh: number; players: HeatmapPlayer[];
  links?: { a: string; b: string; minutes: number; matches: number }[]; orientation?: string };
export const getHeatmaps = (team: string, league = _league) =>
  j<HeatmapData>(`/api/heatmaps/${encodeURIComponent(team)}?league=${encodeURIComponent(league)}`);
export type WCSquadPlayer = { player: string; pos: string; jersey: string; age: string; club: string; league: string; club_logo: string; photo: string };
export type WCSquad = { nation: string; count: number; players: WCSquadPlayer[] };
export const getWCSquad = (nation: string) => j<WCSquad>(`/api/wc/squad/${encodeURIComponent(nation)}`);

// 이적료 표기 통일 — Transfermarkt 원문('€87.50m'·'free transfer'·'loan'·'-')을 화면 형식으로
export function feeLabel(feeEur: number | null | undefined, feeText?: string | null): string {
  const t = String(feeText ?? "").trim().toLowerCase();
  if (t.startsWith("end of loan")) return "임대 복귀";
  if (t.includes("loan fee")) return feeEur ? `임대 ${fmtEur(feeEur)}` : "임대";
  if (t.includes("loan")) return "임대";
  if (t.includes("free")) return "자유 이적";
  if (feeEur && feeEur > 0) return fmtEur(feeEur);
  if (!t || t === "-" || t === "?") return "비공개";
  return String(feeText);
}

// 적정 이적료(src/fee_comps.py) — 가운데 = 이적 직전 시장가치 × 사는 리그·나이 배수(이적 기록에서 학습), 범위 = 실제 이적료의
// 가운데 50%(lo~hi)·80%(lo80~hi80). basis 'ovr' = 시장가치가 없어 OVR·나이·리그로 추정(범위가 넓다).
export type FairBrief = { lo: number; mid: number; hi: number; basis: "mv" | "ovr"; mv_eur?: number | null };
export type FairComp = { player: string; age: number; ovr: number; pos: string; from: string; to: string; from_lg: string; to_lg: string;
  fee_eur: number; ratio: number | null; when: string; photo: string; dist: number };
export type FairPrice = FairBrief & { lo80: number; hi80: number; buyer: string | null; buyer_league: string | null; buyer_known: boolean;
  factors: { k: string; label: string; x: number; n: number }[];
  acc?: { med_err: number; within30?: number; in50?: number; in80?: number; mv_only_err?: number; n?: number } | null;
  comps: FairComp[] };

// '€25~47M' — 범위 한 덩어리(단위는 큰 쪽 기준, €10M 아래는 소수 한 자리)
export function fmtEurRange(lo: number, hi: number): string {
  if (!lo || !hi) return "-";
  if (hi >= 1e6) {
    const d = hi >= 1e7 ? 0 : 1;
    return `€${(lo / 1e6).toFixed(d)}~${(hi / 1e6).toFixed(d)}M`;
  }
  return `€${Math.round(lo / 1e3)}~${Math.round(hi / 1e3)}K`;
}

export function fmtEur(v: number): string {
  if (!v) return "-";
  if (v >= 1e9) return `€${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `€${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `€${Math.round(v / 1e3)}K`;
  return `€${Math.round(v)}`;
}

// 득점 구성(StatBunker) — 오픈플레이·세트피스·PK, 이번 시즌 vs 지난 시즌
export type GoalMixPart = { total: number; open: number; set_piece: number; pen: number; corner: number; games: number };
export type GoalMix = { cur: GoalMixPart | null; prev: GoalMixPart | null };

// 팀 시즌 기록(경기당 득점·실점·리그 순위) — /api/overview ovr.record (src/season_history.py)
export type TeamRecordRow = { season: string; label: string; w?: number; played: number; gf_pg: number; ga_pg: number;
  gf_z: number; ga_z: number; gf_rank: number; ga_rank: number; n: number };

// OVR 구성(단계별 기여)·평점 출처 — /api/player ovr_parts · ratings (src/ratings_v3.ovr_parts_of_row, rating_blend)
export type OvrPart = { key: string; en: string; ko: string; value: number };
export type RatingSources = { blend: number | null; sofascore: number | null; fotmob: number | null; fotmob_scaled: number | null;
  prev_blend: number | null; prev_sofascore: number | null; prev_fotmob: number | null; hist: number | null; prev_minutes: number | null;
  sofascore_minutes?: number | null; fotmob_minutes?: number | null; sofascore_share?: number | null };

// ── DATA STATUS (/status) — 에이전트 레지스트리 × 실행 원장 × watchdog ──
export type OpsState = "ok" | "warn" | "late" | "down" | "nodata";
export type OpsFeed = {
  key: string; label: string; state: OpsState; cadence: string; max_age_h: number; runners: string[]; outputs: string[];
  last_ok: string | null; last_run: string | null; age_h: number | null; failing: string[]; n_failing: number;
  down?: string[]; down_age_h?: number | null; runs_24h: number; fails_24h: number;
};
export type OpsAgent = { key: string; en: string; ko: string; does: string; sources: string[]; checks: string[]; extras: string[]; state: OpsState; feeds: OpsFeed[]; n_ok?: number; n_feeds?: number };
export type OpsFailure = { t: string; runner: string; step: string; league: string | null; code: number | null; sec: number; note?: string; agent: string | null };
export type OpsStatus = {
  generated: string; counts: Record<OpsState, number>; first_entry: string | null; agents: OpsAgent[];
  recent_failures: OpsFailure[]; unregistered_steps: string[];
  watchdog: { checked: string; results: Record<string, string[]>; ai_cause?: string } | null;
};
export const getOpsStatus = () => j<OpsStatus>("/api/ops/status");

// ── 국가대표(INTERNATIONAL) — A매치 기간·소집 명단(/api/intl/team) ──
export type IntlWindow = { start: string; first_match: string; end: string; matches: number; club_matches: number; kind: "break" | "tournament"; comps: string[]; label: string };
export type IntlFixture = { date: string; opp: string; home: boolean; comp: string; score: string | null };
export type IntlPlayer = {
  player: string; nation: string; conf: string; flag: string; fifa_rank: number | null; caps: number | null; goals: number | null;
  pos: string; squad_for: string | null; far: boolean; fixtures: IntlFixture[]; last_results: IntlFixture[];
};
export type IntlTeam = {
  window: IntlWindow | null; state: "now" | "upcoming" | "none"; days_to: number | null; last_window: IntlWindow | null;
  squad_state: "announced" | "previous" | "none"; players: IntlPlayer[]; summary: { n: number; far: number; nations: number };
};
export const getIntlTeam = (team: string, league: string = _league) =>
  j<IntlTeam>(`/api/intl/team/${encodeURIComponent(team)}?league=${encodeURIComponent(league)}`);

// ── INTERNATIONAL 허브(국가대표 탭) — 대회 자동 발견(src/intl_comps.py) · 대륙별 ──
export type IntlEdition = { season: string; start: string; end: string; matches: number; played: number;
  status: "upcoming" | "live" | "finished"; champion: string | null; runner_up: string | null };
export type IntlCompCard = { code: string; name: string; name_ko: string; conf: string;
  kind: "tournament" | "nations_league" | "qualifier" | "friendly"; kind_ko: string; edition: IntlEdition; editions: number };
export type IntlHub = { status: "live" | "soon" | "none"; today: string; window: IntlWindow | null; window_state: "now" | "upcoming" | "none";
  last_window: IntlWindow | null; live: IntlCompCard[]; next_tournament: IntlCompCard | null; today_matches: number;
  by_conf: { conf: string; en: string; ko: string; comps: IntlCompCard[] }[]; callups: number };
export type IntlMatch = { event_id: string; date: string; kickoff: string; comp_code: string; comp: string; conf: string; kind: string;
  stage: string; home: string; away: string; home_logo: string; away_logo: string; state: string; hg: number | null; ag: number | null;
  winner?: "home" | "away" | null; round?: string; group?: string; venue?: string; home_ko?: string; away_ko?: string };
export type IntlGroupRow = { team: string; team_ko?: string; logo: string; rank: number; p: number; w: number; d: number; l: number; gf: number; ga: number; gd: number; pts: number };
export type IntlGroup = { name: string; rows: IntlGroupRow[] };
// 대회 출전국의 우리 리그 선수(가장 최근 소집 명단) · 클럽 영향(대회 중 클럽 경기 수)
export type IntlNationPlayers = { nation: string; nation_ko: string; flag: string; fifa_rank: number | null; announced: boolean; squad_for: string;
  players: { player: string; club: string; league: string; pos: string; caps: number | null }[] };
export type IntlClubImpact = { club: string; league: string; logo: string; club_matches: number | null;
  players: { player: string; nation: string; nation_ko: string }[] };
export type IntlCompDetail = { available: boolean; code: string; name: string; name_ko: string; conf: string; kind: string; kind_ko: string;
  edition: IntlEdition; editions: { season: string; status: string; champion: string | null }[]; matches: IntlMatch[];
  groups?: IntlGroup[]; rounds?: { slug: string; en: string; ko: string; n: number }[];
  players?: IntlNationPlayers[]; club_impact?: IntlClubImpact[] };
// MY NATION — 한 나라 대표팀
export type IntlNationItem = { nation: string; nation_ko: string; flag: string; conf: string; fifa_rank: number | null; ours: number };
export type IntlNationMatch = { event_id: string; date: string; kickoff: string; comp_code: string; comp: string; kind: string; season: string;
  home: boolean; opp: string; opp_ko?: string; opp_logo: string; logo: string; score: string | null; state: string; result: "W" | "D" | "L" | null };
export type IntlNation = { nation: string; display: string; nation_ko: string; flag: string; conf: string; fifa_rank: number | null; squad_for: string;
  form: ("W" | "D" | "L" | null)[]; upcoming: IntlNationMatch[]; recent: IntlNationMatch[];
  tournaments: { code: string; name_ko: string; kind: string; kind_ko: string; edition: IntlEdition | null; group: IntlGroup | null; matches: number }[];
  squad: { player: string; club: string; league: string; ours: boolean; pos: string; caps: number | null; goals: number | null }[]; ours: number };
export const getIntlNations = () => j<{ nations: IntlNationItem[] }>(`/api/intl/nations`);
export const getIntlNation = (nation: string) => j<IntlNation>(`/api/intl/nation/${encodeURIComponent(nation)}`);
let _intlHub: Promise<IntlHub> | null = null;
export const getIntlHub = () => (_intlHub ??= j<IntlHub>(`/api/intl/hub`).catch((e) => { _intlHub = null; throw e; }));
export const getIntlMatches = (o: { scope?: "key" | "all"; when?: "upcoming" | "recent"; conf?: string; kind?: string; code?: string; limit?: number } = {}) =>
  j<{ matches: IntlMatch[] }>(`/api/intl/matches?${new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)])).toString()}`);
export const getIntlComp = (code: string, season = "") =>
  j<IntlCompDetail>(`/api/intl/comp/${encodeURIComponent(code)}${season ? `?season=${encodeURIComponent(season)}` : ""}`);

// ── 선수 뉴스(기사 선수 태그 — src/news_tags.py) ──
export type PlayerNewsItem = { headline: string; headline_en: string; source: string; published: string; link: string; image: string; how: string };
export const getPlayerNews = (player: string, club: string, league: string = _league) =>
  j<{ player: string; articles: PlayerNewsItem[]; total?: number }>(
    `/api/news-player/${encodeURIComponent(player)}?club=${encodeURIComponent(club)}&league=${encodeURIComponent(league)}&limit=5`);

// ── WEEKLY DIGEST(/api/digest) — 지난 7일 리그 변화(규칙 기반) ──
export type DigestMover = { player: string; squad: string; ovr: number; ovr_delta: number; form: number; delta: number };
export type DigestInj = { player: string; squad: string; date: string; ovr: number | null; injury: string; until: string | null };
export type Digest = {
  league: string; since: string; until: string; form_since?: string;
  risers: DigestMover[]; fallers: DigestMover[];
  injuries: { new: DigestInj[]; back: DigestInj[]; n_new: number; n_back: number };
  news: { player: string; squad: string; articles: number; ovr: number | null }[];
  rumors: { n: number; clubs: { club: string; n: number }[]; top: { player: string; from: string; to: string; value_eur: number | null }[] };
  intl?: IntlWindow & { days_to: number };
  summary?: { text: string; at: string; until: string } | null;   // AI 서술 한 문단(daily_data)
};
export const getDigest = (league: string = _league) => j<Digest>(`/api/digest?league=${encodeURIComponent(league)}`);
