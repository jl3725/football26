"""
리그 출전 선수 줄 보강 — 주간 선수 표(players_full, 큰 리그는 이 PC 의 FBref 주간 빌드)에 없는 이번 시즌 리그 출전 선수를
FotMob 경기별 기록(fotmob_match_ratings, 클라우드 매일·경기 20분 뒤)으로 더한다.

2026-11-03 사용자: '메슬리에가 EFL컵에 뛰었는데 출전 없음'. 조사해 보니
  · FBref 가 차단돼 주간 빌드가 10/13 에 받아 둔 캐시만 다시 읽으며 'ok' — 그 뒤 리그에 처음 나온 선수(펜더스·고레츠카·
    판덴베르흐 …)가 선수 표에 아예 없어 스쿼드에서 '출전 없음'(TM 명단 보강 줄)으로 보였다.
  · 원천마다 이름이 다른 선수(FBref 'Bachir Belloumi' ↔ FotMob 'Mohamed Belloumi', 'Kostas' ↔ 'Konstantinos Tsimikas')는
    FotMob 리그 분이 안 붙고 TM 명단 줄로 한 번 더 나왔다.

규칙
  · 같은 사람: 같은 팀에서 이름이 같거나(player_registry.best_match) 성이 같고 그 성이 양쪽 팀 명단에서 하나뿐일 때.
    맞으면 그 줄에 FotMob 번호(`_fm_hint`)를 적어 rating_blend.attach 가 이름 대신 번호로 평점·분을 붙인다.
  · 새 줄: 리그 출전 분 > 0 인데 표에 없는 선수. 세부 지표는 0·덮은 분 0 으로 두어 뒤 단계(season_totals.apply_live_totals 가
    골·도움·분, allcomp_stats.top_up_league 가 세부 지표 전부)가 FotMob 경기 기록으로 채운다. 포지션·나이 = FotMob 명단,
    시장가치·국적·계약·사진·tm_id = TM 계약표, 지난 시즌 기록(prev_*·hist_*) = attach_prev_season 그대로. `_live_debut` 열.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from unidecode import unidecode

FILL_ZERO_SKIP = {"minutes", "age", "market_value_eur", "tm_id"}
POS_OF_GROUP = {"GK": "GK", "DF": "DF", "MF": "MF", "FW": "FW", "keepers": "GK", "defenders": "DF",
                "midfielders": "MF", "attackers": "FW"}


def _fid(v) -> str | None:
    try:
        return str(int(float(v))) if v is not None and v == v and float(v) > 0 else None
    except (TypeError, ValueError):
        return None


def _has(v) -> bool:
    return v is not None and not (isinstance(v, float) and v != v) and v is not pd.NA and str(v) not in ("", "nan", "None")


def _sur(name) -> str:
    from short_name import surname  # noqa: PLC0415
    return " ".join(unidecode(surname(str(name or ""))).lower().replace("-", " ").split())


def match_in_squad(name: str, names: list[str], other_names: list[str] | None = None) -> str | None:
    """같은 팀 표 이름들(names) 가운데 같은 사람 — 이름 규칙(레지스트리) → 성이 양쪽에서 하나뿐일 때 성."""
    import player_registry as preg  # noqa: PLC0415
    if not names:
        return None
    if name in names:
        return name
    hit, _ = preg.best_match(str(name), {n: n for n in names})
    if hit:
        return hit
    s = _sur(name)
    if len(s) < 3:
        return None
    mine = [n for n in names if _sur(n) == s]
    theirs = [n for n in (other_names or [name]) if _sur(n) == s]
    return mine[0] if len(mine) == 1 and len(theirs) <= 1 else None


def league_players(mr: pd.DataFrame | None, league: str) -> pd.DataFrame:
    """이번 시즌 리그 경기(분 > 0) 선수 — FotMob 번호 단위 [fid, squad(마지막 경기), player, minutes]."""
    from season_totals import league_code  # noqa: PLC0415
    code = league_code(league)
    if mr is None or mr.empty or not code or "comp_code" not in mr.columns:
        return pd.DataFrame(columns=["fid", "squad", "player", "minutes"])
    d = mr[(mr["comp_code"].astype(str) == code)].copy()
    d["minutes"] = pd.to_numeric(d["minutes"], errors="coerce").fillna(0)
    d = d[d["minutes"] > 0]
    if d.empty:
        return pd.DataFrame(columns=["fid", "squad", "player", "minutes"])
    d["fid"] = d["fotmob_id"].map(_fid)
    d = d.sort_values("date")
    d["fid"] = d["fid"].fillna("n:" + d["squad"].astype(str) + "|" + d["player"].astype(str))
    gk = sum(pd.to_numeric(d[c], errors="coerce").fillna(0) for c in ("saves", "xgot_faced", "high_claim") if c in d.columns)
    d["_gk"] = (gk > 0) if not isinstance(gk, int) else False
    g = d.groupby("fid")
    return pd.DataFrame({"squad": g["squad"].last(), "player": g["player"].last(),
                         "minutes": g["minutes"].sum(), "gk": g["_gk"].any()}).reset_index()


def add_debuts(frame: pd.DataFrame, mr: pd.DataFrame | None, league: str, squads: pd.DataFrame | None = None,
               contracts: pd.DataFrame | None = None, prev_read=None, season_start: int | None = None,
               version=None, squads_read=None) -> pd.DataFrame:
    """frame 에 `_fm_hint`(같은 사람으로 맞춘 FotMob 번호)·`_live_debut` 열을 달고 리그 출전인데 없는 선수 줄을 더한다."""
    out = frame.copy()
    out["_fm_hint"] = None
    out["_live_debut"] = False
    lp = league_players(mr, league)
    if lp.empty:
        return out
    by_squad: dict[str, list[str]] = {}
    for i, sq, pl in zip(out.index, out["squad"].astype(str), out["player"].astype(str)):
        by_squad.setdefault(sq, []).append(pl)
    row_of = {(str(sq), str(pl)): i for i, sq, pl in zip(out.index, out["squad"], out["player"])}
    fm_names: dict[str, list[str]] = {}
    for sq, pl in zip(lp["squad"].astype(str), lp["player"].astype(str)):
        fm_names.setdefault(sq, []).append(pl)
    reg = _registered(squads, contracts)
    new = []
    for r in lp.itertuples():
        sq, pl = str(r.squad), str(r.player)
        hit = match_in_squad(pl, by_squad.get(sq, []), fm_names.get(sq))
        if hit is not None:
            if not str(r.fid).startswith("n:"):
                out.at[row_of[(sq, hit)], "_fm_hint"] = str(r.fid)
            continue
        if sq not in by_squad:                           # 표에 없는 팀(리그 표기 차이) — 만들지 않는다
            continue
        ids, names = reg.get(sq, (set(), []))
        if (ids or names) and str(r.fid) not in ids and match_in_squad(pl, names) is None:
            continue                                      # 지금 그 팀 명단에 없음 = 시즌 중 떠난 선수(우테마데 → 유벤투스) —
            #                                               옛 팀 줄은 _build_frame 이 일부러 지운다(_moved_out)
        new.append((str(r.fid), sq, pl, bool(r.gk)))
    if not new:
        return out
    groups = _groups_by_id(squads_read, version) if squads_read is not None else {}
    rows = [_new_row(out, fid, sq, pl, squads, contracts, gk, groups.get(fid)) for fid, sq, pl, gk in new]
    add = pd.DataFrame(rows)
    if prev_read is not None and season_start is not None:
        add = _attach_prev(add, prev_read, season_start, version)
    add = add.reindex(columns=list(dict.fromkeys([*out.columns, *add.columns])))
    for c in add.columns:                                 # pd.NA(attach_prev) → NaN, 숫자 열은 숫자로 — ratings_v3 가 NaN 만 안다
        add[c] = add[c].map(lambda v: np.nan if v is pd.NA or v is None else v)
        if c in out.columns and pd.api.types.is_numeric_dtype(out[c]):
            add[c] = pd.to_numeric(add[c], errors="coerce")
    return pd.concat([out, add], ignore_index=True)


_GROUP_CACHE: dict = {}


def _groups_by_id(read, version=None) -> dict[str, str]:
    """{FotMob 번호: 포지션 그룹} — 전 리그 FotMob 명단. 시즌 중 다른 리그로 떠난 선수(첫 경기만 뛰고 이적)도 포지션을 찾게."""
    if version in _GROUP_CACHE:
        return _GROUP_CACHE[version]
    from leagues import LEAGUES  # noqa: PLC0415
    out: dict[str, str] = {}
    for lg in LEAGUES:
        t = read(lg)
        if t is None or t.empty or "fotmob_id" not in t.columns:
            continue
        for f, g in zip(t["fotmob_id"], t.get("group", t.get("pos"))):
            k = _fid(f)
            if k and _has(g):
                out.setdefault(k, str(g))
    _GROUP_CACHE.clear()
    _GROUP_CACHE[version] = out
    return out


def _registered(squads, contracts) -> dict[str, tuple[set[str], list[str]]]:
    """{팀: (FotMob 번호들, 이름들)} — 지금 그 팀 명단(FotMob 1군 명단 ∪ TM 계약표)."""
    out: dict[str, tuple[set[str], list[str]]] = {}
    for t, has_id in ((squads, True), (contracts, False)):
        if t is None or t.empty or "squad" not in t.columns:
            continue
        for r in t.to_dict("records"):
            ids, names = out.setdefault(str(r.get("squad")), (set(), []))
            names.append(str(r.get("player")))
            if has_id and _fid(r.get("fotmob_id")):
                ids.add(_fid(r.get("fotmob_id")))
    return out


def _new_row(frame: pd.DataFrame, fid: str, squad: str, player: str, squads, contracts, gk: bool = False,
             group: str | None = None) -> dict:
    import allcomp_stats as acs  # noqa: PLC0415
    import fotmob_squads as fsq  # noqa: PLC0415
    row = {c: None for c in frame.columns}
    mate = frame[frame["squad"].astype(str) == squad]
    if not mate.empty:                                    # 팀 단위 값(팀 득실 강도 …)은 같은 팀 줄에서
        for c in frame.columns:
            if c.startswith("team_"):
                row[c] = mate.iloc[0][c]
    for c in acs.MAP:                                     # 세부 지표 0 + 덮은 분 0 → top_up_league 가 FotMob 경기로 전부 채움
        if c in frame.columns and c not in FILL_ZERO_SKIP:
            row[c] = 0.0
    for c in ("ss_minutes", "goals", "assists"):
        if c in frame.columns:
            row[c] = 0
    row.update({"player": player, "squad": squad, "minutes": 0.0, "norm_key": unidecode(player).lower().strip(),
                "_fm_hint": None if fid.startswith("n:") else fid, "_live_debut": True})
    f = fsq.find(fsq.index(squads), squad, player) if squads is not None and not squads.empty else None
    if f is not None:
        g = str(f.get("group") or f.get("pos") or "")
        row["pos"] = POS_OF_GROUP.get(g, g[:2].upper() if g else None)
        row["age"] = fsq.age_of(f)
        if _has(f.get("tm_position")):
            row["tm_position"] = f.get("tm_position")
    if contracts is not None and not contracts.empty and "squad" in contracts.columns:
        ct = contracts[contracts["squad"].astype(str) == squad]
        names = [str(n) for n in ct["player"]]
        hit = match_in_squad(player, names)
        if hit is not None:
            c = ct[ct["player"].astype(str) == hit].iloc[0]
            for src, dst in (("tm_id", "tm_id"), ("market_value_eur", "market_value_eur"), ("nationality", "nationality"),
                             ("tm_position", "tm_position"), ("tm_photo", "tm_photo"), ("contract_until", "tm_contract_until"),
                             ("joined_date", "tm_joined_date"), ("contract_signal", "tm_contract_signal"),
                             ("norm_key", "norm_key")):
                if _has(c.get(src)):
                    row[dst] = c.get(src)
            if not _has(row.get("age")) and _has(c.get("age")):
                row["age"] = c.get("age")
    if not _has(row.get("pos")) and group:                # 팀을 떠난 선수 — 전 리그 FotMob 명단에서 번호로
        row["pos"] = POS_OF_GROUP.get(group, group[:2].upper())
    if not _has(row.get("pos")):
        tp = str(row.get("tm_position")).lower() if _has(row.get("tm_position")) else ""
        row["pos"] = ("GK" if "keeper" in tp else "DF" if "back" in tp else "FW" if any(w in tp for w in ("forward", "winger", "striker"))
                      else "MF")
    if gk:                                                # 선방·유효 슈팅 상대 기록 = 골키퍼(명단·TM 이 없어도)
        row["pos"] = "GK"
    return row


_PREV_CACHE: dict = {}                                    # (시즌 시작 해, DB 버전) → 지난 시즌 전 리그 표(필요 열만)


def _attach_prev(add: pd.DataFrame, read, season_start: int, version=None) -> pd.DataFrame:
    import attach_prev_season as aps  # noqa: PLC0415

    def loader(s):
        k = (s, version)
        if k not in _PREV_CACHE:
            if len(_PREV_CACHE) > 6:
                _PREV_CACHE.clear()
            _PREV_CACHE[k] = aps.load_prev(s, read=read)
        return _PREV_CACHE[k]
    try:
        a, _ = aps.attach(add, loader(season_start))
        return aps.attach_hist(a, season_start, loader=loader)
    except Exception as e:  # noqa: BLE001 — 지난 시즌 표가 없으면 이번 시즌 기록만
        print(f"[live_roster] 지난 시즌 기록 건너뜀 {type(e).__name__}: {e}")
        return add
