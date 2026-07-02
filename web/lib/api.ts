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

export type Star = { player: string; pos: string; ovr: number; pot?: number; rating: number; goals: number; assists: number; photo: string };
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
  squad_ratings: { player: string; ovr: number; pot: number; age: number; minutes: number; line: string }[];
  leaders: { label: string; player: string; photo: string; value: number }[];
  departed: { player: string; left_for: string; pos: string; photo: string }[];
  injuries: Injury[];
  transfers: { in: Transfer[]; out: Transfer[] };
  window: Window;
  data_season: string;
};

export type CalEvent = { name: string; start: string; end: string; icon: string; kind: string };

export type Placement = { slot: string; player: string; x: number; y: number; kind: string; ovr: number | null; photo: string; changed?: boolean };
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

// ── 탭별 타입 ─────────────────────────────
export type SquadPlayer = {
  player: string; pos: string; age: number; minutes: number;
  value_eur: number; ovr: number; photo: string; goals: number; assists: number;
};
export type DepthPlayer = { player: string; ovr: number; minutes: number; age: number; photo: string };
export type Bucket = { pos: string; count: number; depth: number; starter: DepthPlayer; rotation: DepthPlayer[] };
export type Squad = { team: string; color: string; lines: Record<string, SquadPlayer[]>; buckets: Bucket[] };

export type Match = {
  gw: number; date: string; home_away: string; opponent: string; opp_logo: string;
  gf: number | null; ga: number | null; score: string; result: string;
  event_id: string | null; formation: string | null;
};
export type Schedule = { team: string; color: string; matches: Match[] };
export type MatchDetail = {
  team: string; color: string; event_id: string; formation: string; home_away: string;
  placements: Placement[]; subs: { minute: string; player_in: string; player_out: string }[]; bench: string[];
};

export type PlayerCard = {
  player: string; pos: string; line: string; age: number;
  nationality: string; value_eur: number; ovr: number; photo: string;
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

export type AuditItem = { player: string; fee_text: string; fee_eur: number; pos: string; minutes: number; goals: number; assists: number; verdict: string; tone: string };
export type ManagerEvo = { name: string; style: string; formation: string; focus: string; appointed: string; previous?: { name: string; style: string; formation: string } };
export type FactorPlayer = { player: string; photo: string; ovr: number };
export type Factor = { label: string; value: number; line: string; players: FactorPlayer[] };
export type Analytics = {
  team: string; color: string;
  ovr: { overall: number; form: number; attack: number; midfield: number; defense: number; set_piece: number };
  radar: { axis: string; value: number }[];
  injuries: { player: string; games_missed: number; days_out: number; injury: string; line: string }[];
  line_missed: Record<string, number>;
  line_share: Record<string, number>;
  context: { home_ppg: number; away_ppg: number; tier_ppg: { top: number; mid: number; bottom: number } };
  factors: { strengths: Factor[]; weaknesses: Factor[] };
  transfer_summary: { spend: number; income: number; in_count: number; out_count: number };
  audit: AuditItem[];
  manager_evo: ManagerEvo | null;
};

export type SimilarResult = { player: string; squad: string; pos: string; age: number; value_eur: number; logo: string; score: number; style: number; perf: number };
export type Recommendation = { player: string; squad: string; logo: string; pos: string; age: number; ovr: number; value_eur: number; photo: string; rating: number; tactical_fit: number; squad_match: number; why_fit: string[]; why_risk: string[]; confidence: string };
export type LostTarget = { player: string; from: string; to: string; ovr: number; pos: string; photo: string };
export type Recommend = { team: string; color: string; weakest: { line: string; label: string; fit_label: string } | null; addressed: boolean; recommendations: Recommendation[]; lost_targets: LostTarget[] };

const q = (team: string, league: string) =>
  `${encodeURIComponent(team)}?league=${encodeURIComponent(league)}`;

export const getSquad = (t: string, l = _league) => j<Squad>(`/api/squad/${q(t, l)}`);
export const getSchedule = (t: string, l = _league) => j<Schedule>(`/api/schedule/${q(t, l)}`);
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

// ── 스카우트 데스크 (Needs Board) ──
export type NeedItem = { line: string; line_label: string; kind: string; title: string; severity: string; reason: string; status: string; player: string | null };
export type NeedsWindow = { is_open: boolean; label: string; kr: string | null; signings: { player: string; line: string; pos: string; fee: string }[]; departures: { player: string; line: string; pos: string }[] };
export type Needs = { team: string; color: string; mode: string; window: NeedsWindow; needs: NeedItem[] };
export const getNeeds = (t: string, l = _league) => j<Needs>(`/api/needs/${q(t, l)}`);
export const getContext = () => j<Context>(`/api/context`);

export type DbPlayer = { player: string; squad: string; logo: string; pos: string; line: string; age: number; nationality: string; value_eur: number; ovr: number; photo: string };
export const getDatabase = (l = _league) => j<{ league: string; players: DbPlayer[]; nationalities: string[] }>(`/api/database?league=${encodeURIComponent(l)}`);

export type Signal = { date: string; team: string; logo: string; type: string; tone: string; icon: string; player: string; photo: string; title: string; detail: string };
export type Signals = { team: string; window: Window; counts: Record<string, number>; signals: Signal[] };
export const getSignals = (team = "", l = _league, limit = 60) =>
  j<Signals>(`/api/signals?team=${encodeURIComponent(team)}&league=${encodeURIComponent(l)}&limit=${limit}`);

// ── 홈 대시보드 ──
export type HomeDeal = { player: string; to: string; to_logo: string; from: string; pos: string; fee_eur: number; fee_text: string };
export type HomeNet = { team: string; logo: string; spend: number; income: number; net: number };
export type HomeMgr = { team: string; logo: string; previous: string; current: string; photo: string; formation: string; changed_at: string };
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
export type WCClubPlayer = { player: string; nation: string; pos: string; photo: string; goals: number };
export type WCClub = { club: string; logo: string; count: number; players: WCClubPlayer[] };
export type WCNation = { nation: string; logo: string; count: number };
export type WorldCupData = { matches: WCRound[]; groups: WCGroup[]; scorers: WCScorer[]; epl_clubs: WCClub[]; nations: WCNation[] };
export const getWC = () => j<WorldCupData>(`/api/wc`);
export type WCSquadPlayer = { player: string; pos: string; jersey: string; age: string; epl_club: string; club_logo: string; photo: string };
export type WCSquad = { nation: string; count: number; players: WCSquadPlayer[] };
export const getWCSquad = (nation: string) => j<WCSquad>(`/api/wc/squad/${encodeURIComponent(nation)}`);

export function fmtEur(v: number): string {
  if (!v) return "-";
  if (v >= 1e6) return `€${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `€${Math.round(v / 1e3)}K`;
  return `€${Math.round(v)}`;
}
