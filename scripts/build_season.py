"""
시즌 데이터 일괄 빌드 — 새 시즌 전환·시즌 중 재빌드용 (로컬 전용: FBref·Sofascore 는 브라우저 필요).

리그별로 아래 체인을 순서대로 실행한다(앞 단계 산출물을 뒤 단계가 읽음). 한 단계가 실패해도
다음 리그로 넘어가며, 끝에 리그×단계 결과표를 출력한다. 로그: logs/season-<시즌>-YYYYMMDD.log

   0 schedule         ESPN 전 대회 일정·결과                    (ESPN)
   1 standings        일정의 리그 결과 → 순위표·팀별 전적        (파생 — GH daily_data 도 매일 실행)
   2 team_defense     순위표 → 팀 공수 지표                      (파생)
   3 fbref            FBref 선수 기본 스탯 → players            (soccerdata)
   4 sofascore        Sofascore 고급 스탯                        (브라우저)
   5 understat        Understat xG + FBref 키퍼 → players_full  (soccerdata)
   6 merge_sofascore  Sofascore 컬럼 재병합
   7 transfermarkt    시장가치·국적·TM 포지션·사진               (Transfermarkt)
   8 contracts        계약 만료일 → players / players_full     (Transfermarkt)
   9 prev_season      직전 시즌 출전·평점(prev_*) — 시즌 초 OVR 안정화
  10 statbunker       팀 세부 스탯(EPL·LaLiga·SerieA, 선택)
  11 unit_metrics     팀 유닛 지표                              (파생)
  12 espn_lineups     리그 경기 라인업(증분)                    (ESPN)
  13 espn_subs        교체 기록(증분)                           (ESPN)
  14 cup_lineups      컵·유럽대회 라인업                         (ESPN)
  15 comp_usage       대회별 출전 사용량                         (ESPN)
  16 heatmaps         선수 시즌 히트맵                          (Sofascore, 브라우저)

사용:
    FB_SEASON_START=2026 python scripts/build_season.py                     # 8개 리그 전체
    FB_SEASON_START=2026 python scripts/build_season.py EPL LaLiga          # 일부 리그
    FB_SEASON_START=2026 python scripts/build_season.py --from understat EPL  # 특정 단계부터
    FB_SEASON_START=2026 python scripts/build_season.py --only espn_lineups,espn_subs
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from leagues import LEAGUES, SEASON_START  # noqa: E402

STATBUNKER_LEAGUES = {"EPL", "LaLiga", "SerieA"}

STEPS: list[tuple[str, list[str]]] = [
    ("schedule", ["src/fetch_schedule.py", "--league", "{league}", "{season}"]),
    ("standings", ["src/standings_from_schedule.py"]),
    ("team_defense", ["src/fetch_team_defense.py"]),
    ("fbref", ["src/fetch_fbref.py"]),
    ("sofascore", ["src/fetch_sofascore_stats.py"]),
    ("understat", ["src/fetch_understat.py"]),
    ("merge_sofascore", ["src/merge_sofascore.py"]),
    ("transfermarkt", ["src/fetch_transfermarkt.py"]),
    ("contracts", ["src/sync_transfermarkt_contracts.py", "--write"]),
    ("prev_season", ["src/attach_prev_season.py"]),
    ("statbunker", ["src/fetch_statbunker_team_stats.py"]),
    ("unit_metrics", ["src/build_team_unit_metrics.py"]),
    ("espn_lineups", ["src/fetch_espn_lineups.py"]),
    ("espn_subs", ["src/fetch_espn_subs.py"]),
    ("cup_lineups", ["src/fetch_cup_lineups.py", "--league", "{league}"]),
    ("comp_usage", ["src/fetch_comp_usage.py", "--league", "{league}"]),
    ("heatmaps", ["src/fetch_sofascore_heatmaps.py"]),
]
STEP_NAMES = [n for n, _ in STEPS]


def _parse(argv: list[str]) -> tuple[list[str], list[str]]:
    leagues, steps = [], list(STEP_NAMES)
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--from":
            steps = STEP_NAMES[STEP_NAMES.index(argv[i + 1]):]
            i += 2
        elif a == "--only":
            steps = [s for s in argv[i + 1].split(",") if s]
            unknown = set(steps) - set(STEP_NAMES)
            if unknown:
                raise SystemExit(f"알 수 없는 단계: {sorted(unknown)}")
            i += 2
        elif a in LEAGUES:
            leagues.append(a)
            i += 1
        else:
            raise SystemExit(f"알 수 없는 인자: {a}")
    return leagues or list(LEAGUES), steps


STEP_TIMEOUT = 45 * 60   # 한 단계 상한(초) — Sofascore 선수별 수집이 가장 김(리그당 ~5분)


def _kill_stray_drivers() -> None:
    """soccerdata·seleniumbase 가 남긴 uc_driver(+크롬) 트리 정리.

    부모 파이썬이 끝나도 드라이버가 살아 남아 메모리를 잡아먹고, 파이프로 출력을 받으면 상속된
    핸들 때문에 다음 단계가 영원히 기다리게 된다(2026-10 빌드에서 실제로 멈춤). 빌드는 순차 실행이라
    이 시점의 uc_driver 는 모두 직전 단계의 잔여물이다.
    """
    if os.name != "nt":
        return
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='uc_driver.exe'\" | "
          "ForEach-Object { taskkill /F /T /PID $_.ProcessId 2>$null | Out-Null }")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)


def _run_step(args: list[str], env: dict) -> tuple[int | None, str]:
    """단계 실행 → (종료코드 | 타임아웃 None, 출력). 출력은 파이프 대신 임시 파일로 받는다
    (잔여 드라이버가 파이프 핸들을 쥐어도 기다리지 않게)."""
    with tempfile.TemporaryFile(mode="w+b") as buf:
        try:
            code = subprocess.run(args, cwd=ROOT, env=env, stdout=buf, stderr=subprocess.STDOUT,
                                  timeout=STEP_TIMEOUT).returncode
        except subprocess.TimeoutExpired:
            code = None
        finally:
            _kill_stray_drivers()
        buf.seek(0)
        return code, buf.read().decode("utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    leagues, steps = _parse(list(argv if argv is not None else sys.argv[1:]))
    season = f"{SEASON_START}_{SEASON_START + 1}"
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"season-{season}-{datetime.now():%Y%m%d}.log"
    python = sys.executable

    results: dict[tuple[str, str], str] = {}
    with log_path.open("a", encoding="utf-8") as log:
        def emit(msg: str) -> None:
            line = f"[{datetime.now():%H:%M:%S}] {msg}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

        emit(f"=== 시즌 {season} 빌드 · 리그 {leagues} · 단계 {steps}")
        for lg in leagues:
            env = {**os.environ, "FB_LEAGUE": lg, "FB_SEASON_START": str(SEASON_START),
                   "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
            for name, cmd in STEPS:
                if name not in steps:
                    continue
                if name == "statbunker" and lg not in STATBUNKER_LEAGUES:
                    results[(lg, name)] = "-"
                    continue
                args = [python] + [c.replace("{league}", lg).replace("{season}", season) for c in cmd]
                emit(f"── {lg} · {name}")
                t0 = time.time()
                code, out = _run_step(args, env)
                log.write(out[-8000:] + "\n")
                status = "ok" if code == 0 else ("TIMEOUT" if code is None else f"FAIL({code})")
                results[(lg, name)] = status
                tail = (out.strip().splitlines() or [""])[-1][:110]
                emit(f"   {status} {time.time() - t0:5.0f}s  {tail}")

        emit("=== 결과")
        emit("league".ljust(18) + " ".join(s[:8].ljust(8) for s in steps))
        for lg in leagues:
            emit(lg.ljust(18) + " ".join(results.get((lg, s), "").ljust(8)[:8] for s in steps))
    failed = [k for k, v in results.items() if v.startswith(("FAIL", "TIMEOUT"))]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
