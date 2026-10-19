from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_season_literals import _season_like, _strip_ts_comments  # noqa: E402


@pytest.mark.parametrize("text", ["25/26", "시즌 2025-26", "2025/26 SEASON", "2025–26", "data_2025_2026.csv", "99/00"])
def test_season_like_catches_season_labels(text: str) -> None:
    assert _season_like(text)


@pytest.mark.parametrize("text", ["10/13", "1/2", "2026-10-13", "3/5 경기", "https://x.com/2025/12/a", "24/7"])
def test_season_like_ignores_dates_and_ratios(text: str) -> None:
    assert not _season_like(text)


def test_ts_comments_stripped_but_strings_kept() -> None:
    src = 'const a = "25/26"; // 26/27\n/* 27/28 */ const u = "https://a.b";'
    lines = _strip_ts_comments(src)
    assert "25/26" in lines[0] and "26/27" not in lines[0]
    assert "27/28" not in lines[1] and "https://a.b" in lines[1]


def test_watchdog_issue_lifecycle(monkeypatch) -> None:
    import watchdog

    calls: list[tuple[str, str, dict | None]] = []
    state = {"open": []}

    def fake_gh(path, method="GET", **kw):
        calls.append((method, path, kw.get("json")))
        if path == "issues" and method == "GET":
            return state["open"]
        if path == "issues" and method == "POST":
            state["open"] = [{"number": 7, "body": kw["json"]["body"]}]
            return {"number": 7}
        return {}

    monkeypatch.setattr(watchdog, "gh", fake_gh)
    fail = {"season": [], "news": ["번역률 0%"]}
    watchdog.file_issue(fail)                       # 실패 → 이슈 생성
    assert any(m == "POST" and p == "issues" for m, p, _ in calls)
    calls.clear()
    watchdog.file_issue(fail)                       # 같은 실패 → 본문만 갱신, 댓글 없음
    assert [p for m, p, _ in calls if m == "POST"] == []
    calls.clear()
    watchdog.file_issue({"season": [], "news": []})  # 전부 정상 → 댓글 후 닫기
    assert ("PATCH", "issues/7", {"state": "closed"}) in calls


def test_build_season_retries_failed_step_and_followers(monkeypatch, tmp_path) -> None:
    """실패한 리그×단계는 한 번 더 — 그 산출물을 읽는 뒤 단계(merge)도 함께, 성공은 ok* 로 남긴다."""
    import build_season as bs

    tries: dict[tuple[str, str], int] = {}

    def fake_run(args, env):
        key = (env["FB_LEAGUE"], args[1])
        tries[key] = tries.get(key, 0) + 1
        # Sofascore 는 첫 시도만 연결 끊김, 히트맵은 두 번 다 실패
        if args[1] == "sofascore" and tries[key] == 1:
            return 1, "connection reset"
        if args[1] == "heatmaps":
            return 1, "season id"
        return 0, "ok"

    monkeypatch.setattr(bs, "STEPS", [("sofascore", ["sofascore"]), ("merge_sofascore", ["merge_sofascore"]),
                                      ("heatmaps", ["heatmaps"]), ("comp_usage", ["comp_usage"])])
    monkeypatch.setattr(bs, "STEP_NAMES", ["sofascore", "merge_sofascore", "heatmaps", "comp_usage"])
    monkeypatch.setattr(bs, "RETRY_WAIT", 0)
    monkeypatch.setattr(bs, "ROOT", tmp_path)
    monkeypatch.setattr(bs, "_run_step", fake_run)
    monkeypatch.setattr(bs.run_ledger, "LEDGER_DIR", tmp_path / "runs")
    monkeypatch.setenv("LEDGER_RUNNER", "local-test")
    assert bs.main(["EPL"]) == 1                                  # 히트맵은 재시도에도 실패 → 종료코드 1
    assert tries[("EPL", "sofascore")] == 2 and tries[("EPL", "merge_sofascore")] == 2
    assert tries[("EPL", "heatmaps")] == 2 and tries[("EPL", "comp_usage")] == 1
    log = next((tmp_path / "logs").glob("season-*.log")).read_text(encoding="utf-8")
    assert "재시도로 성공" in log
    tries.clear()
    assert bs.main(["EPL", "--only", "sofascore,merge_sofascore", "--no-retry"]) == 1
    assert tries[("EPL", "sofascore")] == 1                       # --no-retry 면 다시 돌지 않는다


def test_xg_zero_team_warns_then_blocks(monkeypatch) -> None:
    """출전은 있는데 xG 합이 0 인 팀 — 한두 팀은 경고(watchdog 이 이름을 알림), 리그 30% 이상이면 저장 차단."""
    import pandas as pd
    import validate_data as vd

    def frame(zero_teams: int) -> pd.DataFrame:
        rows = []
        for t in range(10):
            for p in range(11):
                rows.append({"squad": f"T{t}", "player": f"P{t}-{p}", "minutes": 90,
                             "xg_p90": 0.0 if t < zero_teams else 0.2})
        rows.append({"squad": "Bench FC", "player": "x", "minutes": 30, "xg_p90": 0.0})  # 출전 분이 적은 팀은 판단 안 함
        return pd.DataFrame(rows)

    monkeypatch.setattr(vd.ds, "read_table", lambda table, league=None: frame(1))
    assert vd.xg_zero_teams("EPL") == (["T0"], 10)
    errors, warnings = vd.validate_xg("EPL")
    assert not errors and "T0" in warnings[0]
    monkeypatch.setattr(vd.ds, "read_table", lambda table, league=None: frame(3))
    errors, _ = vd.validate_xg("EPL")
    assert errors and "3/10" in errors[0]
    assert vd.validate_xg("LigaPortugal") == ([], [])             # Understat 없는 리그는 보지 않는다
