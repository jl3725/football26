"""
data/ 의 시즌 CSV 들을 단일 SQLite(`data/football.db`)로 통합한다.

목적
----
* 31개 CSV 난립 → 하나의 DB. 리그/시즌 컬럼을 부여해 다중 리그 확장의 토대.
* agent 들이 CSV 를 덮어쓰며 생기는 경합(같은 경로 last-run-wins)을 향후 DB
  upsert 로 대체하기 위한 1단계.

동작
----
* `data/*.csv` 를 훑어 파일명을 (stem, league, season) 으로 파싱
  (src.leagues.parse_data_filename).
* 같은 stem 은 하나의 테이블로 concat, `league`/`season` 컬럼을 추가.
* 기존 `news.db` 의 articles 테이블도 그대로 옮겨온다.
* 원본 CSV 는 **건드리지 않는다**(source of truth 유지, DB 는 파생).

이 스크립트는 멱등(idempotent) — 매번 테이블을 새로 만든다. 언제든 재실행 가능.

    python scripts/build_db.py
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

# Windows 콘솔(cp949)에서도 한글/기호 출력이 깨지지 않도록 UTF-8 고정
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from leagues import DATA_DIR, parse_data_filename  # noqa: E402

DB_PATH = DATA_DIR / "football.db"
NEWS_DB = DATA_DIR / "news.db"

# 통합에서 제외할 파일 stem(별도 처리하거나 파생이 아닌 것)
SKIP_STEMS: set[str] = set()


def _safe_read_csv(path: Path) -> pd.DataFrame | None:
    try:
        return pd.read_csv(path)
    except Exception as e:  # noqa: BLE001
        print(f"  ! 읽기 실패 {path.name}: {e}")
        return None


def build() -> None:
    # 1) CSV 를 stem 별로 그룹화
    groups: dict[str, list[tuple[str, str, Path]]] = defaultdict(list)
    for path in sorted(DATA_DIR.glob("*.csv")):
        parsed = parse_data_filename(path.name)
        if parsed is None:
            # 시즌 토큰 없는 파일(players_sample.csv, calendar_events.csv 등)
            stem = path.stem
            groups[stem].append(("_", "_", path))
            continue
        stem, league, season = parsed
        if stem in SKIP_STEMS:
            continue
        groups[stem].append((league, season, path))

    if DB_PATH.exists():
        DB_PATH.unlink()  # 멱등 재빌드
    conn = sqlite3.connect(DB_PATH)

    total_rows = 0
    print(f"→ {DB_PATH.relative_to(ROOT)} 생성")
    for stem, items in sorted(groups.items()):
        frames: list[pd.DataFrame] = []
        for league, season, path in items:
            df = _safe_read_csv(path)
            if df is None or df.empty:
                continue
            if league != "_":
                # 소스에 동명 컬럼이 있으면 보존을 위해 이름을 바꾼 뒤 파일 레벨 태그를 추가
                for col in ("league", "season"):
                    if col in df.columns:
                        df = df.rename(columns={col: f"{col}_src"})
                df.insert(0, "league", league)
                df.insert(1, "season", season)
            frames.append(df)
        if not frames:
            continue
        combined = pd.concat(frames, ignore_index=True)
        combined.to_sql(stem, conn, if_exists="replace", index=False)
        total_rows += len(combined)
        print(f"  · {stem:38s} {len(combined):6d} rows  ({len(items)} file)")

    # 2) news.db articles 병합
    if NEWS_DB.exists():
        try:
            ndf = pd.read_sql("SELECT * FROM articles", sqlite3.connect(NEWS_DB))
            ndf.to_sql("news_articles", conn, if_exists="replace", index=False)
            total_rows += len(ndf)
            print(f"  · {'news_articles':38s} {len(ndf):6d} rows  (news.db)")
        except Exception as e:  # noqa: BLE001
            print(f"  ! news.db 병합 실패: {e}")

    conn.commit()
    conn.close()
    print(f"✓ 완료 — 테이블 {len(groups)}개 내외, 총 {total_rows} rows")


if __name__ == "__main__":
    build()
