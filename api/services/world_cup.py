"""월드컵 데이터 조립 서비스.

HTTP와 분리해 정기 수집 데이터, FIFA 예상 랭킹, 클럽 차출 교차참조를
하나의 응답 모델로 조립한다.
"""
from __future__ import annotations

import math

from unidecode import unidecode

import api.bootstrap  # noqa: F401
import datastore as ds
import teammeta as tm
from api.services.player_data import number, photo_url, player_frame
from leagues import ACTIVE_LEAGUE

ROUNDS = [
    "group-stage",
    "round-of-32",
    "round-of-16",
    "quarterfinals",
    "semifinals",
    "3rd-place-match",
    "final",
]
ROUND_LABELS = {
    "group-stage": "조별리그",
    "round-of-32": "32강",
    "round-of-16": "16강",
    "quarterfinals": "8강",
    "semifinals": "4강",
    "3rd-place-match": "3·4위전",
    "final": "결승",
}
CLUB_LEAGUES = (
    "EPL",
    "LaLiga",
    "SerieA",
    "Bundesliga",
    "Ligue1",
    "LigaPortugal",
    "Eredivisie",
    "BelgianProLeague",
)


class WorldCupDataError(LookupError):
    """월드컵 원본 데이터가 없거나 요청 대상을 찾지 못한 경우."""


def _read(table: str):
    return ds.read_table(table, league=ACTIVE_LEAGUE)


def _num_or_none(value):
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _player_index():
    """월드컵 선수 정규화 이름 → 현재 클럽 선수 행과 리그."""

    def normalize(value):
        return unidecode(str(value)).lower().strip()

    candidates: dict[str, tuple] = {}
    available = set(ds.available_leagues())
    for league in CLUB_LEAGUES:
        if league not in available:
            continue
        try:
            frame = player_frame(league)
        except Exception:  # noqa: BLE001
            frame = None
        if frame is None or "player" not in frame.columns:
            continue
        if "left_for" in frame.columns:
            frame = frame[
                frame["left_for"].isna()
                | (frame["left_for"].astype(str).str.strip() == "")
            ]
        for _, row in frame.iterrows():
            key = normalize(row["player"])
            minutes = number(row.get("minutes"))
            previous = candidates.get(key)
            if previous is None or minutes > previous[2]:
                candidates[key] = (row, league, minutes)
    return {key: (value[0], value[1]) for key, value in candidates.items()}, normalize


def _live_fifa_ranking():
    """공식 FIFA 점수에 완료된 월드컵 결과를 SUM(Elo) 방식으로 반영한다."""
    ranking = _read("fifa_ranking")
    if ranking is None or "code" not in ranking.columns or ranking.empty:
        return [], ""

    points, metadata = {}, {}
    for _, row in ranking.iterrows():
        code = str(row.get("code") or "").strip()
        if not code:
            continue
        points[code] = number(row.get("points"))
        metadata[code] = {
            "team": str(row.get("team") or ""),
            "flag": str(row.get("flag") or ""),
            "confederation": str(row.get("confederation") or ""),
            "official_rank": int(number(row.get("rank"))),
        }
    base_points = dict(points)
    updated = str(ranking.iloc[0].get("updated") or "")

    matches = _read("wc_matches")
    if matches is not None and "completed" in matches.columns:
        completed = matches[
            matches["completed"].astype(str).str.lower().isin({"true", "1", "yes"})
        ].copy()
        if "date" in completed.columns:
            completed = completed.sort_values("date")
        for _, game in completed.iterrows():
            home = str(game.get("home_abbr") or "").strip()
            away = str(game.get("away_abbr") or "").strip()
            if home not in points or away not in points:
                continue
            home_score = _num_or_none(game.get("home_score"))
            away_score = _num_or_none(game.get("away_score"))
            if home_score is None or away_score is None:
                continue
            importance = 50.0 if str(game.get("round")) == "group-stage" else 60.0
            expected_home = 1.0 / (
                math.pow(10, -(points[home] - points[away]) / 600.0) + 1.0
            )
            result_home = (
                1.0
                if home_score > away_score
                else (0.0 if home_score < away_score else 0.5)
            )
            points[home] += importance * (result_home - expected_home)
            points[away] += importance * (
                (1.0 - result_home) - (1.0 - expected_home)
            )

    result = []
    for index, (code, value) in enumerate(
        sorted(points.items(), key=lambda item: -item[1]), start=1
    ):
        meta = metadata.get(code, {})
        official_rank = meta.get("official_rank", index)
        result.append(
            {
                "rank": index,
                "team": meta.get("team", code),
                "code": code,
                "points": round(value, 2),
                "official_rank": official_rank,
                "rank_change": official_rank - index,
                "points_change": round(value - base_points.get(code, value), 2),
                "confederation": meta.get("confederation", ""),
                "flag": meta.get("flag", ""),
            }
        )
    return result, updated


def world_cup_payload() -> dict:
    matches = _read("wc_matches")
    if matches is None:
        raise WorldCupDataError("WC 데이터 없음 — src/fetch_wc.py 실행 필요")
    groups_frame = _read("wc_groups")
    scorers_frame = _read("wc_scorers")
    squads_frame = _read("wc_squads")

    nation_logo = {}
    for _, row in matches.iterrows():
        pairs = (
            (str(row.get("home")), str(row.get("home_logo"))),
            (str(row.get("away")), str(row.get("away_logo"))),
        )
        for nation, logo in pairs:
            if nation and logo.startswith("http") and nation not in nation_logo:
                nation_logo[nation] = logo

    def match_row(row):
        return {
            "date": str(row.get("date") or ""),
            "group": str(row.get("group") or ""),
            "home": str(row.get("home") or ""),
            "home_abbr": str(row.get("home_abbr") or ""),
            "home_logo": str(row.get("home_logo") or ""),
            "home_score": _num_or_none(row.get("home_score")),
            "away": str(row.get("away") or ""),
            "away_abbr": str(row.get("away_abbr") or ""),
            "away_logo": str(row.get("away_logo") or ""),
            "away_score": _num_or_none(row.get("away_score")),
            "status": str(row.get("status") or ""),
            "completed": bool(row.get("completed")),
        }

    rounds = []
    for slug in ROUNDS:
        subset = (
            matches[matches["round"] == slug]
            if "round" in matches.columns
            else matches.iloc[0:0]
        )
        items = [match_row(row) for _, row in subset.iterrows()]
        if items:
            rounds.append(
                {"round": slug, "label": ROUND_LABELS.get(slug, slug), "matches": items}
            )

    grouped: dict[str, list] = {}
    if groups_frame is not None:
        for _, row in groups_frame.iterrows():
            grouped.setdefault(str(row.get("group")), []).append(
                {
                    "team": str(row.get("team") or ""),
                    "logo": str(row.get("logo") or ""),
                    "P": int(number(row.get("P"))),
                    "W": int(number(row.get("W"))),
                    "D": int(number(row.get("D"))),
                    "L": int(number(row.get("L"))),
                    "GF": int(number(row.get("GF"))),
                    "GA": int(number(row.get("GA"))),
                    "GD": int(number(row.get("GD"))),
                    "Pts": int(number(row.get("Pts"))),
                }
            )
    groups = [
        {"group": name, "table": table}
        for name, table in sorted(grouped.items())
        if name
    ]

    player_index, normalize = _player_index()
    goal_map: dict[str, int] = {}
    scorers = []
    if scorers_frame is not None:
        for _, row in scorers_frame.iterrows():
            goal_map[normalize(row.get("player"))] = int(number(row.get("goals")))
        for _, row in scorers_frame.head(20).iterrows():
            nation = str(row.get("nation") or "")
            scorers.append(
                {
                    "player": str(row.get("player") or ""),
                    "nation": nation,
                    "goals": int(number(row.get("goals"))),
                    "pens": int(number(row.get("pens"))),
                    "logo": nation_logo.get(nation, ""),
                }
            )

    assists_frame = _read("wc_assists")
    assist_map: dict[str, int] = {}
    assists = []
    if assists_frame is not None:
        for _, row in assists_frame.iterrows():
            assist_map[normalize(row.get("player"))] = int(
                number(row.get("assists"))
            )
        for _, row in assists_frame.head(20).iterrows():
            nation = str(row.get("nation") or "")
            assists.append(
                {
                    "player": str(row.get("player") or ""),
                    "nation": nation,
                    "assists": int(number(row.get("assists"))),
                    "logo": nation_logo.get(nation, ""),
                }
            )

    age_map = {}
    if squads_frame is not None:
        for _, row in squads_frame.iterrows():
            age_map[normalize(row.get("player"))] = int(number(row.get("age")))

    contributions = {}
    if scorers_frame is not None:
        for _, row in scorers_frame.iterrows():
            key = normalize(row.get("player"))
            contributions[key] = {
                "player": str(row.get("player") or ""),
                "nation": str(row.get("nation") or ""),
                "goals": int(number(row.get("goals"))),
                "assists": assist_map.get(key, 0),
                "age": age_map.get(key, 0),
            }
    if assists_frame is not None:
        for _, row in assists_frame.iterrows():
            key = normalize(row.get("player"))
            contributions.setdefault(
                key,
                {
                    "player": str(row.get("player") or ""),
                    "nation": str(row.get("nation") or ""),
                    "goals": goal_map.get(key, 0),
                    "assists": int(number(row.get("assists"))),
                    "age": age_map.get(key, 0),
                },
            )

    def impact_card(contribution):
        hit = player_index.get(normalize(contribution["player"]))
        player_row = hit[0] if hit else None
        return {
            **contribution,
            "ga": contribution["goals"] + contribution["assists"],
            "logo": nation_logo.get(contribution["nation"], ""),
            "club": str(player_row["squad"]) if player_row is not None else "",
            "photo": photo_url(player_row) if player_row is not None else "",
        }

    rising = sorted(
        [
            item
            for item in contributions.values()
            if 0 < item["age"] <= 21 and item["goals"] + item["assists"] >= 1
        ],
        key=lambda item: -(item["goals"] + item["assists"]),
    )[:6]
    veterans = sorted(
        [
            item
            for item in contributions.values()
            if item["age"] >= 33 and item["goals"] + item["assists"] >= 1
        ],
        key=lambda item: -(item["goals"] + item["assists"]),
    )[:6]

    advancing = set()
    if "round" in matches.columns:
        round_values = set(matches["round"].astype(str))
        knockout = (
            matches[matches["round"] != "group-stage"]
            if "group-stage" in round_values
            else matches[
                matches["round"].astype(str).str.contains(
                    "round|final|quarter|semi", case=False, na=False
                )
            ]
        )
        for _, row in knockout.iterrows():
            advancing.add(str(row.get("home") or ""))
            advancing.add(str(row.get("away") or ""))

    group_heroes = []
    if groups_frame is not None:
        eliminated = [
            row
            for _, row in groups_frame.iterrows()
            if str(row.get("team")) not in advancing
        ]
        eliminated.sort(
            key=lambda row: (
                -int(number(row.get("Pts"))),
                -int(number(row.get("GD"))),
                -int(number(row.get("GF"))),
            )
        )
        strong = [row for row in eliminated if int(number(row.get("Pts"))) >= 3]
        for row in (strong or eliminated[:4])[:6]:
            nation = str(row.get("team") or "")
            stars = sorted(
                [
                    item
                    for item in contributions.values()
                    if item["nation"] == nation
                    and item["goals"] + item["assists"] >= 1
                ],
                key=lambda item: -(item["goals"] + item["assists"]),
            )[:2]
            group_heroes.append(
                {
                    "team": nation,
                    "logo": str(row.get("logo") or "")
                    or nation_logo.get(nation, ""),
                    "group": str(row.get("group") or ""),
                    "P": int(number(row.get("P"))),
                    "W": int(number(row.get("W"))),
                    "D": int(number(row.get("D"))),
                    "L": int(number(row.get("L"))),
                    "GD": int(number(row.get("GD"))),
                    "Pts": int(number(row.get("Pts"))),
                    "stars": [
                        {
                            "player": star["player"],
                            "goals": star["goals"],
                            "assists": star["assists"],
                        }
                        for star in stars
                    ],
                }
            )

    by_club: dict[str, dict] = {}
    if squads_frame is not None:
        for _, row in squads_frame.iterrows():
            hit = player_index.get(normalize(row.get("player")))
            if hit is None:
                continue
            player_row, league = hit
            club = str(player_row["squad"])
            bucket = by_club.setdefault(club, {"league": league, "players": []})
            bucket["players"].append(
                {
                    "player": str(row.get("player") or ""),
                    "nation": str(row.get("nation") or ""),
                    "pos": str(row.get("pos") or ""),
                    "photo": photo_url(player_row),
                    "goals": goal_map.get(normalize(row.get("player")), 0),
                }
            )

    club_callups = []
    for club, info in by_club.items():
        players = info["players"]
        players.sort(key=lambda item: -item["goals"])
        club_callups.append(
            {
                "club": club,
                "league": info["league"],
                "logo": tm.team_logo(club),
                "count": len(players),
                "players": players,
            }
        )
    club_callups.sort(key=lambda item: (-item["count"], item["league"], item["club"]))

    nations = []
    if squads_frame is not None:
        counts: dict[str, int] = {}
        for _, row in squads_frame.iterrows():
            nation = str(row.get("nation") or "")
            if nation:
                counts[nation] = counts.get(nation, 0) + 1
        nations = [
            {"nation": nation, "logo": nation_logo.get(nation, ""), "count": count}
            for nation, count in sorted(counts.items())
        ]

    fifa_all, fifa_updated = _live_fifa_ranking()
    return {
        "matches": rounds,
        "groups": groups,
        "scorers": scorers,
        "assists": assists,
        "rising_stars": [impact_card(item) for item in rising],
        "veterans": [impact_card(item) for item in veterans],
        "group_heroes": group_heroes,
        "club_callups": club_callups,
        "nations": nations,
        "fifa_ranking": fifa_all[:30],
        "fifa_updated": fifa_updated,
        "fifa_live": any(item["points_change"] for item in fifa_all),
    }


def squad_payload(nation: str) -> dict:
    squads = _read("wc_squads")
    if squads is None or "nation" not in squads.columns:
        raise WorldCupDataError("WC 스쿼드 데이터 없음")

    index, normalize = _player_index()
    rows = squads[squads["nation"].astype(str) == nation]
    if rows.empty:
        raise WorldCupDataError(f"'{nation}' 스쿼드 없음")

    players = []
    for _, row in rows.iterrows():
        hit = index.get(normalize(row.get("player")))
        player_row = hit[0] if hit else None
        club = str(player_row["squad"]) if player_row is not None else ""
        players.append(
            {
                "player": str(row.get("player") or ""),
                "pos": str(row.get("pos") or ""),
                "jersey": str(row.get("jersey") or ""),
                "age": str(row.get("age") or ""),
                "club": club,
                "league": hit[1] if hit else "",
                "club_logo": tm.team_logo(club) if club else "",
                "photo": photo_url(player_row) if player_row is not None else "",
            }
        )
    order = {"G": 0, "D": 1, "M": 2, "F": 3}
    players.sort(key=lambda item: (order.get(item["pos"], 9), item["player"]))
    return {"nation": nation, "count": len(players), "players": players}
