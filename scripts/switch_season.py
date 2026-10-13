"""
데이터 시즌 전환 — '현재 상태' 파일을 새 시즌 파일명으로 넘긴다.

데이터 파일은 두 종류다.
  · 시즌 기록(순위·선수 스탯·라인업·일정)  → scripts/build_season.py 가 새 시즌 파일을 만든다.
  · 현재 상태(부상·계약·루머·감독·이적 등) → 파일명엔 시즌이 붙지만 내용은 '지금' 기준이라
    전환 직후에도 화면이 비지 않도록 여기서 새 시즌 이름으로 넘긴다(이후엔 수집기가 새 이름으로 갱신).

규칙
  · 스냅샷(지금 상태)               : 그대로 복사
  · 변경 이력(감독 교체·부상/시장가치 변동): 새 시즌 시작일(7/1) 이후 행만
  · 이적(transfers)                : season_id == 새 시즌 행만 (지난 시즌 파일엔 그대로 둠)
이미 새 시즌 파일이 있으면 건너뛴다(--force 로 덮어쓰기).

사용:
    FB_SEASON_START=2026 python scripts/switch_season.py          # 미리보기
    FB_SEASON_START=2026 python scripts/switch_season.py --write
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from leagues import LEAGUES, SEASON_START, data_path  # noqa: E402

NEW = f"{SEASON_START}_{SEASON_START + 1}"
OLD = f"{SEASON_START - 1}_{SEASON_START}"
SEASON_BEGIN = f"{SEASON_START}-07-01"

SNAPSHOT_CSV = ["transfermarkt_injuries", "transfermarkt_contracts", "transfer_rumors",
                "transfer_buzz", "tm_injury_history", "team_home_kits"]
SNAPSHOT_JSON = ["manager_profiles", "season_teams"]
# 변경 이력: (stem, 날짜 컬럼)
LOGS = [("manager_changes", "detected_at"), ("transfermarkt_injury_changes", "run_date"),
        ("market_value_changes", "run_date")]


def plan() -> list[tuple[str, Path, Path, str]]:
    """(종류, 원본, 대상, 설명) 목록."""
    items = []
    for lg in LEAGUES:
        for stem in SNAPSHOT_CSV:
            items.append(("copy", data_path(stem, lg, OLD), data_path(stem, lg, NEW), stem))
        for stem in SNAPSHOT_JSON:
            items.append(("copy", data_path(stem, lg, OLD, ext="json"),
                          data_path(stem, lg, NEW, ext="json"), stem))
        for stem, col in LOGS:
            items.append((f"since:{col}", data_path(stem, lg, OLD), data_path(stem, lg, NEW), stem))
        items.append(("season_id", data_path("transfers", lg, OLD), data_path("transfers", lg, NEW),
                      "transfers"))
    return [it for it in items if it[1].exists()]


def run(write: bool, force: bool) -> int:
    done = skipped = 0
    for kind, src, dst, stem in plan():
        if dst.exists() and not force:
            print(f"  [skip] {dst.name} 이미 있음")
            skipped += 1
            continue
        if kind == "copy":
            note = "복사"
            if write:
                shutil.copyfile(src, dst)
        else:
            df = pd.read_csv(src)
            if kind == "season_id":
                keep = df[pd.to_numeric(df.get("season_id"), errors="coerce") == SEASON_START]
            else:
                col = kind.split(":", 1)[1]
                keep = df[df[col].astype(str).str[:10] >= SEASON_BEGIN] if col in df.columns else df.iloc[0:0]
            note = f"{len(keep)}/{len(df)}행"
            if write:
                keep.to_csv(dst, index=False, encoding="utf-8")
        print(f"  {'[write]' if write else '[plan] '} {src.name} → {dst.name} ({note})")
        done += 1
    print(f"\n{OLD} → {NEW}: {done}개 {'처리' if write else '예정'} · {skipped}개 건너뜀"
          + ("" if write else "  (적용: --write)"))
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    raise SystemExit(run(write="--write" in args, force="--force" in args))
