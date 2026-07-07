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

export type Star = { player: string; pos: string; ovr: number; pot?: number; form?: number | null; rating: number; goals: number; assists: number; photo: string; role?: string; big_match?: boolean };
export type Injury = { player: string; injury: string; until: string; pos: string; photo: string };
export type Window = { season_id: number; window: string; label: string; state: string; is_open: boolean; kr: string | null };

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
  ovr: { overall: number; attack: number; midfield: number; defense: number; top_xi?: number };
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
  squad_ratings: { player: string; ovr: number; pot: number; form: number | null; age: number; minutes: number; line: string }[];
  leaders: { label: string; player: string; photo: string; value: number }[];
  departed: { player: string; left_for: string; pos: string; photo: string }[];
  injuries: Injury[];
  transfers: { in: Transfer[]; out: Transfer[] };
  window: Window;
  data_season: string;
};

export type CalEvent = { name: string; start: string; end: string; icon: string; kind: string };

export type Placement = { slot: string; player: string; x: number; y: number; kind: string; ovr: number | null; photo: string; changed?: boolean; in?: boolean; out?: string };
export type Lineup = {
  team: string; color: string;
  season: { formation: string; placements: Placement[] };
  recent: { formation: string; placements: Placement[] } | null;
  bench: { player: string; pos: string; ovr: number; photo: string }[];
};

async function j<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
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
  candidate: string; club?: string; role: string;
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

// ── Ask Scout (자연어 라우팅 · 로컬 전용 · OpenAI) ──
// result 는 intent 에 따라 Recommend|Fit|ManagerSim|{results}|Identity 중 하나(느슨하게).
export type Scout = {
  available: boolean; reason?: string; error?: string; auth_required?: boolean;
  intent?: string | null; args?: Record<string, unknown>;
  answer?: string;
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
  value_eur: number; ovr: number; photo: string; goals: number; assists: number;
};
export type DepthPlayer = { player: string; ovr: number; minutes: number; age: number; photo: string };
export type Bucket = { pos: string; count: number; depth: number; starter: DepthPlayer; rotation: DepthPlayer[] };
export type Squad = { team: string; color: string; lines: Record<string, SquadPlayer[]>; buckets: Bucket[] };

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
  role: string; big_match: boolean; comps: CompUse[];
};
export type Players = { team: string; color: string; players: PlayerCard[] };

export type MetricBar = { label: string; pct: number; raw: number };
export type MetricCat = { name: string; avg: number; metrics: MetricBar[] };
export type Badge = { label: string; rank: number; medal: string };
export type PlayerDetail = {
  player: string; team: string; color: string; pos: string; line: string;
  age: number; nationality: string; value_eur: number; photo: string;
  ovr: number; ss_rating: number; minutes: number; goals: number; assists: number;
  contract_until: string; is_gk: boolean;
  categories: MetricCat[];
  radar: { axis: string; value: number }[];
  badges: Badge[];
  comp_usage: CompProfile;
};

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
};
export type News = { team: string; color: string; articles: Article[]; sparse: boolean };

export type AuditItem = { player: string; fee_text: string; fee_eur: number; pos: string; minutes: number; goals: number; assists: number; verdict: string; tone: string; photo: string };
export type ManagerEvo = { name: string; style: string; formation: string; focus: string; appointed: string; previous?: { name: string; style: string; formation: string } };
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
export type Longshot = { player: string; squad: string; logo: string; ovr: number; pos: string; photo: string; role: string; bucket_label: string; reason: string; cross_league?: boolean; source_league?: string; current_ovr?: number };
export type Recommend = { team: string; color: string; weakest: { line: string; label: string; fit_label: string; bucket?: string; bucket_label?: string } | null; addressed: boolean; recommendations: Recommendation[]; longshots?: Longshot[]; lost_targets: LostTarget[] };

const q = (team: string, league: string) =>
  `${encodeURIComponent(team)}?league=${encodeURIComponent(league)}`;

export const getSquad = (t: string, l = _league) => j<Squad>(`/api/squad/${q(t, l)}`);

// ── 스쿼드 네트워크 (KG TEAMMATE_OF) ──
export type SGNode = { id: string; name: string; pos: string; line: string; rating: number | null };
export type SGEdge = { a: string; b: string; matches: number };
export type SquadGraphData = { available: boolean; reason?: string; error?: string; team?: string; nodes: SGNode[]; edges: SGEdge[] };
export const getSquadGraph = (t: string, l = _league) => j<SquadGraphData>(`/api/squad-graph/${q(t, l)}`);
export const getSchedule = (t: string, season = "", l = _league) => j<Schedule>(`/api/schedule/${q(t, l)}${season ? `&season=${season}` : ""}`);
export const getMatch = (t: string, eid: string, l = _league) =>
  j<MatchDetail>(`/api/match/${encodeURIComponent(t)}/${encodeURIComponent(eid)}?league=${encodeURIComponent(l)}`);
export const getPlayers = (t: string, l = _league) => j<Players>(`/api/players/${q(t, l)}`);
export const getPlayerDetail = (t: string, p: string, l = _league) =>
  j<PlayerDetail>(`/api/player/${encodeURIComponent(t)}/${encodeURIComponent(p)}?league=${encodeURIComponent(l)}`);
export const getTransfers = (t: string, l = _league) => j<Transfers>(`/api/transfers/${q(t, l)}`);
export const getNews = (t: string, l = _league) => j<News>(`/api/news/${q(t, l)}`);
export const getAnalytics = (t: string, l = _league) => j<Analytics>(`/api/analytics/${q(t, l)}`);
export const getCalendar = () => j<{ events: CalEvent[] }>(`/api/calendar`);
export const getLineup = (t: string, l = _league) => j<Lineup>(`/api/lineup/${q(t, l)}`);
export type Diag = { kind: string; severity: string; player: string; slot: string; line: string; to?: string; fee?: string; replacement: string; note: string; photo: string };
export type Projection = {
  team: string; color: string; current_label: string; next_label: string;
  current: { formation: string; placements: Placement[] };
  projected: { formation: string; placements: Placement[] };
  diagnosis: Diag[];
};
export const getProjection = (t: string, l = _league) => j<Projection>(`/api/projection/${q(t, l)}`);
export type Captain = { name: string; photo: string; ovr: number | null; pos: string; role: string; is_main: boolean };
export const getCaptains = (t: string, l = _league) =>
  j<{ team: string; color: string; captains: Captain[] }>(`/api/captains/${q(t, l)}`);
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
};
export type Discover = {
  available: boolean; reason?: string; error?: string;
  team?: string; target_league?: string; target_roles?: string[];
  kpi?: { count: number; avg_age: number | null; avg_value: number | null; leagues: string[] };
  recommendations: DiscoverPick[];
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
export type Needs = { team: string; color: string; mode: string; window: NeedsWindow; needs: NeedItem[] };
export const getNeeds = (t: string, l = _league) => j<Needs>(`/api/needs/${q(t, l)}`);
export const getContext = () => j<Context>(`/api/context`);

export type DbPlayer = { player: string; squad: string; league: string; logo: string; pos: string; line: string; age: number; nationality: string; value_eur: number; ovr: number; photo: string; role: string; big_match: boolean };
type DbResp = { league: string; players: DbPlayer[]; nationalities: string[]; leagues: string[] };
// 세션 내 캐시 — DB 는 세션 중 불변. 탭 재방문 시 재요청 없이 즉시(대용량 전리그 목록).
let _dbCache: Promise<DbResp> | null = null;
export const getDatabase = () => (_dbCache ??= j<DbResp>(`/api/database`).catch((e) => { _dbCache = null; throw e; }));

export type Signal = { date: string; team: string; logo: string; type: string; tone: string; icon: string; player: string; photo: string; title: string; detail: string };
export type Signals = { team: string; window: Window; counts: Record<string, number>; signals: Signal[] };
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
export type HomeAll = { window: Context["window"]; leagues: { key: string; name: string }[]; top_deals: HubDeal[]; buzz: HubBuzz[]; manager_changes: HubChange[]; snapshots: HubSnapshot[]; injuries: HubInjury[]; hot_form: HubForm[]; goal_leaders: HubGoal[]; prospects: HubForm[]; veterans: HubForm[]; value_picks: HubValue[]; risers: HubRiser[]; contracts: HubContract[] };
export const getHomeAll = () => j<HomeAll>(`/api/home/all`);
export type WCSquadPlayer = { player: string; pos: string; jersey: string; age: string; club: string; league: string; club_logo: string; photo: string };
export type WCSquad = { nation: string; count: number; players: WCSquadPlayer[] };
export const getWCSquad = (nation: string) => j<WCSquad>(`/api/wc/squad/${encodeURIComponent(nation)}`);

export function fmtEur(v: number): string {
  if (!v) return "-";
  if (v >= 1e6) return `€${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `€${Math.round(v / 1e3)}K`;
  return `€${Math.round(v)}`;
}
