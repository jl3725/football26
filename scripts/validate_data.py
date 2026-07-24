"""리그 데이터의 최소 계약을 검증한다.

수집 워크플로와 CI가 "명령은 성공했지만 데이터는 비어 있는" 상태를 조기에
발견하도록 한다. 핵심 테이블 누락/스키마 오류는 실패, 선택 테이블 누락은
경고로 보고한다.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import datastore as ds  # noqa: E402
from leagues import LEAGUES  # noqa: E402


@dataclass(frozen=True)
class Contract:
    columns: frozenset[str]
    minimum_rows: int = 1
    unique_by: tuple[str, ...] = ()


CORE_CONTRACTS: dict[str, Contract] = {
    "players_full": Contract(
        frozenset({"player", "squad", "pos", "minutes"}), minimum_rows=100
    ),
    "standings": Contract(
        frozenset({"rank", "squad", "played", "points"}),
        minimum_rows=12,
        unique_by=("squad",),
    ),
    "schedule_full": Contract(
        frozenset({"squad", "date", "opponent", "status"}), minimum_rows=100
    ),
    "transfers": Contract(
        frozenset({"squad", "direction", "player", "club", "fee_text"}),
        minimum_rows=1,
    ),
    "team_unit_metrics": Contract(
        frozenset({"squad", "overall_index", "attack_index", "defense_index"}),
        minimum_rows=12,
        unique_by=("squad",),
    ),
    "team_defense": Contract(
        frozenset({"squad", "goals_for", "goals_against"}),
        minimum_rows=12,
        unique_by=("squad",),
    ),
    "espn_lineups": Contract(
        frozenset({"squad", "formation", "player", "event_id"}), minimum_rows=100
    ),
}

OPTIONAL_CONTRACTS: dict[str, Contract] = {
    "transfermarkt_injuries": Contract(
        frozenset({"player", "squad"}), minimum_rows=1
    ),
    "tm_injury_history": Contract(
        frozenset({"player", "squad"}), minimum_rows=1
    ),
    "player_comp_usage": Contract(
        frozenset({"player", "squad"}), minimum_rows=1
    ),
    "manager_changes": Contract(frozenset({"team"}), minimum_rows=1),
}


def validate_table(table: str, league: str, contract: Contract) -> list[str]:
    """한 테이블을 검증하고 오류 문자열 목록을 반환한다."""
    frame = ds.read_table(table, league=league)
    label = f"{league}/{table}"
    if frame is None:
        return [f"{label}: missing"]
    if len(frame) < contract.minimum_rows:
        return [f"{label}: only {len(frame)} rows (minimum {contract.minimum_rows})"]

    errors: list[str] = []
    missing_columns = sorted(contract.columns.difference(frame.columns))
    if missing_columns:
        errors.append(f"{label}: missing columns {', '.join(missing_columns)}")

    keys = list(contract.unique_by)
    if keys and all(key in frame.columns for key in keys):
        duplicate_count = int(frame.duplicated(keys, keep=False).sum())
        if duplicate_count:
            errors.append(
                f"{label}: {duplicate_count} rows have duplicate key {', '.join(keys)}"
            )
    return errors


def validate(
    tables: list[str] | None = None,
    leagues: list[str] | None = None,
    include_optional: bool = True,
) -> tuple[list[str], list[str]]:
    selected_leagues = leagues or list(LEAGUES)
    selected_tables = tables or list(CORE_CONTRACTS)
    errors: list[str] = []
    warnings: list[str] = []

    unknown = sorted(set(selected_tables).difference(CORE_CONTRACTS | OPTIONAL_CONTRACTS))
    if unknown:
        errors.append(f"unknown tables: {', '.join(unknown)}")
        return errors, warnings

    for league in selected_leagues:
        if league not in LEAGUES:
            errors.append(f"unknown league: {league}")
            continue
        for table in selected_tables:
            contract = CORE_CONTRACTS.get(table) or OPTIONAL_CONTRACTS[table]
            errors.extend(validate_table(table, league, contract))

        if include_optional and tables is None:
            for table, contract in OPTIONAL_CONTRACTS.items():
                warnings.extend(validate_table(table, league, contract))

    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tables",
        nargs="+",
        help="검증할 테이블. 생략하면 모든 핵심 테이블을 검증한다.",
    )
    parser.add_argument(
        "--leagues",
        nargs="+",
        help="검증할 리그 키. 생략하면 설정된 모든 리그를 검증한다.",
    )
    parser.add_argument(
        "--no-optional",
        action="store_true",
        help="전체 검증 시 선택 데이터 경고를 생략한다.",
    )
    args = parser.parse_args(argv)

    errors, warnings = validate(
        tables=args.tables,
        leagues=args.leagues,
        include_optional=not args.no_optional,
    )
    for warning in warnings:
        print(f"WARN  {warning}")
    for error in errors:
        print(f"ERROR {error}")

    if errors:
        print(f"FAILED: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"PASS: core data contracts satisfied ({len(warnings)} optional warning(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
