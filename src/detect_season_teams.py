"""다음 시즌(예: 26/27) 프리미어리그 로스터 자동 감지.

위키 '2026-27 Premier League' 페이지(감독 동기화가 이미 긁는 그 페이지)의 팀 목록을
읽어, 지난 시즌(standings) 대비 승격(IN)/강등(OUT)을 감지해 data/season_teams.json 에
기록한다. 프론트 사이드바의 '다음 시즌(개막 전)' 탭이 이 파일을 사용한다.

승격팀 로고·컬러는 teammeta 에 있어야 한다(없으면 경고 — teammeta 추가 필요).

사용:
    python src/detect_season_teams.py            # 프리뷰
    python src/detect_season_teams.py --write
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import teammeta as tm
from leagues import data_path
from sync_manager_profiles import fetch_source_managers, tracking_season_title

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "season_teams.json"


def _source_title(league: str, base_title: str) -> str:
    """리그별 위키 시즌문서 제목. tracking_season_title() 은 'PL' 표기이므로 치환."""
    if league == "EPL":
        return base_title
    if league == "LaLiga":
        return base_title.replace("Premier League", "La Liga")
    if league == "SerieA":
        return base_title.replace("Premier League", "Serie A")
    if league == "Bundesliga":
        return base_title.replace("Premier League", "Bundesliga")
    if league == "Ligue1":
        return base_title.replace("Premier League", "Ligue 1")
    raise SystemExit(f"[season-teams] 지원하지 않는 리그: {league}")


def _normalizer(league):
    """위키 팀명 → 우리 squad 표기 정규화기."""
    if league == "LaLiga":
        from fetch_laliga_managers import to_squad
        return to_squad
    if league == "SerieA":
        from fetch_serie_managers import to_squad
        return to_squad
    if league == "Bundesliga":
        from fetch_bundes_managers import to_squad
        return to_squad
    if league == "Ligue1":
        from fetch_ligue_managers import to_squad
        return to_squad
    return lambda t: t


def _out_path(league: str, override: Path | None) -> Path:
    if override is not None:
        return override
    return OUT_PATH if league == "EPL" else data_path("season_teams", league, ext="json")


def _label_from_title(title: str) -> str:
    """'2026-27 Premier League' → '26/27'."""
    m = re.search(r"(\d{4})-(\d{2})", title)
    return f"{m.group(1)[2:]}/{m.group(2)}" if m else ""


def _prev_season_teams(league: str) -> set[str]:
    """지난 시즌 팀 집합 — 실제 최종 순위(standings) 기준. 실패 시 teammeta."""
    try:
        import datastore as ds
        st = ds.read_table("standings", league=league)
        if st is not None and "squad" in st.columns and not st.empty:
            return set(st["squad"].astype(str))
    except Exception:
        pass
    return set(tm.TEAM_INFO.keys())


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--league", default="EPL", help="EPL | LaLiga")
    ap.add_argument("--season-title", default=None,
                    help="위키 시즌 문서 제목 override (기본: 날짜 기반, 예 '2026-27 Premier League')")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    league = args.league
    base_title = args.season_title or tracking_season_title()
    title = _source_title(league, base_title)
    norm = _normalizer(league)
    out_path = _out_path(league, args.out)
    label = _label_from_title(title)
    print(f"[season-teams] {league} tracking: {title} ({label})")

    try:
        src = fetch_source_managers(title)  # {team: manager} — 다음 시즌 팀
    except Exception as exc:
        print(f"[season-teams] ERROR fetch: {exc}", file=sys.stderr)
        return 1  # 기존 파일 유지(덮어쓰지 않음)

    # 위키 킷 스폰서 표(Front/Sleeve/Back 열) 등 팀이 아닌 파싱 잡음 제거
    _NOISE = {"Front", "Sleeve", "Back", "Kit", "Shirt", "Sponsor", "Chest", "Team"}
    next_teams = sorted({norm(t) for t in src.keys()} - _NOISE)
    if len(next_teams) < 10:
        print(f"[season-teams] 팀 수 비정상({len(next_teams)}) — 중단, 기존 파일 유지", file=sys.stderr)
        return 1

    prev = _prev_season_teams(league)
    promoted = sorted(set(next_teams) - prev)
    relegated = sorted(prev - set(next_teams))

    teams, missing = [], []
    for t in next_teams:
        logo, color = tm.team_logo(t), tm.team_color(t)
        if not logo:
            missing.append(t)
        teams.append({"name": t, "color": color, "logo": logo, "promoted": t in promoted})

    print(f"  teams={len(next_teams)}  promoted(IN)={promoted}  relegated(OUT)={relegated}")
    if missing:
        print(f"  ⚠ teammeta 로고/컬러 없음 — 추가 필요: {missing}", file=sys.stderr)

    out = {
        "season_label": label,
        "source_title": title,
        "detected_at": dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
        "teams": teams,
        "promoted": promoted,
        "relegated": relegated,
        "meta_missing": missing,
    }
    if args.write:
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"WROTE {out_path}")
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
