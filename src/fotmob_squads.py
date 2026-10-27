"""
FotMob 팀 스쿼드 — 등록 1군 전원(출전 없는 선수 포함)·세부 포지션·생년월일·등번호·국적·부상(복귀 예상) → data/fotmob_squads_{리그}_{시즌}.csv

계기(2026-10-22 사용자): 첼시 GK 마르티네스 부상인데 '대체 없음' — 백업 마이크 펜더르스(이번 시즌 0분)가 스쿼드에 없었고,
'Mahdi Jazuli MF 0세'처럼 나이가 빈 선수가 보였다. 점검(scripts/audit_squads.py): 8개 리그 등록 선수 4,524명 중 961명이
화면 스쿼드에 없었고 158명이 나이 없음. 또 사카(챔스 바이에른전 10분 부상 교체)가 부상 목록에 몇 시간 동안 없었다.
FotMob /api/data/teams?id= 의 squad 는 팀마다 감독·GK·수비·미드·공격 전원과 age·dateOfBirth·positionIdsDesc('RM,RB,LM')·
injured·injury.expectedReturn 을 준다 — 클라우드(GH Actions)에서도 받힌다. 팀당 요청 1번.

쓰는 곳: api/services/player_data._build_frame(나이·포지션 빈칸 채우기), api.main._roster_extras(출전 없는 등록 선수),
api.main._injuries_table(FotMob 이 표시한 부상자). 매일 daily_data·match_refresh 에서 받는다.

    python src/fotmob_squads.py [--league EPL]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import LEAGUES, SEASON, data_path  # noqa: E402

COLS = ["squad", "player", "fotmob_id", "group", "positions", "tm_position", "pos", "age", "birth_date", "shirt", "ccode",
        "injured", "expected_return", "fetched"]
GROUP_POS = {"keepers": "GK", "defenders": "DF", "midfielders": "MF", "attackers": "FW"}
# FotMob 세부 포지션 첫 값 → TM 세부 포지션 표기(우리 표의 tm_position 축 — positions.py·ratings_v3 가 읽는다)
TM_POS = {"GK": "Goalkeeper", "CB": "Centre-Back", "RB": "Right-Back", "RWB": "Right-Back", "LB": "Left-Back", "LWB": "Left-Back",
          "CDM": "Defensive Midfield", "DM": "Defensive Midfield", "CM": "Central Midfield", "CAM": "Attacking Midfield",
          "AM": "Attacking Midfield", "RM": "Right Midfield", "LM": "Left Midfield", "RW": "Right Winger", "LW": "Left Winger",
          "ST": "Centre-Forward", "CF": "Centre-Forward", "SS": "Second Striker"}
GROUP_TM = {"keepers": "Goalkeeper", "defenders": "Centre-Back", "midfielders": "Central Midfield", "attackers": "Centre-Forward"}


def tm_position(group: str, positions: str) -> str:
    first = str(positions or "").split(",")[0].strip().upper()
    return TM_POS.get(first) or GROUP_TM.get(group, "")


def team_rows(squad: str, tid: int, get) -> list[dict]:
    d = get(f"https://www.fotmob.com/api/data/teams?id={tid}") or {}
    groups = ((d.get("squad") or {}).get("squad")) or []
    today = dt.date.today().isoformat()
    out = []
    for g in groups:
        title = str(g.get("title") or "")
        if title not in GROUP_POS:                       # coach 등
            continue
        for m in g.get("members") or []:
            inj = m.get("injury") or {}
            pos = str(m.get("positionIdsDesc") or "")
            out.append({"squad": squad, "player": m.get("name"), "fotmob_id": str(m.get("id") or ""), "group": title,
                        "positions": pos, "tm_position": tm_position(title, pos), "pos": GROUP_POS[title],
                        "age": m.get("age"), "birth_date": m.get("dateOfBirth") or "", "shirt": m.get("shirtNumber"),
                        "ccode": m.get("ccode") or "", "injured": bool(m.get("injured")),
                        "expected_return": str(inj.get("expectedReturn") or "") if m.get("injured") else "", "fetched": today})
    return out


def collect(league: str, ids: dict[str, int], get, sleep: float = 0.4) -> pd.DataFrame:
    try:
        ours = list(pd.read_csv(data_path("standings", league))["squad"].astype(str))
    except (FileNotFoundError, KeyError):
        ours = []
    rows = []
    for sq in ours:
        tid = ids.get(sq)
        if not tid:
            continue
        try:
            rows += team_rows(sq, tid, get)
        except Exception as e:  # noqa: BLE001 — 한 팀 실패가 리그를 멈추지 않게
            print(f"  [{league}] {sq}: {type(e).__name__}")
        time.sleep(sleep)
    return pd.DataFrame(rows, columns=COLS)


def age_of(row) -> float | None:
    """생년월일이 있으면 오늘 기준 만 나이, 없으면 FotMob age."""
    b = str(row.get("birth_date") or "")
    try:
        d = dt.date.fromisoformat(b[:10])
        t = dt.date.today()
        return float(t.year - d.year - ((t.month, t.day) < (d.month, d.day)))
    except ValueError:
        a = pd.to_numeric(row.get("age"), errors="coerce")
        return float(a) if pd.notna(a) and a > 0 else None


def index(squads: pd.DataFrame) -> dict[str, dict[str, dict]]:
    """{클럽: {FotMob 이름: 행}}."""
    out: dict[str, dict[str, dict]] = {}
    if squads is None or squads.empty:
        return out
    for r in squads.to_dict("records"):
        out.setdefault(str(r.get("squad")), {})[str(r.get("player"))] = r
    return out


def find(idx: dict[str, dict[str, dict]], squad: str, name: str) -> dict | None:
    """같은 팀 FotMob 명단에서 그 선수(player_registry 규칙 — 'Mahdi Jazuli' ↔ 'Mahdi Nicoll-Jazuli')."""
    import player_registry as preg  # noqa: PLC0415
    team = idx.get(str(squad)) or {}
    if not team:
        return None
    if name in team:
        return team[name]
    hit, _ = preg.best_match(str(name), {n: n for n in team})
    return team.get(hit) if hit else None


def photo_ids_from_matches(frame: pd.DataFrame, rows: pd.DataFrame | None) -> pd.DataFrame:
    """명단에도 없는 출전 선수(유스·시즌 중 합류·임대) — FotMob 경기별 기록에서 같은 팀 선수의 번호로 사진만(fm_photo_id).
    2026-10-27: 사진 없는 149명 전원이 이번 시즌 뛴 선수였고 126명은 경기별 기록에 같은 팀·같은 이름으로 있었다.
    이름이 다르면(Jean Thierry Lazare ↔ Lazare Amani) 같은 팀에서 성(어느 한쪽의 마지막 낱말, 4자+)이 겹치거나 이름이
    비슷하고(0.75+) 출전 분이 가까운(±max(30, 20%)) 선수가 하나뿐일 때만 — 이름(첫 낱말)만 겹치는 'José López ↔ José Ángel'은
    잇지 않는다(틀린 얼굴이 이니셜보다 나쁘다). 이미 다른 선수가 쓰는 번호는 건너뛴다. 평점 연결(fm_id)엔 섞지 않는다."""
    import difflib  # noqa: PLC0415

    import player_registry as preg  # noqa: PLC0415
    if frame is None or frame.empty or rows is None or rows.empty or not {"squad", "player", "fotmob_id"} <= set(rows.columns):
        return frame
    has_tm = frame.get("tm_photo", pd.Series(None, index=frame.index)).map(lambda v: isinstance(v, str) and v.startswith("http"))
    num = lambda c: pd.to_numeric(frame[c], errors="coerce") if c in frame.columns else pd.Series(float("nan"), index=frame.index)  # noqa: E731
    need = ~has_tm & num("fm_id").isna() & num("fm_photo_id").isna()
    if not need.any():
        return frame
    used = {int(v) for c in ("fm_id", "fm_photo_id") for v in num(c).dropna()}
    r = rows[rows["fotmob_id"].notna()].copy()
    r["_fid"] = pd.to_numeric(r["fotmob_id"], errors="coerce")
    r["_m"] = pd.to_numeric(r.get("minutes"), errors="coerce").fillna(0)
    by_squad: dict[str, dict[int, tuple[str, float]]] = {}
    for (sq, fid), g in r.dropna(subset=["_fid"]).groupby(["squad", "_fid"]):
        by_squad.setdefault(str(sq), {})[int(fid)] = (str(g["player"].iloc[-1]), float(g["_m"].sum()))
    out = frame.copy()
    if "fm_photo_id" not in out.columns:
        out["fm_photo_id"] = None
    out["fm_photo_id"] = out["fm_photo_id"].astype("object")
    for i in out.index[need]:
        cands = {f: v for f, v in by_squad.get(str(out.at[i, "squad"]), {}).items() if f not in used}
        name = preg.norm(out.at[i, "player"])
        exact = [f for f, (p, _) in cands.items() if preg.norm(p) == name]
        pick = exact[0] if len(exact) == 1 else None
        if pick is None and not exact:
            mins = pd.to_numeric(out.at[i, "minutes"], errors="coerce")
            near = []
            for f, (p, m) in cands.items():
                pn = preg.norm(p)
                common = {t for t in set(name.split()) & set(pn.split()) if len(t) >= 4}
                surnames = {w.split()[-1] for w in (name, pn) if w.split()}
                alike = bool(common & surnames) or difflib.SequenceMatcher(None, name, pn).ratio() >= 0.75
                close = mins == mins and abs(m - float(mins)) <= max(30.0, 0.2 * float(mins))
                if alike and close:
                    near.append(f)
            pick = near[0] if len(near) == 1 else None
        if pick is not None:
            out.at[i, "fm_photo_id"] = pick
            used.add(pick)
    return out


def fill_frame(frame: pd.DataFrame, squads: pd.DataFrame, info: pd.DataFrame | None = None,
               match_rows: pd.DataFrame | None = None) -> pd.DataFrame:
    """선수 표의 빈 나이·세부 포지션을 FotMob 명단으로(있는 값은 그대로) — 명단에 없으면 선수 데이터(player_info)의 생년월일.
    '0세'·포지션 없음 방지. match_rows(FotMob 경기별 기록)가 있으면 명단에 없는 출전 선수의 사진 번호도."""
    if frame is None or frame.empty or ((squads is None or squads.empty) and (info is None or info.empty)):
        return photo_ids_from_matches(frame, match_rows)
    sq_part = squads if squads is not None and not squads.empty else pd.DataFrame(columns=COLS)
    if info is not None and not info.empty:     # 생년월일만 있는 행 — 명단 행 뒤에(명단이 먼저)
        extra = info[["squad", "player", "birth_date"]].assign(tm_position=None)
        sq_part = pd.concat([extra, sq_part], ignore_index=True)   # index() 는 나중 행이 덮으므로 명단을 뒤에
    idx = index(sq_part)
    # 이름으로 못 찾으면 FotMob 번호로(선수 표의 fm_id — src/rating_blend.attach) — 'Pepelu'↔'José Luis García Vayá' 처럼
    # 표기가 전혀 다른 선수는 이름 규칙으로 안 붙어 나이가 비었다(2026-10-27, 출전 시간 지문으로 번호가 붙은 선수)
    by_id: dict[str, dict] = {}
    if "fotmob_id" in sq_part.columns:
        for r in sq_part.to_dict("records"):
            try:
                by_id[str(int(float(r.get("fotmob_id"))))] = r
            except (TypeError, ValueError):
                continue
    age = pd.to_numeric(frame.get("age"), errors="coerce")
    need_age = age.isna() | (age <= 0)
    # 사진 번호 — TM 사진도 FotMob 평점 번호(fm_id)도 없는 선수(출전이 짧아 평점 표에 없음 등)는 명단의 FotMob 번호로 사진만.
    # 평점 연결(fm_id)엔 섞지 않는다(2026-10-27: 사진 없는 출전 선수 203명 중 56명)
    if "fm_id" in frame.columns:
        no_photo = frame["fm_id"].isna() & ~frame.get("tm_photo", pd.Series(None, index=frame.index)).map(
            lambda v: isinstance(v, str) and v.startswith("http"))
        if no_photo.any():
            frame = frame.copy()
            ids = []
            for i in frame.index:
                r = find(idx, frame.at[i, "squad"], frame.at[i, "player"]) if no_photo.loc[i] else None
                v = (r or {}).get("fotmob_id")
                try:
                    ids.append(int(float(v)) if v is not None and str(v) not in ("", "nan") else None)
                except (TypeError, ValueError):
                    ids.append(None)
            frame["fm_photo_id"] = ids
    frame = photo_ids_from_matches(frame, match_rows)
    tp = frame["tm_position"] if "tm_position" in frame.columns else pd.Series([None] * len(frame), index=frame.index)
    need_pos = ~tp.map(lambda v: isinstance(v, str) and bool(v.strip()))
    todo = frame.index[need_age | need_pos]
    if not len(todo):
        return frame
    frame = frame.copy()
    if "tm_position" not in frame.columns:
        frame["tm_position"] = None
    frame["age"] = pd.to_numeric(frame["age"], errors="coerce")
    for i in todo:
        r = find(idx, frame.at[i, "squad"], frame.at[i, "player"])
        if r is None and "fm_id" in frame.columns:
            try:
                r = by_id.get(str(int(float(frame.at[i, "fm_id"]))))
            except (TypeError, ValueError):
                r = None
        if r is None:
            continue
        if need_age.loc[i]:
            a = age_of(r)
            if a:
                frame.at[i, "age"] = a
        if need_pos.loc[i] and r.get("tm_position"):
            frame.at[i, "tm_position"] = r["tm_position"]
    return frame


INFO_COLS = ["squad", "player", "fotmob_id", "birth_date", "primary_team", "fetched"]


def player_info(league: str, frame: pd.DataFrame, get, cap: int = 200) -> pd.DataFrame:
    """1군 명단에 없는데 출전한 선수(유스 데뷔 — 'Mahdi Nicoll-Jazuli' 16세, 시즌 중 떠난 선수 — Beto → 피오렌티나)의 생년월일·
    지금 소속 — FotMob 선수 데이터(/api/data/playerData). FotMob id 는 경기별 평점 표에서(같은 팀·이름 규칙). 받은 선수는 다시 안 받는다."""
    import player_registry as preg  # noqa: PLC0415
    path = data_path("fotmob_player_info", league, SEASON)
    have = pd.read_csv(path, dtype={"fotmob_id": str}) if path.exists() else pd.DataFrame(columns=INFO_COLS)
    done = set(have["fotmob_id"].astype(str))
    try:
        mr = pd.read_csv(data_path("fotmob_match_ratings", league, SEASON), dtype={"fotmob_id": str},
                         usecols=["squad", "player", "fotmob_id"]).drop_duplicates()
    except (FileNotFoundError, ValueError):
        return have
    by_team = {sq: {str(p): str(f) for p, f in zip(g["player"], g["fotmob_id"])} for sq, g in mr.groupby("squad")}
    age = pd.to_numeric(frame.get("age"), errors="coerce")
    rows = []
    for sq, name in frame.loc[age.isna() | (age <= 0), ["squad", "player"]].itertuples(index=False):
        cands = by_team.get(str(sq)) or {}
        hit, _ = preg.best_match(str(name), {n: n for n in cands})
        fid = cands.get(hit) if hit else None
        if not fid or fid in done or len(rows) >= cap:
            continue
        d = get(f"https://www.fotmob.com/api/data/playerData?id={fid}") or {}
        bd = str(((d.get("birthDate") or {}).get("utcTime") or ""))[:10]
        rows.append({"squad": sq, "player": name, "fotmob_id": fid, "birth_date": bd,
                     "primary_team": (d.get("primaryTeam") or {}).get("teamName") or "", "fetched": dt.date.today().isoformat()})
        done.add(fid)
        time.sleep(0.3)
    if not rows:
        return have
    out = pd.concat([have, pd.DataFrame(rows, columns=INFO_COLS)], ignore_index=True)
    out.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    return out


def injured_rows(squads: pd.DataFrame) -> list[dict]:
    """FotMob 이 부상으로 표시한 선수 → fotmob_injuries 와 같은 열(kind=injury)."""
    if squads is None or squads.empty or "injured" not in squads.columns:
        return []
    inj = squads[squads["injured"].astype(str).str.lower().isin({"true", "1"})]
    return [{"squad": r["squad"], "player": r["player"], "fotmob_id": str(r.get("fotmob_id") or ""), "kind": "injury",
             "expected_return": str(r.get("expected_return") or ""), "match_id": "", "match_date": "",
             "fetched": r.get("fetched")} for r in inj.to_dict("records")]


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    a = ap.parse_args(argv)
    from fetch_fotmob_ratings import FOTMOB_ID, _get  # noqa: PLC0415
    from news_wires import fotmob_team_ids  # noqa: PLC0415
    ids = fotmob_team_ids()
    bad = 0
    # 라이트 리그는 src/lite_league.py 가 같은 팀 응답으로 명단까지 쓴다(요청 중복 방지)
    for lg in [a.league] if a.league else [x for x in LEAGUES if x in FOTMOB_ID and not LEAGUES[x].lite]:
        df = collect(lg, ids, _get)
        if df.empty:
            print(f"[{lg}] 스쿼드 0명 — 건너뜀")
            bad += 1
            continue
        df.to_csv(data_path("fotmob_squads", lg, SEASON), index=False, encoding="utf-8", lineterminator="\n")
        print(f"[{lg}] {df['squad'].nunique()}팀 · {len(df)}명 · 부상 {int(df['injured'].sum())}명 -> {data_path('fotmob_squads', lg, SEASON).name}")
        try:                                            # 명단에 없는 출전 선수의 생년월일(유스 데뷔·시즌 중 이적)
            import datastore as ds  # noqa: PLC0415
            full = ds.read_table("players_full", league=lg)
            if full is not None:
                info = player_info(lg, fill_frame(full, df), _get)
                print(f"    생년월일 보강 표 {len(info)}명")
        except Exception as e:  # noqa: BLE001
            print(f"    [player_info] 건너뜀 {type(e).__name__}: {e}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
