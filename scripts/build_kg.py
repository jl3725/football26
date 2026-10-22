"""football26 지식그래프(KG) 적재 — CSV → Neo4j (멱등 MERGE, 증분).

노드:  League, Country, Club, Player(id=tm_id), Manager, TransferEvent, Competition
관계:  (League)-[:IN_COUNTRY]->(Country)
       (Club)-[:COMPETES_IN]->(League)
       (Player)-[:PLAYS_FOR]->(Club)
       (Player)-[:REPRESENTS]->(Country)              # 국적/대표팀
       (Player)-[:TEAMMATE_OF {matches}]-(Player)     # 같은 경기 선발 공유(espn_lineups)
       (Player)-[:PLAYED_IN {starts,apps}]->(Competition)  # UCL/UEL/ECL 유럽 경험
       (Manager)-[:MANAGES]->(Club)
       (TransferEvent)-[:OF]->(Player) / -[:FROM]->(Club) / -[:TO]->(Club)
       (Player)-[:CAPTAIN_OF {rank, role}]->(Club)      # 주장단(위키 스쿼드 표)
       (Player)-[:MENTIONED_WITH {articles, last}]-(Player)  # 최근 60일 같은 기사에 함께 나옴(뉴스 선수 태그)
       (Player)-[:CALLED_UP {squad_for, caps, goals}]->(Country)  # 대표팀 소집(위키 Current squad)
       (Player)-[:LINKED_TO {heat, stage, tm_prob, news, outlets, last}]->(Club)  # 이적설(TM 루머 + 뉴스, src/rumor_map.py)
       (Claim {player, dest, window, stage, first, last, n, status})-[:ABOUT]->(Player) / -[:TO_CLUB]->(Club) / -[:FROM_CLUB]->(Club)
         (이적 기록의 TO·FROM 과 이름을 나눠 — 라벨 없이 쓴 질의가 주장과 실제 이적을 섞지 않게)
       (Outlet|Journalist)-[:REPORTED {first, last, n, stage}]->(Claim)   # 이적 루머 주장(뉴스 → data/news_claims.csv)
       (Journalist)-[:WRITES_FOR {n}]->(Outlet)
         주장 = 선수·행선지·이적 시장 하나. status = hit·miss(닫힌 시장 판정)·pending. Outlet·Journalist 에 적중률(rate·score·n)
속성 보강: Player(contract_until·career_games_missed·career_spells·ovr·form·recent·xg_p90·influence·
          captain_rank·injured_now·news_60d·active), Club(europe_coefficient), Country(fifa_rank·fifa_points)
골·도움·출전 분·OVR 은 화면과 같은 선수 표(api/services/player_data.player_frame — FotMob·Understat 매일 반영)에서.

정리(2026-10-20): MERGE 만 하던 때는 팀을 떠난 선수의 PLAYS_FOR·바뀐 감독의 MANAGES 가 남았다. 이번 실행에서
다시 확인된 관계에 seen=실행 시각을 달고, 못 본 PLAYS_FOR·MANAGES·CAPTAIN_OF·MENTIONED_WITH·CALLED_UP·LINKED_TO 는 지운다.
이번에 안 보인 선수 노드는 지우지 않고 active=false(이적 기록이 가리키므로).
주간 자동 재적재: .github/workflows/kg_reload.yml

접속(기본 로컬 docker): NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD.
사용:  pip install -r requirements-kg.txt && python scripts/build_kg.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys
from itertools import combinations
from pathlib import Path

import pandas as pd
from unidecode import unidecode

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from leagues import data_path  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME") or "neo4j"
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "football26")

LEAGUE_META = {
    "EPL": ("Premier League", "England", 100.0),
    "LaLiga": ("La Liga", "Spain", 95.5),
    "SerieA": ("Serie A", "Italy", 96.1),
    "Bundesliga": ("Bundesliga", "Germany", 94.7),
    "Ligue1": ("Ligue 1", "France", 92.8),
    "LigaPortugal": ("Liga Portugal", "Portugal", 90.7),
    "Eredivisie": ("Eredivisie", "Netherlands", 88.5),
    "BelgianProLeague": ("Belgian Pro League", "Belgium", 87.5),
}
try:   # 라이트 리그(챔피언십 …, 2026-10-22) — 이름·나라는 리그 설정, 수준은 league_level(UEFA 계수·시장가치 직선)
    from leagues import LEAGUES as _LG  # noqa: E402
    import league_level as _ll  # noqa: E402
    LEAGUE_META.update({k: (c.name, c.country, _ll.level(k)) for k, c in _LG.items() if k not in LEAGUE_META})
except ImportError:
    pass
# comp_usage 컬럼 → Competition 노드(유럽대항전 = 스카우팅 검증 신호)
EURO_COMPS = [("ucl", "UEFA Champions League"), ("uel", "UEFA Europa League"),
              ("conf", "UEFA Conference League")]

CONSTRAINTS = [
    "CREATE CONSTRAINT player_id IF NOT EXISTS FOR (p:Player) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT club_name IF NOT EXISTS FOR (c:Club) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT league_key IF NOT EXISTS FOR (l:League) REQUIRE l.key IS UNIQUE",
    "CREATE CONSTRAINT country_name IF NOT EXISTS FOR (n:Country) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT manager_name IF NOT EXISTS FOR (m:Manager) REQUIRE m.name IS UNIQUE",
    "CREATE CONSTRAINT transfer_id IF NOT EXISTS FOR (t:TransferEvent) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT competition_name IF NOT EXISTS FOR (x:Competition) REQUIRE x.name IS UNIQUE",
    "CREATE CONSTRAINT claim_id IF NOT EXISTS FOR (k:Claim) REQUIRE k.id IS UNIQUE",
    "CREATE CONSTRAINT outlet_name IF NOT EXISTS FOR (o:Outlet) REQUIRE o.name IS UNIQUE",
    "CREATE CONSTRAINT journalist_name IF NOT EXISTS FOR (j:Journalist) REQUIRE j.name IS UNIQUE",
]
CLAIM_DAYS = 400         # 주장 보관 — 지난 시장 적중 판정까지(무료 AuraDB 20만 노드 한도 안에서 수천 개)


def _norm(s) -> str:
    return unidecode(str(s or "")).lower().strip()


# Transfermarkt 세부 포지션 약어 → 정식명
TM_POS_NORM = {
    "CB": "Centre-Back", "RB": "Right-Back", "LB": "Left-Back", "RWB": "Right-Back",
    "LWB": "Left-Back", "DM": "Defensive Midfield", "CM": "Central Midfield",
    "AM": "Attacking Midfield", "RM": "Right Midfield", "LM": "Left Midfield",
    "RW": "Right Winger", "LW": "Left Winger", "CF": "Centre-Forward",
    "SS": "Second Striker", "GK": "Goalkeeper",
}


def _pos_detail(v):
    v = _clean(v)
    if v is None:
        return None
    s = str(v).strip()
    return TM_POS_NORM.get(s, s) or None


def _clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return v


def _num(v):
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _pid(tm, nk, league) -> str | None:
    if tm is not None and pd.notna(tm):
        try:
            return f"tm:{int(tm)}"
        except (TypeError, ValueError):
            pass
    nk = _clean(nk)
    return f"nk:{league}:{_norm(nk)}" if nk else None


def _players_and_map(league: str):
    """players_full → (player rows, norm(name)->pid 맵). 계약·역할·국적 포함."""
    try:
        df = pd.read_csv(data_path("players_full", league))
    except (OSError, ValueError):
        return [], {}
    rows, n2p = [], {}
    for _, r in df.iterrows():
        nm = _clean(r.get("player"))
        pid = _pid(r.get("tm_id"), r.get("norm_key"), league)
        if not pid or not nm:
            continue
        nat = _clean(r.get("nationality"))
        nat = str(nat).split("/")[0].split(",")[0].strip() if nat else None
        rows.append({
            "id": pid, "name": str(nm), "club": str(r.get("squad") or ""),
            "pos": _clean(r.get("pos")), "pos_detail": _pos_detail(r.get("tm_position")),
            "age": _num(r.get("age")), "nat": nat,
            "mv": _num(r.get("market_value_eur")), "ss": _num(r.get("ss_rating")),
            "goals": _num(r.get("goals")), "assists": _num(r.get("assists")),
            "minutes": _num(r.get("minutes")),
            "contract_until": (str(r.get("tm_contract_until"))[:10]
                               if _clean(r.get("tm_contract_until")) else None),
        })
        key = _norm(r.get("norm_key") or nm)
        n2p.setdefault(key, pid)
        n2p.setdefault(_norm(nm), pid)
    return rows, n2p


def _load_managers(league: str) -> list[dict]:
    try:
        d = json.loads(data_path("manager_profiles", league, ext="json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [{"name": str((p or {}).get("name")).strip(), "club": club,
             "nationality": _clean((p or {}).get("nationality")),
             "formation": _clean((p or {}).get("formation"))}
            for club, p in d.items() if (p or {}).get("name") and str((p or {}).get("name")).strip()]


def _load_transfers(league: str) -> list[dict]:
    try:
        df = pd.read_csv(data_path("transfers", league))
    except (OSError, ValueError):
        return []
    rows = []
    for _, r in df.iterrows():
        if str(r.get("direction")) != "in":
            continue
        player, to, frm = str(r.get("player") or ""), str(r.get("squad") or ""), str(r.get("club") or "")
        if not player or not to:
            continue
        season = str(r.get("season") or "")
        rows.append({"id": f"{league}:{season}:{player}:{frm}->{to}", "player": player,
                     "to": to, "from": frm, "fee_eur": _num(r.get("fee_eur")),
                     "fee_text": _clean(r.get("fee_text")), "window": _clean(r.get("window")),
                     "season": season})
    return rows


def _load_teammates(league: str, n2p: dict) -> list[dict]:
    """espn_lineups(+컵) → 같은 (경기·팀) 선발 공유 페어 카운트 → TEAMMATE_OF."""
    frames = []
    for stem in ("espn_lineups", "espn_lineups_cups"):
        try:
            frames.append(pd.read_csv(data_path(stem, league)))
        except (OSError, ValueError):
            pass
    if not frames:
        return []
    lu = pd.concat(frames, ignore_index=True)
    if not {"event_id", "squad", "player"}.issubset(lu.columns):
        return []
    if "starter" in lu.columns:
        lu = lu[lu["starter"].astype(str).str.lower().isin(["true", "1", "yes"])]
    pair: dict = {}
    for (_ev, _sq), g in lu.groupby(["event_id", "squad"]):
        pids = {n2p.get(_norm(p)) for p in g["player"].tolist()}
        pids.discard(None)
        for a, b in combinations(sorted(pids), 2):
            pair[(a, b)] = pair.get((a, b), 0) + 1
    return [{"a": a, "b": b, "m": c} for (a, b), c in pair.items()]


def _load_comp_played(league: str, n2p: dict) -> list[dict]:
    """player_comp_usage → 유럽대항전 출전(PLAYED_IN)."""
    try:
        df = pd.read_csv(data_path("player_comp_usage", league))
    except (OSError, ValueError):
        return []
    rows = []
    for _, r in df.iterrows():
        pid = n2p.get(_norm(r.get("norm_key") or r.get("player")))
        if not pid:
            continue
        for pfx, comp in EURO_COMPS:
            st = _num(r.get(f"{pfx}_starts")) or 0
            ap = _num(r.get(f"{pfx}_apps")) or 0
            if st > 0 or ap > 0:
                rows.append({"pid": pid, "comp": comp, "starts": int(st), "apps": int(ap)})
    return rows


def _load_injuries(league: str) -> list[dict]:
    """tm_injury_history → 선수별 통산 결장경기·스펠 합계(tm_player_id=tm_id 기준)."""
    try:
        df = pd.read_csv(data_path("tm_injury_history", league))
    except (OSError, ValueError):
        return []
    if "tm_player_id" not in df.columns:
        return []
    agg = {}
    for _, r in df.iterrows():
        tid = _clean(r.get("tm_player_id"))
        if tid is None:
            continue
        pid = f"tm:{int(tid)}"
        a = agg.setdefault(pid, {"pid": pid, "gm": 0, "sp": 0})
        a["gm"] += int(_num(r.get("games_missed")) or 0)
        a["sp"] += int(_num(r.get("spells")) or 0)
    return list(agg.values())


def _load_reps(players: list[dict]) -> list[dict]:
    return [{"pid": p["id"], "country": p["nat"]} for p in players if p.get("nat")]


RUN = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
_API = {}


def _live(league: str) -> dict[str, dict]:
    """pid → 화면 선수 표 값(OVR·폼·최근 폼·골·도움·분·xG/90). 표를 못 만들면 빈 dict(CSV 값 유지)."""
    try:
        from api.services.player_data import player_frame  # noqa: PLC0415
        f = player_frame(league)
    except Exception as e:  # noqa: BLE001
        print(f"  ! {league} 선수 표 실패({type(e).__name__}) — CSV 값으로")
        return {}
    out = {}
    if f is None:
        return out
    for r in f.to_dict("records"):
        pid = _pid(r.get("tm_id"), r.get("norm_key"), league)
        if pid:
            out[pid] = {"ovr": _num(r.get("_ovr")), "form": _num(r.get("_form")), "recent": _num(r.get("_recent")),
                        "goals": _num(r.get("goals")), "assists": _num(r.get("assists")),
                        "minutes": _num(r.get("minutes")), "xg": _num(r.get("xg_p90"))}
    return out


def _api():
    if "m" not in _API:
        try:
            import api.main as m  # noqa: PLC0415
            _API["m"] = m
        except Exception as e:  # noqa: BLE001
            print(f"  ! api.main 로드 실패({type(e).__name__}) — 영향력·부상 생략")
            _API["m"] = None
    return _API["m"]


def _load_influence(league: str, clubs: list[str], n2p: dict) -> dict[str, float]:
    """pid → 팀 안 영향력(0~100, NETWORK 탭 LEADERSHIP 과 같은 계산)."""
    m = _api()
    out: dict[str, float] = {}
    if m is None:
        return out
    for club in clubs:
        try:
            inf = (m.network(club, league).get("leadership") or {}).get("influence") or {}
        except Exception:  # noqa: BLE001
            continue
        for name, v in inf.items():
            pid = n2p.get(_norm(name))
            if pid:
                out[pid] = float(v)
    return out


def _load_injured(league: str, n2p: dict) -> set[str]:
    m = _api()
    if m is None:
        return set()
    try:
        t = m._injuries_table(league)
    except Exception:  # noqa: BLE001
        return set()
    names = [] if t is None else t["player"].astype(str).tolist()
    return {n2p[_norm(x)] for x in names if _norm(x) in n2p}


def _load_captains(league: str, n2p: dict) -> list[dict]:
    """wiki_squads → 주장단(1군만)."""
    try:
        df = pd.read_csv(data_path("wiki_squads", league))
    except (OSError, ValueError):
        return []
    df = df[df["role_rank"].notna()]
    if "section" in df.columns:
        df = df[df["section"].astype(str) != "loan"]
    rows = []
    for r in df.to_dict("records"):
        pid = n2p.get(_norm(r.get("player")))
        if pid:
            rows.append({"pid": pid, "club": str(r["squad"]), "rank": int(r["role_rank"]),
                         "role": str(r.get("role") or "")})
    return rows


def _load_news_pairs(n2p_by_league: dict, days: int = 60) -> tuple[list[dict], dict[str, int]]:
    """news.db 기사 선수 태그 → (같은 기사 선수 쌍 [{a,b,n,last}], pid → 기사 수). 최근 days 일(처음 수집일 기준)."""
    import news_store  # noqa: PLC0415 — main 이력 밖 data-news 보관소
    db = ROOT / "data" / "news.db"
    if not db.exists() and (db != news_store.DB or news_store.ensure() is None):   # 시험용 ROOT 면 받지 않는다
        return [], {}
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    try:
        con = sqlite3.connect(db)
        rows = con.execute(
            "SELECT ap.link, ap.player, ap.league, MAX(a.first_seen) FROM article_players ap "
            "JOIN articles a ON a.link = ap.link WHERE a.first_seen >= ? GROUP BY ap.link, ap.player, ap.league",
            (since,)).fetchall()
        con.close()
    except sqlite3.Error:
        return [], {}
    by_link: dict[str, set] = {}
    last: dict[str, str] = {}
    for link, player, league, seen in rows:
        pid = n2p_by_league.get(league, {}).get(_norm(player))
        if pid:
            by_link.setdefault(link, set()).add(pid)
            last[link] = str(seen or "")[:10]
    pair: dict = {}
    count: dict[str, int] = {}
    for link, pids in by_link.items():
        for x in pids:
            count[x] = count.get(x, 0) + 1
        for a, b in combinations(sorted(pids), 2):
            n, lt = pair.get((a, b), (0, ""))
            pair[(a, b)] = (n + 1, max(lt, last.get(link, "")))
    return [{"a": a, "b": b, "n": n, "last": lt} for (a, b), (n, lt) in pair.items()], count


def _load_callups(n2p_by_league: dict) -> list[dict]:
    path = ROOT / "data" / "intl_callups.csv"
    if not path.exists():
        return []
    rows = []
    for r in pd.read_csv(path).to_dict("records"):
        pid = n2p_by_league.get(str(r.get("our_league")), {}).get(_norm(r.get("our_player")))
        if pid:
            rows.append({"pid": pid, "nation": str(r["nation"]), "sf": _clean(r.get("squad_for")),
                         "caps": _num(r.get("caps")), "goals": _num(r.get("goals"))})
    return rows


def _rumor_base() -> tuple:
    """(canon, n2pc, tm_rows) — 클럽 표기(rumor_map.make_canon)·이름 → [(pid, 클럽)]·TM 루머 행."""
    import rumor_map as rm  # noqa: PLC0415
    club_league: dict[str, str] = {}
    player_clubs: dict[str, set[str]] = {}
    n2pc: dict[str, list[tuple[str, str]]] = {}      # 이름 → [(pid, 클럽)] — 동명이인은 연결의 '현 소속'과 같은 클럽 쪽
    for lg in LEAGUE_META:
        try:
            df = pd.read_csv(data_path("players_full", lg))
        except (OSError, ValueError):
            continue
        if "squad" not in df.columns:
            continue
        for r in df.to_dict("records"):
            club, nm = _clean(r.get("squad")), _clean(r.get("player"))
            if not club:
                continue
            club = str(club)
            club_league[club] = lg
            pid = _pid(r.get("tm_id"), r.get("norm_key"), lg)
            if not nm:
                continue
            player_clubs.setdefault(_norm(nm), set()).add(club)
            if pid:
                for k in {_norm(r.get("norm_key") or nm), _norm(nm)}:
                    if (pid, club) not in n2pc.setdefault(k, []):
                        n2pc[k].append((pid, club))
    tm_rows = []
    for lg in LEAGUE_META:
        try:
            t = pd.read_csv(data_path("transfer_rumors", lg))
        except (OSError, ValueError):
            continue
        tm_rows += [{"player": r.get("player"), "target_club": r.get("target_club"), "current_club": r.get("current_club"),
                     "probability": r.get("probability"), "date": r.get("date"), "league": lg} for r in t.to_dict("records")]
    # 클럽 표기 — 우리 선수의 TM 현 소속 표기로 학습 + 리그 안에서만 비슷한 이름(rumor_map.make_canon, API 와 같은 규칙).
    # 'RCD Espanyol Barcelona'→Barcelona·'Manchester City U18'→Manchester City 처럼 다른 클럽·2군을 묶지 않는다
    canon = rm.make_canon(club_league, player_clubs, tm_rows)
    return canon, n2pc, tm_rows


def _pid_for(k: str, frm: str, n2pc: dict, n2p_by_league: dict) -> str | None:
    """같은 이름이 여럿이면 현 소속(frm)과 같은 클럽의 선수 — 예전엔 리그 순서상 첫 번째를 골랐다."""
    cands = n2pc.get(k) or []
    return (next((p for p, c in cands if c == frm), None) or (cands[0][0] if cands else None)
            or next((m[k] for m in n2p_by_league.values() if k in m), None))


def _load_rumor_links(n2p_by_league: dict, base: tuple | None = None) -> list[dict]:
    """이적설 연결(src/rumor_map.collect — TM 루머 + 열린 시장 뉴스 루머, 매체 적중률 가중) → LINKED_TO 행.
    우리 데이터에 없는 선수(8개 리그 밖)는 'rumor:이름' 외부 노드로 — 같은 표적을 쫓는 클럽끼리 그래프로 이어지게."""
    import datetime as dt  # noqa: PLC0415

    import rumor_map as rm  # noqa: PLC0415
    canon, n2pc, tm_rows = base or _rumor_base()
    claims, scores = [], {}
    cp, rp = ROOT / "data" / "news_claims.csv", ROOT / "data" / "news_reliability.csv"
    if cp.exists():
        c = pd.read_csv(cp)
        claims = c[c["status"].astype(str) == "pending"].to_dict("records")
    if rp.exists():
        r = pd.read_csv(rp)
        scores = {str(x.name): float(x.score) for x in r[(r["kind"] == "outlet") & (~r["few"].astype(bool))].itertuples()}
    links = rm.collect(tm_rows, claims, canon, rm.outlet_factor(scores), dt.date.today())
    rows = []
    for lk in links.values():
        if lk["heat"] <= 0:
            continue
        k = _norm(lk["player"])
        pid = _pid_for(k, lk["from"], n2pc, n2p_by_league)
        rows.append({"pid": pid or f"rumor:{k}", "name": lk["player"], "to": lk["to"], "heat": lk["heat"],
                     "stage": lk["stage"], "prob": (lk["tm"] or {}).get("prob"), "news": len(lk["news"]),
                     "outlets": lk["outlets"], "last": lk["last"]})
    return rows


def claim_graph(claims: list[dict], canon, pid_of, rel: list[dict] | None = None,
                today: dt.date | None = None) -> dict[str, list[dict]]:
    """뉴스 루머 주장(news_claims.csv 행) → 그래프 행. 주장 = (선수, 행선지, 시장) 하나에 기사 여러 건.
    claims: {link, date, source, journalists('|'), stage, player, origin, dest, window, status}
    canon(클럽) → 우리 표기(없으면 None), pid_of(선수 norm, 현 소속) → 선수 id(없으면 None → 'rumor:이름').
    rel: news_reliability.csv 행(kind outlet·journalist) → 매체·기자 적중률 속성."""
    import rumor_map as rm  # noqa: PLC0415
    today = today or dt.date.today()
    cut = (today - dt.timedelta(days=CLAIM_DAYS)).isoformat()

    def club(n) -> str:
        n = str(_clean(n) or "").strip()
        return (canon(n) or n) if n else ""

    def later(a: str, b: str) -> str:
        """더 나아간 단계(부인은 다른 단계가 없을 때만)."""
        if not a or a == "denied":
            return b or a
        if not b or b == "denied":
            return a
        return a if rm.STAGE_ORDER.index(a) >= rm.STAGE_ORDER.index(b) else b

    cl: dict[str, dict] = {}
    rep: dict[tuple, dict] = {}
    wf: dict[tuple, int] = {}
    for r in claims:
        d, st = str(r.get("date") or "")[:10], str(_clean(r.get("stage")) or "")
        k, to = _norm(r.get("player")), club(r.get("dest"))
        if not d or d < cut or not k or not to or st not in rm.STAGE_ORDER:
            continue
        frm, win = club(r.get("origin")), str(_clean(r.get("window")) or "")
        cid = f"{k}|{to}|{win}"
        c = cl.setdefault(cid, {"id": cid, "player": str(r.get("player")), "key": k, "dest": to, "origin": frm,
                                "window": win, "stage": "", "first": d, "last": d, "links": set(), "status": "pending",
                                "pid": pid_of(k, frm) or f"rumor:{k}"})
        c["stage"] = later(c["stage"], st)
        c["first"], c["last"] = min(c["first"], d), max(c["last"], d)
        c["links"].add(str(r.get("link") or ""))
        if str(r.get("status")) in ("hit", "miss"):
            c["status"] = str(r.get("status"))
        src = str(_clean(r.get("source")) or "")
        js = [j.strip() for j in str(_clean(r.get("journalists")) or "").split("|") if j.strip()]
        for kind, name in [("Outlet", src)] * bool(src) + [("Journalist", j) for j in js]:
            x = rep.setdefault((kind, name, cid), {"kind": kind, "name": name, "claim": cid, "first": d, "last": d,
                                                   "n": 0, "stage": ""})
            x["first"], x["last"], x["n"] = min(x["first"], d), max(x["last"], d), x["n"] + 1
            x["stage"] = later(x["stage"], st)
        for j in js:
            if src:
                wf[(j, src)] = wf.get((j, src), 0) + 1
    rows = []
    for c in cl.values():
        c["n"] = len(c.pop("links"))
        rows.append(c)
    score = {(("Outlet" if x.get("kind") == "outlet" else "Journalist"), str(x.get("name"))): x
             for x in rel or [] if x.get("kind") in ("outlet", "journalist")}
    nodes = []
    for kind, name in sorted({(x["kind"], x["name"]) for x in rep.values()}):
        s = score.get((kind, name)) or {}
        nodes.append({"kind": kind, "name": name, "n": _num(s.get("n")), "hits": _num(s.get("hits")),
                      "rate": _num(s.get("rate")), "score": _num(s.get("score")),
                      "few": bool(s.get("few")) if s else None})
    return {"claims": rows, "reports": list(rep.values()), "writes": [{"j": j, "o": o, "n": n} for (j, o), n in wf.items()],
            "nodes": nodes}


def _load_claims(n2p_by_league: dict, base: tuple) -> dict[str, list[dict]]:
    canon, n2pc, _ = base
    cp, rp = ROOT / "data" / "news_claims.csv", ROOT / "data" / "news_reliability.csv"
    if not cp.exists():
        return {"claims": [], "reports": [], "writes": [], "nodes": []}
    rel = pd.read_csv(rp).to_dict("records") if rp.exists() else []
    return claim_graph(pd.read_csv(cp).to_dict("records"), canon,
                       lambda k, frm: _pid_for(k, frm, n2pc, n2p_by_league), rel)


def _batched(session, cypher, rows, batch=500, **params):
    for i in range(0, len(rows), batch):
        session.run(cypher, rows=rows[i:i + batch], **params)


def main() -> int:
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print(f"[kg] connected {NEO4J_URI}")

    with driver.session() as s:
        for c in CONSTRAINTS:
            s.run(c)
        for _, comp in EURO_COMPS:
            s.run("MERGE (:Competition {name:$n})", n=comp)

        tot = {"tm": 0, "rep": 0, "comp": 0, "inj": 0, "cap": 0}
        n2p_by_league: dict[str, dict] = {}
        for lg, (name, country, level) in LEAGUE_META.items():
            s.run("MERGE (l:League {key:$k}) SET l.name=$n, l.level=$lv "
                  "MERGE (co:Country {name:$c}) MERGE (l)-[:IN_COUNTRY]->(co)",
                  k=lg, n=name, c=country, lv=level)

            players, n2p = _players_and_map(lg)
            n2p_by_league[lg] = n2p
            live = _live(lg)
            clubs = sorted({x["club"] for x in players if x["club"]})
            infl = _load_influence(lg, clubs, n2p)
            hurt = _load_injured(lg, n2p)
            caps = _load_captains(lg, n2p)
            cap_rank = {c["pid"]: c["rank"] for c in caps}
            for x in players:                              # 화면과 같은 최신 값(FotMob·Understat 매일)
                lv = live.get(x["id"], {})
                for k in ("goals", "assists", "minutes"):
                    if lv.get(k) is not None:
                        x[k] = lv[k]
                x.update({"ovr": lv.get("ovr"), "form": lv.get("form"), "recent": lv.get("recent"),
                          "xg": lv.get("xg"), "inf": infl.get(x["id"]), "inj": x["id"] in hurt,
                          "cap": cap_rank.get(x["id"])})
            _batched(s,
                     "UNWIND $rows AS r MERGE (c:Club {name:r.club}) "
                     "MERGE (l:League {key:$key}) MERGE (c)-[:COMPETES_IN]->(l) "
                     "MERGE (p:Player {id:r.id}) "
                     "  SET p.name=r.name, p.pos=r.pos, p.pos_detail=r.pos_detail, p.age=r.age, p.nationality=r.nat, "
                     "      p.market_value_eur=r.mv, p.ss_rating=r.ss, p.goals=r.goals, "
                     "      p.assists=r.assists, p.minutes=r.minutes, p.contract_until=r.contract_until, "
                     "      p.league=$key, p.ovr=r.ovr, p.form=r.form, p.recent=r.recent, p.xg_p90=r.xg, "
                     "      p.influence=r.inf, p.injured_now=r.inj, p.captain_rank=r.cap, p.active=true, p.seen=$run "
                     "MERGE (p)-[pf:PLAYS_FOR]->(c) SET pf.seen=$run", players, key=lg, run=RUN)

            _batched(s, "UNWIND $rows AS r MERGE (m:Manager {name:r.name}) "
                        "SET m.nationality=r.nationality, m.formation=r.formation "
                        "MERGE (c:Club {name:r.club}) MERGE (m)-[mg:MANAGES]->(c) SET mg.seen=$run",
                     _load_managers(lg), run=RUN)

            _batched(s, "UNWIND $rows AS r MATCH (p:Player {id:r.pid}) MATCH (c:Club {name:r.club}) "
                        "MERGE (p)-[k:CAPTAIN_OF]->(c) SET k.rank=r.rank, k.role=r.role, k.seen=$run", caps, run=RUN)
            tot["cap"] += len(caps)

            _batched(s, "UNWIND $rows AS r MERGE (t:TransferEvent {id:r.id}) "
                        "  SET t.player=r.player, t.fee_eur=r.fee_eur, t.fee_text=r.fee_text, "
                        "      t.window=r.window, t.season=r.season "
                        "MERGE (to:Club {name:r.to}) MERGE (t)-[:TO]->(to) "
                        "FOREACH (_ IN CASE WHEN r.from<>'' THEN [1] ELSE [] END | "
                        "  MERGE (fr:Club {name:r.from}) MERGE (t)-[:FROM]->(fr)) "
                        "WITH t,r MATCH (p:Player {name:r.player})-[:PLAYS_FOR]->(:Club {name:r.to}) "
                        "MERGE (t)-[:OF]->(p)", _load_transfers(lg))

            reps = _load_reps(players)
            _batched(s, "UNWIND $rows AS r MATCH (p:Player {id:r.pid}) "
                        "MERGE (co:Country {name:r.country}) MERGE (p)-[:REPRESENTS]->(co)", reps)

            comp = _load_comp_played(lg, n2p)
            _batched(s, "UNWIND $rows AS r MATCH (p:Player {id:r.pid}) "
                        "MATCH (x:Competition {name:r.comp}) "
                        "MERGE (p)-[pl:PLAYED_IN]->(x) SET pl.starts=r.starts, pl.apps=r.apps", comp)

            inj = _load_injuries(lg)
            _batched(s, "UNWIND $rows AS r MATCH (p:Player {id:r.pid}) "
                        "SET p.career_games_missed=r.gm, p.career_spells=r.sp", inj)

            mates = _load_teammates(lg, n2p)
            _batched(s, "UNWIND $rows AS r MATCH (a:Player {id:r.a}), (b:Player {id:r.b}) "
                        "MERGE (a)-[t:TEAMMATE_OF]-(b) SET t.matches=r.m", mates)

            tot["tm"] += len(mates); tot["rep"] += len(reps)
            tot["comp"] += len(comp); tot["inj"] += len(inj)
            print(f"  {lg:14} players={len(players):4} teammates={len(mates):5} "
                  f"reps={len(reps):4} euro={len(comp):4} inj={len(inj):4}")

        # 리그 걸친 관계: 기사 동시 언급(최근 60일), 대표팀 소집
        pairs, ncount = _load_news_pairs(n2p_by_league)
        _batched(s, "UNWIND $rows AS r MATCH (a:Player {id:r.a}), (b:Player {id:r.b}) "
                    "MERGE (a)-[m:MENTIONED_WITH]-(b) SET m.articles=r.n, m.last=r.last, m.seen=$run", pairs, run=RUN)
        _batched(s, "UNWIND $rows AS r MATCH (p:Player {id:r.pid}) SET p.news_60d=r.n",
                 [{"pid": k, "n": v} for k, v in ncount.items()])
        calls = _load_callups(n2p_by_league)
        _batched(s, "UNWIND $rows AS r MATCH (p:Player {id:r.pid}) MERGE (co:Country {name:r.nation}) "
                    "MERGE (p)-[c:CALLED_UP]->(co) SET c.squad_for=r.sf, c.caps=r.caps, c.goals=r.goals, c.seen=$run",
                 calls, run=RUN)
        base = _rumor_base()
        rumors = _load_rumor_links(n2p_by_league, base)
        _batched(s, "UNWIND $rows AS r MERGE (p:Player {id:r.pid}) "
                    "  ON CREATE SET p.name=r.name, p.external=true, p.active=false "
                    "MERGE (c:Club {name:r.to}) MERGE (p)-[l:LINKED_TO]->(c) "
                    "SET l.heat=r.heat, l.stage=r.stage, l.tm_prob=r.prob, l.news=r.news, l.outlets=r.outlets, "
                    "    l.last=r.last, l.seen=$run", rumors, run=RUN)
        print(f"  기사 동시 언급 {len(pairs)}쌍 · 대표팀 소집 {len(calls)}명 · 주장단 {tot['cap']}명 · 이적설 {len(rumors)}건")
        # 루머 주장 그래프 — 누가(매체·기자) 무엇을(선수→행선지, 시장) 언제 보도했고 맞았는지
        g = _load_claims(n2p_by_league, base)
        _batched(s, "UNWIND $rows AS r MERGE (k:Claim {id:r.id}) "
                    "SET k.player=r.player, k.dest=r.dest, k.origin=r.origin, k.window=r.window, k.stage=r.stage, "
                    "    k.first=r.first, k.last=r.last, k.n=r.n, k.status=r.status, k.seen=$run "
                    "MERGE (p:Player {id:r.pid}) ON CREATE SET p.name=r.player, p.external=true, p.active=false "
                    "MERGE (k)-[:ABOUT]->(p) "
                    "MERGE (to:Club {name:r.dest}) MERGE (k)-[:TO_CLUB]->(to) "
                    "FOREACH (_ IN CASE WHEN r.origin<>'' THEN [1] ELSE [] END | "
                    "  MERGE (fr:Club {name:r.origin}) MERGE (k)-[:FROM_CLUB]->(fr))", g["claims"], run=RUN)
        for kind in ("Outlet", "Journalist"):
            _batched(s, f"UNWIND $rows AS r MERGE (x:{kind} {{name:r.name}}) "
                        "SET x.n=r.n, x.hits=r.hits, x.rate=r.rate, x.score=r.score, x.few=r.few, x.seen=$run",
                     [x for x in g["nodes"] if x["kind"] == kind], run=RUN)
            _batched(s, f"UNWIND $rows AS r MATCH (x:{kind} {{name:r.name}}) MATCH (k:Claim {{id:r.claim}}) "
                        "MERGE (x)-[e:REPORTED]->(k) SET e.first=r.first, e.last=r.last, e.n=r.n, e.stage=r.stage, e.seen=$run",
                     [x for x in g["reports"] if x["kind"] == kind], run=RUN)
        _batched(s, "UNWIND $rows AS r MATCH (j:Journalist {name:r.j}) MATCH (o:Outlet {name:r.o}) "
                    "MERGE (j)-[w:WRITES_FOR]->(o) SET w.n=r.n, w.seen=$run", g["writes"], run=RUN)
        print(f"  루머 주장 {len(g['claims'])}건 · 보도 {len(g['reports'])}건 · 매체·기자 {len(g['nodes'])}곳")

        # 이번 실행에서 다시 확인 안 된 관계 정리 — 떠난 선수의 소속·바뀐 감독·지난 주장·옛 소집·오래된 동시 언급
        for rel in ("PLAYS_FOR", "MANAGES", "CAPTAIN_OF", "MENTIONED_WITH", "CALLED_UP", "LINKED_TO", "REPORTED", "WRITES_FOR"):
            n = s.run(f"MATCH ()-[r:{rel}]-() WHERE coalesce(r.seen, '') <> $run "
                      "WITH DISTINCT r DELETE r RETURN count(r) AS n", run=RUN).single()["n"]
            print(f"  정리 {rel}: {n}")
        s.run("MATCH (k:Claim) WHERE coalesce(k.seen, '') <> $run DETACH DELETE k", run=RUN)   # 보관 기간 지난 주장
        s.run("MATCH (x) WHERE (x:Outlet OR x:Journalist) AND NOT (x)--() DETACH DELETE x")
        s.run("MATCH (p:Player {external:true}) WHERE NOT (p)--() DETACH DELETE p")   # 이적설이 식은 외부 선수
        gone = s.run("MATCH (p:Player) WHERE coalesce(p.seen, '') <> $run SET p.active=false RETURN count(p) AS n",
                     run=RUN).single()["n"]
        print(f"  이번에 안 보인 선수 active=false: {gone}")

        # 글로벌 보강: 클럽 UEFA 계수, 국가 FIFA 랭킹
        _enrich_club_coef(s)
        _enrich_country_fifa(s)

        c = s.run(
            "MATCH (p:Player) WITH count(p) AS pl "
            "MATCH ()-[t:TEAMMATE_OF]-() WITH pl, count(t)/2 AS mates "
            "MATCH (:Player)-[r:REPRESENTS]->() WITH pl, mates, count(r) AS reps "
            "MATCH (:Player)-[e:PLAYED_IN]->() RETURN pl, mates, reps, count(e) AS euro").single()
        print(f"[kg] Player={c['pl']} TEAMMATE_OF={c['mates']} REPRESENTS={c['reps']} PLAYED_IN={c['euro']}")
    driver.close()
    return 0


def _enrich_club_coef(session):
    try:
        df = pd.read_csv(ROOT / "data" / "uefa_club_coefficients.csv")
    except (OSError, ValueError):
        return
    clubs = [c["name"] for c in session.run("MATCH (c:Club) RETURN c.name AS name")]
    cn = {_norm(c): c for c in clubs}
    rows = []
    for _, r in df.iterrows():
        raw = _norm(r.get("club"))
        match = cn.get(raw)
        if not match:  # 부분일치(예: 'FC Porto'~'Porto')
            match = next((orig for n, orig in cn.items() if n and (n in raw or raw in n) and len(n) > 3), None)
        if match:
            rows.append({"club": match, "coef": _num(r.get("coefficient"))})
    _batched(session, "UNWIND $rows AS r MATCH (c:Club {name:r.club}) SET c.europe_coefficient=r.coef", rows)
    print(f"  [enrich] Club europe_coefficient: {len(rows)}개 매칭")


def _enrich_country_fifa(session):
    try:
        df = pd.read_csv(ROOT / "data" / "fifa_ranking.csv")
    except (OSError, ValueError):
        return
    countries = [c["name"] for c in session.run("MATCH (n:Country) RETURN n.name AS name")]
    cn = {_norm(c): c for c in countries}
    rows = []
    for _, r in df.iterrows():
        match = cn.get(_norm(r.get("team")))
        if match:
            rows.append({"country": match, "rank": int(_num(r.get("rank")) or 0),
                         "pts": _num(r.get("points"))})
    _batched(session, "UNWIND $rows AS r MATCH (n:Country {name:r.country}) "
                      "SET n.fifa_rank=r.rank, n.fifa_points=r.pts", rows)
    print(f"  [enrich] Country fifa_rank: {len(rows)}개 매칭")


if __name__ == "__main__":
    raise SystemExit(main())
