"""선수 데이터 로딩과 API 표시용 공통 변환."""
from __future__ import annotations

import re

import pandas as pd
from unidecode import unidecode

import api.bootstrap  # noqa: F401
import datastore as ds
from leagues import data_path

_EXTRA_PHOTO_CACHE: dict[str, dict[str, str]] = {}


def number(value, default=0.0):
    try:
        converted = float(value)
        return default if pd.isna(converted) else converted
    except (TypeError, ValueError):
        return default


def photo_url(row) -> str:
    """TM 사진 → 없으면 FotMob 사진(fm_id, src/rating_blend.attach) — TM 매칭이 안 된 주전급 70여 명이 이니셜로 나왔다."""
    photo = row.get("tm_photo")
    fid = row.get("fm_id")
    if photo is not None and not pd.isna(photo) and str(photo).startswith("http"):
        # TM id 로 짐작해 만든 주소('…/portrait/medium/708086.png')는 실제 파일명(…-1780663789.jpg)이 아니라 404 가 난다
        # (2026-10-19 점검: 15명) — FotMob 사진이 있으면 그쪽
        if not (re.search(r"/portrait/medium/\d+\.png$", str(photo)) and fid is not None and not pd.isna(fid)):
            return str(photo)
    try:
        if fid is not None and not pd.isna(fid) and int(fid) > 0:
            return f"https://images.fotmob.com/image_resources/playerimages/{int(fid)}.png"
    except (TypeError, ValueError):
        pass
    return ""


def extra_photo_map(league: str) -> dict[str, str]:
    """players_full에 없는 선수의 Transfermarkt 사진 폴백."""
    if league in _EXTRA_PHOTO_CACHE:
        return _EXTRA_PHOTO_CACHE[league]

    result: dict[str, str] = {}
    for table, photo_column in (
        ("transfers", "photo"),
        ("transfermarkt_contracts", "tm_photo"),
        ("transfermarkt_injuries", "tm_photo"),
    ):
        frame = ds.read_table(table, league=league)
        if (
            frame is None
            or photo_column not in frame.columns
            or "player" not in frame.columns
        ):
            continue
        for _, row in frame.iterrows():
            photo = str(row.get(photo_column) or "")
            if photo.startswith("http"):
                key = unidecode(str(row.get("player"))).lower().strip()
                result.setdefault(key, photo)

    _EXTRA_PHOTO_CACHE[league] = result
    return result


def resolve_photo(name, resolve, league: str) -> str:
    """이름 → players_full 사진, 없으면 Transfermarkt 폴백."""
    if not name:
        return ""
    row = resolve(name)
    photo = photo_url(row) if row is not None else ""
    key = unidecode(str(name)).lower().strip()
    return photo or extra_photo_map(league).get(key, "")


_FRAME_CACHE: dict = {}

# 배포 빌드에서 미리 만든 선수 표·출전 포지션 집계(scripts/precompute_team_units.py → data/runtime_cache/).
# Render 무료(0.1 CPU)는 깰 때마다 8개 리그 × 두 시즌 표를 다시 만드느라(로컬 20~40초 → 운영 수 분)
# 홈 빅매치·Overview 가 70초 제한을 넘겼다(2026-10-15). DB 파일 시각(스탬프)이 같을 때만 쓴다.
RUNTIME_CACHE = ds.DB_PATH.parent / "runtime_cache"


def _db_size() -> int:
    try:
        return ds.DB_PATH.stat().st_size
    except OSError:
        return -1


def same_build(stamp, size) -> bool:
    """캐시가 지금 DB 로 만든 것인가 — DB 파일 시각이 같으면 그렇다. Render 는 빌드한 DB 를 그대로 싣고
    가는데 옮기면서 파일 시각이 바뀔 수 있어, Render(환경변수 RENDER)에서는 파일 크기가 같으면 같은 배포본으로 본다."""
    import os  # noqa: PLC0415
    if stamp == ds._db_mtime():
        return True
    return bool(os.environ.get("RENDER")) and size is not None and size == _db_size()


def _disk_get(name: str):
    import pickle  # noqa: PLC0415
    path = RUNTIME_CACHE / name
    try:
        if path.exists():
            with path.open("rb") as f:
                obj = pickle.load(f)
            if same_build(obj.get("stamp"), obj.get("size")):
                return obj["data"]
    except Exception:  # noqa: BLE001 — 깨진·옛 캐시는 무시하고 다시 만든다
        return None
    return None


def disk_put(name: str, data) -> None:
    import pickle  # noqa: PLC0415
    RUNTIME_CACHE.mkdir(parents=True, exist_ok=True)
    with (RUNTIME_CACHE / name).open("wb") as f:
        pickle.dump({"stamp": ds._db_mtime(), "size": _db_size(), "data": data}, f, protocol=pickle.HIGHEST_PROTOCOL)


def frame_cache_name(league: str, season: str | None) -> str:
    return f"frame_{league}_{season or 'cur'}.pkl"


def player_frame(league: str, season: str | None = None):
    """players_full과 대회별 선발 수를 합친 선수 데이터 단일 진입점.

    리그 레벨(_league_level)과 리그 내 순위 폼(_form)을 붙인다. 요청마다 수십 번 불리므로 DB 수정
    시각 기준으로 캐시하고, 호출부가 고쳐 써도 안전하게 사본을 준다. season(예: "2025_2026")을 주면
    그 시즌 표(지난 시즌 대비 성장 계산용).
    """
    key = (league, season, ds._db_mtime())
    hit = _FRAME_CACHE.get(key)
    if hit is not None:
        return hit.copy()
    frame = _disk_get(frame_cache_name(league, season))
    if frame is None:
        frame = _build_frame(league, season)
    if frame is not None:
        if len(_FRAME_CACHE) > 24:      # 8개 리그 × 이번·지난 시즌(16) + 여유 — 넘치면 전부 비워 다시 계산하므로 넉넉히
            _FRAME_CACHE.clear()
        _FRAME_CACHE[key] = frame
        return frame.copy()
    return None


_MOVED_CACHE: dict = {}
_ROLE_CACHE: dict = {}


def role_counts(season: str | None = None) -> dict:
    """전 리그 ESPN 선발(그 시즌 1.0 + 직전 시즌 0.5) → {정규화 이름: Counter(역할)} — src/positions.py."""
    import positions as ps  # noqa: PLC0415
    from leagues import DATA_DIR, SEASON_START  # noqa: PLC0415
    from player_names import read_lineup_csv  # noqa: PLC0415
    start = int(season[:4]) if season else SEASON_START
    key = (start, ds._db_mtime())
    if key in _ROLE_CACHE:
        return _ROLE_CACHE[key]
    disk = _disk_get(f"roles_{start}.pkl")
    if disk is not None:
        _ROLE_CACHE[key] = disk
        return disk
    frames, weights = [], []
    for tag, w in ((f"{start}_{start + 1}", 1.0), (f"{start - 1}_{start}", 0.5)):
        for path in sorted(DATA_DIR.glob(f"espn_lineups*_{tag}.csv")):
            try:
                frames.append(read_lineup_csv(path, ["squad", "event_id", "formation", "starter", "player",
                                                     "espn_pos", "formation_place"]))   # 이름 정규화
                weights.append(w)
            except (ValueError, OSError):
                continue
    if len(_ROLE_CACHE) > 4:          # 이번·지난 시즌 둘을 번갈아 부르므로 하나만 남기면 매번 다시 계산했다
        _ROLE_CACHE.clear()
    _ROLE_CACHE[key] = ps.role_counts(frames, weights)
    return _ROLE_CACHE[key]


def _played_line(frame: pd.DataFrame, season: str | None) -> list:
    """실제로 선 자리(선발 3회+)의 라인 — TM 이 '수비형 미드'로 둔 풀백(Lewis-Skelly) 등을 실제 역할로."""
    import positions as ps  # noqa: PLC0415
    rc = role_counts(season)
    out = []
    for name, tmp in zip(frame["player"], frame.get("tm_position", pd.Series([None] * len(frame), index=frame.index))):
        prof = ps.profile(ps.lookup(rc, name), tmp if isinstance(tmp, str) else None)
        out.append(ps.LINE_OF.get(prof.get("primary")) if prof.get("source") != "tm" else None)
    return out


def _nk(row) -> str:
    k = row.get("norm_key")
    return unidecode(str(k if isinstance(k, str) and k.strip() else row.get("player") or "")).lower().strip()


def _moved_out(season: str | None) -> set[tuple[str, str]]:
    """(norm_key, 떠난 팀) — 다른 팀(전 리그)에 TM 매칭된 행이 있고 그 행의 직전 팀이 이 팀인 선수."""
    from leagues import LEAGUES  # noqa: PLC0415
    key = (season, ds._db_mtime())
    if key in _MOVED_CACHE:
        return _MOVED_CACHE[key]
    out: set[tuple[str, str]] = set()
    for lg in LEAGUES:
        f = ds.read_table("players_full", league=lg, season=season)
        if f is None or "tm_id" not in f.columns or "prev_squad" not in f.columns:
            continue
        for _, r in f[f["tm_id"].notna() & f["prev_squad"].notna()].iterrows():
            if r["prev_squad"] != r.get("squad"):
                out.add((_nk(r), str(r["prev_squad"])))
    _MOVED_CACHE.clear()
    _MOVED_CACHE[key] = out
    return out


def _build_frame(league: str, season: str | None = None):
    frame = ds.read_table("players_full", league=league, season=season)
    if frame is None:
        return None

    frame = frame.copy()
    # 이적 전 팀 잔류 행 제거 — 시즌 중 옮긴 선수의 옛 팀 행(TM 매칭 없음)이 리그 목록에 중복으로 남아
    # 'Enzo Fernández(Chelsea) 89' 처럼 보였다. 새 팀 행의 직전 팀이 이 팀일 때만(동명이인 보호).
    if "tm_id" in frame.columns:
        moved = _moved_out(season)
        if moved:
            stale = frame["tm_id"].isna() & pd.Series(
                [(_nk(r), str(r.get("squad"))) in moved for _, r in frame.iterrows()], index=frame.index)
            frame = frame[~stale].copy()
    # 평점 리그 보정용(ratings_v3) — 행마다 리그 레벨을 실어 어느 호출부에서든 같은 보정이 되게
    import league_level  # noqa: PLC0415
    frame["_league_level"] = league_level.level(league)
    if "norm_key" not in frame.columns:
        frame["norm_key"] = None
    missing = frame["norm_key"].isna() | frame["norm_key"].astype(str).str.strip().isin(
        ["", "nan", "None"]
    )
    if missing.any():
        frame.loc[missing, "norm_key"] = frame.loc[missing, "player"].map(
            lambda value: unidecode(str(value)).lower().strip()
        )

    try:
        usage = pd.read_csv(
            data_path("player_comp_usage", league, season),
            usecols=[
                "squad",
                "norm_key",
                "ucl_starts",
                "uel_starts",
                "conf_starts",
                "cup_starts",
            ],
        )
        frame = frame.merge(usage, on=["squad", "norm_key"], how="left")
    except (OSError, KeyError, ValueError):
        pass
    # 평점 = Sofascore + FotMob 두 출처 평균(src/rating_blend.py) — 직전·2시즌 전 기록도 FotMob 으로 보강
    try:
        import rating_blend as rb  # noqa: PLC0415
        frame = rb.blend(rb.attach(frame, league, season, lambda lg, s: ds.read_table("fotmob_ratings", league=lg, season=s)))
    except Exception as e:  # noqa: BLE001 — FotMob 표가 없으면 Sofascore 만
        print(f"[rating_blend] {league} {season}: 건너뜀 {type(e).__name__}: {e}")
    # 골·도움·출전 분을 경기 직후 값으로 — FotMob 리그 경기 합이 FBref(주간)보다 최신일 때(src/season_totals.py).
    # 2026-10-20 사용자: 홀란 리그 8골인데 6골. OVR·리더·득점왕이 모두 이 표를 읽으므로 여기 한 곳에서.
    if season is None:
        try:
            import season_totals as st  # noqa: PLC0415
            # xG 계열 먼저(FBref 분과 비교해야 하므로 FotMob 이 분을 바꾸기 전에) — Understat 매일, 5대 리그
            frame = st.apply_understat_live(frame, ds.read_table("understat_players", league=league))
            frame = st.apply_live_totals(frame, ds.read_table("fotmob_match_ratings", league=league), league)
            frame = st.apply_gk_live(frame, ds.read_table("players_sofascore_stats", league=league))   # GK 클린시트% 최신
        except Exception as e:  # noqa: BLE001 — 경기별 기록이 없으면 FBref 그대로
            print(f"[season_totals] {league}: 건너뜀 {type(e).__name__}: {e}")
    import ratings_v3 as rv3  # noqa: PLC0415
    try:
        frame["_line"] = _played_line(frame, season)
    except Exception:  # noqa: BLE001 — 라인업이 없으면 TM 역할로
        frame["_line"] = None
    frame = rv3.add_form_column(frame)
    # 최근 폼(최근 3·5경기, 전 대회) — FotMob 경기별 평점(src/recent_form.py). 지난 시즌 표엔 붙이지 않는다
    if season is None:
        try:
            import recent_form as rf  # noqa: PLC0415
            frame = rf.add_recent_form(frame, ds.read_table("fotmob_match_ratings", league=league))
        except Exception as e:  # noqa: BLE001 — 경기별 평점 표가 없으면 시즌 폼만
            print(f"[recent_form] {league}: 건너뜀 {type(e).__name__}: {e}")
    # OVR 은 행 데이터만으로 정해지므로 표를 만들 때 한 번만 — 추천 1회에 3,500번 다시 계산하던 것
    frame["_ovr"] = [rv3.ovr_of_row(r) for _, r in frame.iterrows()]
    return frame
