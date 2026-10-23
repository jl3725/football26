"""라이트 리그(2026-10-22 1단계 확장) — FotMob 리그 표·ESPN 팀 대조·라인업 토큰·2부 리그 수준·파일명 규칙."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import fotmob_lineups as fl  # noqa: E402
import league_level as ll  # noqa: E402
import lite_league as lite  # noqa: E402
import team_analysis as ta  # noqa: E402
from leagues import LEAGUES, LITE_LEAGUES, parse_data_filename  # noqa: E402


def test_lite_leagues_configured() -> None:
    assert {"Championship", "SuperLig", "AustrianBundesliga", "DanishSuperliga", "SwissSuperLeague"} <= set(LITE_LEAGUES)
    assert all(LEAGUES[k].fotmob_id and LEAGUES[k].espn for k in LITE_LEAGUES)
    assert LEAGUES["Championship"].division == 2
    # 겹치는 접미사(AustrianBundesliga ↔ Bundesliga)도 제 리그로
    assert parse_data_filename("standings_AustrianBundesliga_2026_2027.csv") == ("standings", "AustrianBundesliga", "2026_2027")
    assert parse_data_filename("standings_Bundesliga_2026_2027.csv") == ("standings", "Bundesliga", "2026_2027")


def test_standings_rows_split_tables() -> None:
    row = lambda n, i, pts: {"name": n, "id": i, "idx": i, "played": 22, "wins": 1, "draws": 1, "losses": 1,   # noqa: E731
                             "scoresStr": "30-20", "goalConDiff": 10, "pts": pts}
    # 스플릿 뒤 응답엔 그룹 표 둘 + 정규 라운드 전체 표가 같이 온다(오스트리아 25/26) — 전체 표는 빼야 한다
    d = {"table": [{"data": {"tables": [{"table": {"all": [row("A", 1, 30), row("B", 2, 28)]}},
                                         {"table": {"all": [row("C", 1, 20), row("D", 2, 18)]}},
                                         {"table": {"all": [row("B", 1, 40), row("A", 2, 39), row("D", 3, 30), row("C", 4, 20)]}}]}}]}
    rows = lite.standings_rows(d)
    assert [(r["rank"], r["squad"]) for r in rows] == [(1, "A"), (2, "B"), (3, "C"), (4, "D")]   # 하위 그룹은 이어서
    assert rows[0]["gf"] == 30 and rows[0]["ga"] == 20


def test_align_espn_by_fixtures() -> None:
    """이름으로 못 맞추는 팀(Rapid Vienna ↔ Rapid Wien)도 같은 날 같은 상대 경기로 맞춘다."""
    ev = lambda day, h, a: {"date": f"{day}T18:00Z", "competitions": [{"competitors": [   # noqa: E731
        {"homeAway": "home", "team": {"id": h[0], "displayName": h[1]}},
        {"homeAway": "away", "team": {"id": a[0], "displayName": a[1]}}]}]}
    rapid, lask, sturm = ("1", "Rapid Vienna"), ("2", "LASK Linz"), ("3", "SK Sturm Graz")
    events = [ev("2026-08-01", rapid, lask), ev("2026-08-08", sturm, rapid), ev("2026-08-15", lask, sturm)]
    fixtures = [("2026-08-01", "Rapid Wien", "LASK"), ("2026-08-08", "Sturm Graz", "Rapid Wien"),
                ("2026-08-15", "LASK", "Sturm Graz")]
    m = lite.align_espn(events, fixtures, ["Rapid Wien", "LASK", "Sturm Graz"], "AustrianBundesliga")
    assert {k: v["squad"] for k, v in m.items()} == {"1": "Rapid Wien", "2": "LASK", "3": "Sturm Graz"}


def _p(pid: int, y: float, x: float) -> dict:
    return {"positionId": pid, "verticalLayout": {"x": x, "y": y}, "name": f"p{pid}"}


def test_lineup_tokens_433_and_4231() -> None:
    # 4-3-3: x 작을수록 오른쪽
    xi = [_p(11, .1, .5), _p(32, .36, .125), _p(34, .36, .375), _p(36, .36, .625), _p(38, .36, .875),
          _p(73, .61, .21), _p(75, .61, .5), _p(77, .61, .79), _p(103, .87, .21), _p(105, .87, .5), _p(107, .87, .79)]
    toks = fl.tokens(xi, "4-3-3")
    assert toks == ["G", "RB", "CD-R", "CD-L", "LB", "CM-R", "CM", "CM-L", "RF", "F", "LF"]
    assert ta.espn_assign_slots(toks, "4-3-3")[1] == "RB" and ta.espn_assign_slots(toks, "4-3-3")[8] == "RW"
    xi2 = [_p(11, .1, .5), _p(32, .36, .125), _p(34, .36, .375), _p(36, .36, .625), _p(38, .36, .875),
           _p(64, .55, .3), _p(66, .55, .7), _p(83, .72, .2), _p(85, .72, .5), _p(87, .72, .8), _p(115, .9, .5)]
    assert fl.tokens(xi2, "4-2-3-1")[5:] == ["DM-R", "DM-L", "AM-R", "AM", "AM-L", "F"]


def test_second_tier_level_from_market_value() -> None:
    """1부 리그 (log 클럽 평균 시장가치, 레벨) 직선 → 2부 리그. 시장가치가 1부 중간이면 레벨도 중간."""
    known = {"EPL": 100.0, "LaLiga": 95.5, "Ligue1": 92.8, "Eredivisie": 89.7, "BelgianProLeague": 88.5}
    mv = {"EPL": 640e6, "LaLiga": 287e6, "Ligue1": 217e6, "Eredivisie": 73e6, "BelgianProLeague": 57e6, "Championship": 98e6}
    out, fit = ll.fit_second_tier(mv, known)
    assert fit["n"] == 5 and 89.0 <= out["Championship"] <= 92.0
    assert ll.levels()["Championship"] < 100.0          # 협회 계수(잉글랜드 = EPL)를 그대로 쓰지 않는다


def test_same_match_two_id_systems_is_one_match() -> None:
    """라이트 리그 일정(FotMob id)과 풀 리그 일정(ESPN id)에 같은 유럽 경기가 있으면 한 경기 — ESPN id 를 남긴다(라이브 스코어)."""
    import datetime as dt

    import pandas as pd

    import match_center as mc
    row = lambda sq, ha, opp, eid, gf, ga: {"squad": sq, "comp": "챔피언스리그", "comp_code": "uefa.champions",   # noqa: E731
                                           "date": "2026-10-21", "kickoff": "2026-10-21T16:45Z", "home_away": ha,
                                           "opponent": opp, "gf": gf, "ga": ga, "status": "completed", "event_id": eid,
                                           "opponent_logo": ""}
    rows = {"SuperLig": pd.DataFrame([row("Galatasaray", "A", "Lille", "6106312", 4, 2)]),
            "Ligue1": pd.DataFrame([row("Lille", "H", "Galatasaray", "401915396", 2, 4)])}
    out = mc.results_from(rows, dt.date(2026, 10, 22), 3)
    assert len(out) == 1 and out[0]["event_id"] == "401915396"
    assert {out[0]["home"]["team"], out[0]["away"]["team"]} == {"Lille", "Galatasaray"}


def test_league_tiers_and_parent() -> None:
    """홈 리그 지도 티어 — 리그 수준 92·86 에서 자르고, 2부 리그는 같은 나라 1부 아래."""
    assert ll.parent_league("Championship") == "EPL" and ll.tier("Championship") is None
    assert ll.parent_league("EPL") is None and ll.tier("EPL") == 1
    for lg in LEAGUES:
        t = ll.tier(lg)
        if t:
            lv = ll.level(lg)
            assert t == (1 if lv >= ll.TIER_CUTS[0] else 2 if lv >= ll.TIER_CUTS[1] else 3), lg


def test_parse_exports_counts_big5_permanent_only() -> None:
    import fetch_league_exports as fx
    html = """<div class="box"><h2>FC Basel 1893</h2><table><thead><tr><th>Out</th><th>Age</th></tr></thead><tbody>
      <tr><td class="hauptlink"><a href="/x/profil/spieler/1">A Player</a></td><td>20</td><td></td><td></td><td></td><td></td><td></td>
          <td><a href="/fc-arsenal/startseite/verein/11">Arsenal FC</a></td><td>€12.00m</td></tr>
      <tr><td class="hauptlink"><a href="/x/profil/spieler/2">B Player</a></td><td>22</td><td></td><td></td><td></td><td></td><td></td>
          <td><a href="/fc-arsenal/startseite/verein/11">Arsenal FC</a></td><td>loan transfer</td></tr>
      <tr><td class="hauptlink"><a href="/x/profil/spieler/3">C Player</a></td><td>24</td><td></td><td></td><td></td><td></td><td></td>
          <td><a href="/fc-sion/startseite/verein/321">FC Sion</a></td><td>€1.00m</td></tr>
    </tbody></table></div>"""
    tables, rows = fx.parse_outs(html, {11})
    assert tables == 1 and len(rows) == 1
    assert rows[0]["player"] == "A Player" and rows[0]["fee_eur"] == 12_000_000 and rows[0]["age"] == 20


def test_manager_bio_filter() -> None:
    """감독 소개 — 동음이의 문서·축구 밖 문서는 버린다(버밍엄 크리스 데이비스 → 영국 정치인 목록이 붙었던 것)."""
    assert not lite._football_bio("크리스토퍼 또는 크리스 데이비스는 다음을 지칭할 수 있다: 크리스 데이비스(영국 정치인)")
    assert not lite._football_bio("Chris Davies may refer to: Chris Davies (politician)")
    assert lite._football_bio("크리스토퍼 폴 데이비스는 현재 EFL 챔피언십 버밍엄 시티의 감독을 맡고 있는 프로 축구 지도자이다.")
