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
    photo?: string; bio?: string; tactics?: string;
    previous?: { name: string; left_date: string };
    changed_at?: string;
  } | null;
  edge: { strengths: { label: string; value: number }[]; weaknesses: { label: string; value: number }[] };
  snapshot: { open_play: number; set_piece: number; penalty: number; yellows: number; reds: number; yellow_per_match: number } | null;
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

export type Placement = { slot: string; player: string; x: number; y: number; kind: string; ovr: number | null; photo: string; changed?: boolean; in?: boolean; out?: string; club?: string };
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

async function j<T>(url: string): Promise<T> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(url, { cache: "no-store", signal: ctl.signal });
    if (!res.ok) throw new Error(`${res.status} ${url}`);
    noteDataVersion(res.headers.get("x-data-version"));
    return res.json();
  } finally {
    clearTimeout(timer);
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
export const getBuilder = (t: string, l = _league) => j<{ team: string; color: string; players: BuilderPlayer[] }>(`/api/builder/${q(t, l)}`);
export type LoanOut = { player: string; club: string; pos: string; nat: string; photo: string; source: string; minutes: number | null; ovr: number | null };
export type Squad = { team: string; color: string; lines: Record<string, SquadPlayer[]>; buckets: Bucket[]; loans?: LoanOut[] };

export type Match = {
  gw?: number; comp: string; date: string; home_away: string; opponent: string; opp_logo: string;
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

export type MetricBar = { label: string; pct: number; raw: number };
export type MetricCat = { name: string; avg: number; metrics: MetricBar[] };
export type Badge = { label: string; rank: number; medal: string };
export type PlayerDetail = {
  player: string; team: string; color: string; pos: string; line: string;
  age: number; nationality: string; value_eur: number; photo: string;
  ovr: number; ss_rating: number; minutes: number; goals: number; assists: number;
  contract_until: string; is_gk: boolean; trend?: Trend;
  ovr_parts?: OvrPart[]; ratings?: RatingSources; form?: number | null; recent?: RecentForm | null;
  categories: MetricCat[];
  radar: { axis: string; value: number }[];
  badges: Badge[];
  comp_usage: CompProfile;
  value_history: { date: string; value_eur: number }[];
  peers: { line: string; n: number };
  season_log?: SeasonLog;
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
};
export type News = { team: string; color: string; articles: Article[]; sparse: boolean;
  ai?: { lines: string[]; at: string; n?: number } | null };   // 최근 48시간 AI 요약 1~3줄

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

export type SimilarResult = { player: string; squad: string; pos: string; age: number; value_eur: number; logo: string; score: number; style: number; perf: number };
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
export const getPlayerDetail = (t: string, p: string, l = _league) =>
  j<PlayerDetail>(`/api/player/${encodeURIComponent(t)}/${encodeURIComponent(p)}?league=${encodeURIComponent(l)}`);
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
  leadership: { captains: NetCaptain[]; armband: string | null; core: NetCore[]; influence: Record<string, number> };
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
export const getSimilar = (p: string, l = _league) =>
  j<{ player: string; results: SimilarResult[] }>(`/api/similar/${encodeURIComponent(p)}?league=${encodeURIComponent(l)}`);
export const getRecommend = (t: string, l = _league) => j<Recommend>(`/api/recommend/${q(t, l)}`);

// ── 벡터(Qdrant) 스타일-핏 교차리그 발굴 + KG 신호 (로컬 전용) ──
export type DiscoverPick = {
  player: string; squad: string; pos: string; ovr: number; current_ovr: number; projected_ovr: number;
  cross_league: boolean; source_league: string; value_eur: number | null; style_fit: number;
  euro: boolean; age: number | null; photo: string; why_fit: string[];
  goals?: number; assists?: number; rating?: number;
  price_verdict?: string; likely_fee_eur?: number | null; recruit_fit?: number; contract_until?: string;
  kg_rumored?: boolean; kg_rumor_prob?: number | null; kg_precedent?: number;
  policy_ok?: boolean | null; policy_notes?: string[];   // 구단 이적 정책(나이·이적료) 대조
  realistic?: boolean;   // 경쟁 팀·강팀 핵심 주전이면 false(영입 가능성 낮음)
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
export type Inbox = { team: string; briefing: InboxMsg[]; messages: InboxMsg[]; counts: Record<string, number>; league_events: Signal[]; generated: string };
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
export type HubChange = { team: string; logo: string; previous: string; current: string; photo: string; changed_at: string; league: string; league_name: string };
export type HubSnapRow = { rank: number; team: string; logo: string; points: number };
export type HubSnapshot = { league: string; league_name: string; color: string; table: HubSnapRow[] };
export type HubForm = { player: string; club: string; club_logo: string; rating: number; ovr: number; pos: string; age: number; photo: string; league: string; league_name: string };
export type HubValue = HubForm & { value_eur: number };
export type HubRiser = { player: string; club: string; club_logo: string; value_eur: number; delta_eur: number; pct: number; photo: string; league: string; league_name: string };
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
  summary?: { spend_eur: number; signings: number; manager_changes: number; injured: number }; generated_at?: string };
export const getHomeAll = () => j<HomeAll>(`/api/home/all`);
// 매치 센터 — 다가오는 경기·빅매치(src/match_center.py). kst 는 한국 시간 표기, d_day 는 오늘 기준.
export type FixtureSide = { team: string; league: string | null; rank: number | null; points: number | null;
  logo: string; color: string; ovr: number | null; form: string[] };
// 승리 확률 — 팀 OVR 차이 + 경기당 골득실 → 포아송 모델(src/match_center.win_prob). 베팅 배당 아님.
export type WinProb = { h: number; d: number; a: number; xg_h: number; xg_a: number };
// 외부 예측 — fans = Sofascore 팬 투표(n 표, BTTS·선제골 투표 포함), elo = ClubElo 독립 Elo 모델
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
// 예측 성적표 — 팬 투표 vs 우리 모델 vs ClubElo(/api/prediction-league, 원천 data/predictions_log.csv)
export type PredScore = { key: "fans" | "model" | "elo"; en: string; kr: string; n: number; acc: number | null; brier: number | null; logloss: number | null; hits: number };
export type PredPick = { pick: "H" | "D" | "A"; p: number } | null;
export type PredRecent = { event_id: string; date: string; home: string; away: string; home_logo: string; away_logo: string; hg: number; ag: number;
  result: "H" | "D" | "A"; fans: PredPick; model: PredPick; elo: PredPick };
export type PredSplit = { event_id: string; date: string; home: string; away: string; home_logo: string; away_logo: string; fans: PredPick; model: PredPick; gap: number };
type PredStat = Omit<PredScore, "key" | "en" | "kr">;
// common: 세 출처가 모두 예측한 같은 경기 맞대결(rank = 적중률 → 브라이어) · v3: 같은 경기를 모델 v3 로(이전 경기는 재계산, 참고)
export type PredictionLeague = { available: boolean; since?: string; sources: PredScore[];
  h2h: { n: number; fans: PredStat; model: PredStat } | null; recent: PredRecent[]; split: PredSplit[];
  common?: { n: number; scores: Record<string, PredStat>; rank: string[]; v3: PredStat | null; v3_live: number } | null;
  model_versions?: Record<string, number>; v3_since?: string | null };
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
export const getTeamFixtures = (team: string, l = _league) =>
  j<{ team: string; next: Fixture[] }>(`/api/fixtures/${encodeURIComponent(team)}?league=${encodeURIComponent(l)}`);
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
  prev_blend: number | null; prev_sofascore: number | null; prev_fotmob: number | null; hist: number | null; prev_minutes: number | null };

// ── DATA STATUS (/status) — 에이전트 레지스트리 × 실행 원장 × watchdog ──
export type OpsState = "ok" | "warn" | "late" | "nodata";
export type OpsFeed = {
  key: string; label: string; state: OpsState; cadence: string; max_age_h: number; runners: string[]; outputs: string[];
  last_ok: string | null; last_run: string | null; age_h: number | null; failing: string[]; n_failing: number;
  runs_24h: number; fails_24h: number;
};
export type OpsAgent = { key: string; en: string; ko: string; does: string; sources: string[]; checks: string[]; extras: string[]; state: OpsState; feeds: OpsFeed[] };
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
