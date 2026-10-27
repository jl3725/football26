"""
대표팀 경기 선수 평점 → data/fotmob_intl_ratings_{시즌}.csv — OVR 경기력의 '리그 밖 표본'(src/allcomp_stats.py)에 더한다.

2026-10-27 사용자: '하베르츠 85·에제 84 정도 아닌가 — 국대 활약도 넣자'. 유럽·컵(2026-10-21)처럼 대표팀 경기도 평점 표본이다
(월드컵·대륙 대회·네이션스리그·예선·친선). 상대 수준은 allcomp_stats.intl_level 이 FIFA 랭킹 점수로 붙인다.
- 대회: FotMob 전체 대회 목록(/api/data/allLeagues 'international')에서 남자 A대표팀 대회만 — 이름 규칙(여자·연령별·올림픽,
  intl_comps.NOT_SENIOR + '(W)')을 먼저 거르고, 경기 팀 이름 대부분이 FIFA 회원국(data/fifa_ranking.csv)인 대회만 남긴다.
  클럽 대회(챔스·리베르타도레스·클럽 친선)·자선 경기는 팀 이름이 나라가 아니라 빠진다. 대회 id 를 코드에 적지 않는다.
- 기간: 지난 시즌 시작(SEASON_START−1 년 7/25)부터 — OVR 은 이번·지난 시즌만 쓴다. 대회마다 FotMob 현재 시즌과 그 앞 시즌을 본다.
- 선수: 우리 리그 선수(FotMob id — fotmob_squads·fotmob_ratings·fotmob_match_ratings)만 남긴다.
- 이미 받은 경기는 다시 받지 않는다. 우리 선수가 없는 경기도 빈 줄(fotmob_id 빈칸)을 남겨 다시 받지 않는다.
- 시즌 = 경기 날짜(7/25 경계) — 6~7월 월드컵은 끝난 시즌(지난 시즌 표본, prev_x), 9월부터는 이번 시즌.
- 행: match_id, date, comp_id, comp, friendly, nation, opponent, nation_points·opp_points(받을 때 FIFA 랭킹 점수 — 서버가 나라 이름을
  다시 맞추지 않게), fotmob_id, player, club, league, minutes, rating, goals, assists

사용: python src/fetch_fotmob_intl.py [--max 600]
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_fotmob_matches import _stats, finished  # noqa: E402
from fetch_fotmob_ratings import _get  # noqa: E402
from leagues import LEAGUES, SEASON_START, data_path  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
TABLE = "fotmob_intl_ratings"
COLS = ["match_id", "date", "comp_id", "comp", "friendly", "nation", "opponent", "nation_points", "opp_points",
        "fotmob_id", "player", "club", "league", "minutes", "rating", "goals", "assists"]
SEASON_EDGE = "07-25"            # 이 날부터 새 시즌 — 7월 중순 끝나는 월드컵·유로는 끝난 시즌에
NATION_SHARE = 0.6               # 경기 팀 이름 중 FIFA 회원국 비율이 이 이상이면 대표팀 대회


def season_of(date: str) -> str:
    y = int(date[:4])
    y = y if date[5:10] >= SEASON_EDGE else y - 1
    return f"{y}_{y + 1}"


def senior_name(name: str) -> bool:
    from intl_comps import NOT_SENIOR  # noqa: PLC0415
    return not NOT_SENIOR.search(name) and not re.search(r"\(W\)|\bW\b", name)


def nation_index() -> dict[str, tuple[str, float]]:
    """정규화한 나라 이름 → (FIFA 표기, 랭킹 점수). TM·위키 표기 별칭(fetch_intl)도 같은 나라로."""
    import player_registry as preg  # noqa: PLC0415
    from fetch_intl import FIFA_NAME, NATION_TITLE  # noqa: PLC0415
    p = DATA / "fifa_ranking.csv"
    if not p.exists():
        return {}
    f = pd.read_csv(p)
    out = {preg.norm(r.team): (str(r.team), float(r.points)) for r in f.itertuples()}
    for tm, fifa in FIFA_NAME.items():
        if preg.norm(fifa) in out:
            out.setdefault(preg.norm(tm), out[preg.norm(fifa)])
            if tm in NATION_TITLE:
                out.setdefault(preg.norm(NATION_TITLE[tm]), out[preg.norm(fifa)])
    for tm, title in NATION_TITLE.items():
        if preg.norm(tm) in out:
            out.setdefault(preg.norm(title), out[preg.norm(tm)])
    return out


def nation_of(name: str, idx: dict) -> tuple[str, float] | None:
    """FotMob 나라 이름 → (FIFA 표기, 점수). 정확히 → 규칙(FIFA 표기에 낱말이 다 들어 있음 'China'⊂'China PR' ·
    약어 'UAE' · 앞부분 'Kyrgyzstan'~'Kyrgyz' · Saint=St) → 유사도. 비회원(보네르·마르티니크)은 None(약체 기본값)."""
    import difflib  # noqa: PLC0415

    import player_registry as preg  # noqa: PLC0415

    def canon(s: str) -> str:
        return " ".join("st" if w in ("saint", "st") else w for w in re.sub(r"[,()]", " ", s).split())
    k = canon(preg.norm(name))
    if not k:
        return None
    keys = {canon(x): x for x in idx}
    if k in keys:
        return idx[keys[k]]
    toks = k.split()
    sub = [(len(c.split()), x) for c, x in keys.items() if set(toks) <= set(c.split())]
    cands = [x for n, x in sub if n == min(n for n, _ in sub)] if sub else []   # 'China' → China PR(군더더기 가장 적은 쪽)
    if not cands and str(name).isupper() and 2 <= len(name) <= 4:
        cands = [x for c, x in keys.items() if "".join(w[0] for w in c.split()) == k.replace(" ", "")]
    if not cands and len(toks) == 1 and len(toks[0]) >= 5:
        cands = [x for c, x in keys.items() if len(c.split()) <= 2 and min(len(c.split()[0]), len(toks[0])) >= 5
                 and (c.split()[0].startswith(toks[0]) or toks[0].startswith(c.split()[0]))]
    if len({idx[x] for x in cands}) == 1:
        return idx[cands[0]]
    hit = difflib.get_close_matches(k, list(keys), n=1, cutoff=0.88)
    return idx[keys[hit[0]]] if hit else None


def refill_points(have: dict, idx: dict) -> None:
    """이미 받은 줄 중 점수가 빈 나라를 다시 맞춘다(이름 규칙을 고친 뒤·랭킹에 새로 들어온 나라)."""
    for se, t in have.items():
        if t.empty or "opp_points" not in t.columns:
            continue
        n = 0
        for col, ncol in (("opp_points", "opponent"), ("nation_points", "nation")):
            miss = t[col].isna() & t["fotmob_id"].notna()
            for i in t.index[miss]:
                hit = nation_of(str(t.at[i, ncol] or ""), idx)
                if hit:
                    t.at[i, col] = hit[1]
                    n += 1
        if n:
            t.to_csv(data_path(TABLE, "EPL", se), index=False)
            print(f"[intl-ratings] {se}: 빈 점수 {n}칸 다시 채움")


def our_players() -> dict[str, tuple[str, str, str]]:
    """{FotMob 선수 id: (리그, 우리 팀 표기, 이름)} — 이번 시즌 명단이 먼저(지금 소속), 없으면 평점 표."""
    out: dict[str, tuple[str, str, str]] = {}
    seasons = [f"{SEASON_START}_{SEASON_START + 1}", f"{SEASON_START - 1}_{SEASON_START}"]
    for table in ("fotmob_squads", "fotmob_ratings", "fotmob_match_ratings"):
        for se in seasons:
            for lg in LEAGUES:
                p = data_path(table, lg, se)
                if not p.exists():
                    continue
                try:
                    t = pd.read_csv(p, usecols=lambda c: c in ("fotmob_id", "squad", "player"))
                except (ValueError, OSError):
                    continue
                for f, sq, pl in zip(t["fotmob_id"], t["squad"], t["player"]):
                    try:
                        k = str(int(float(f)))
                    except (TypeError, ValueError):
                        continue
                    out.setdefault(k, (lg, str(sq), str(pl)))
    return out


def comps(cutoff: str, idx: dict) -> list[tuple[int, str, list[dict]]]:
    """[(대회 id, 이름, cutoff 이후 끝난 경기)] — 남자 A대표팀 대회만."""
    d = _get("https://www.fotmob.com/api/data/allLeagues") or {}
    cands = [(int(l["id"]), str(l.get("name") or "")) for g in (d.get("international") or [])
             for l in (g.get("leagues") or []) if l.get("id") and senior_name(str(l.get("name") or ""))]
    out = []
    for fid, name in cands:
        j = _get(f"https://www.fotmob.com/api/data/leagues?id={fid}") or {}
        ms = (j.get("fixtures") or {}).get("allMatches") or []
        teams = {str((m.get(s) or {}).get("name") or "") for m in ms for s in ("home", "away")} - {""}
        if not teams or sum(nation_of(t, idx) is not None for t in teams) / len(teams) < NATION_SHARE:
            continue
        seasons = [str(s) for s in (j.get("allAvailableSeasons") or [])]
        sel = str((j.get("details") or {}).get("selectedSeason") or (seasons[0] if seasons else ""))
        prev = _prev_label(sel)
        got = [m for m in finished(fid, since=cutoff)]
        if prev and int(re.findall(r"\d{4}", prev)[-1]) >= int(cutoff[:4]):
            got += finished(fid, season=prev, since=cutoff)
        seen, uniq = set(), []
        for m in got:
            if m["id"] not in seen:
                seen.add(m["id"])
                uniq.append(m)
        print(f"[intl-ratings] {fid} {name}: 끝난 경기 {len(uniq)}")
        out.append((fid, name, uniq))
        time.sleep(0.3)
    return out


def _prev_label(label: str) -> str | None:
    ys = re.findall(r"\d{4}", label)
    if len(ys) == 2:
        return f"{int(ys[0]) - 1}/{int(ys[1]) - 1}"
    if len(ys) == 1:
        return str(int(ys[0]) - 1)
    return None


def match_rows(j: dict, match: dict, fid: int, comp: str, ours: dict, idx: dict) -> list[dict]:
    ps = ((j.get("content") or {}).get("playerStats")) or {}
    home, away = match.get("home") or {}, match.get("away") or {}
    names = {str(home.get("id")): str(home.get("name") or ""), str(away.get("id")): str(away.get("name") or "")}
    date = str((match.get("status") or {}).get("utcTime") or "")[:10]
    base = {"match_id": str(match["id"]), "date": date, "comp_id": fid, "comp": comp,
            "friendly": int("friendl" in comp.lower())}
    rows = []
    for pid, p in ps.items():
        k = str(p.get("id") or pid)
        if k not in ours:
            continue
        s = _stats(p)
        mn = (s.get("Minutes played") or (None,))[0]
        if not mn:
            continue
        tid = str(p.get("teamId") or "")
        other = next((n for t, n in names.items() if t != tid), "")
        lg, club, nm = ours[k]
        own, opp = nation_of(names.get(tid, ""), idx), nation_of(other, idx)
        rows.append({**base, "nation": names.get(tid, ""), "opponent": other, "nation_points": own[1] if own else None,
                     "opp_points": opp[1] if opp else None, "fotmob_id": k, "player": p.get("name") or nm,
                     "club": club, "league": lg, "minutes": mn, "rating": (s.get("FotMob rating") or (None,))[0],
                     "goals": (s.get("Goals") or (0,))[0] or 0, "assists": (s.get("Assists") or (0,))[0] or 0})
    if not rows:                                    # 받았다는 표시 — 우리 선수가 없는 경기
        rows.append({**base, "nation": names.get(str(home.get("id")), ""), "opponent": names.get(str(away.get("id")), "")})
    return rows


def load(season: str) -> pd.DataFrame:
    p = data_path(TABLE, "EPL", season)
    return pd.read_csv(p, dtype={"match_id": str, "fotmob_id": str}) if p.exists() else pd.DataFrame(columns=COLS)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=600, help="한 번에 받을 경기 상한(처음엔 여러 번에 나눠 채운다)")
    a = ap.parse_args()
    cutoff = f"{SEASON_START - 1}-{SEASON_EDGE}"
    seasons = [f"{SEASON_START - 1}_{SEASON_START}", f"{SEASON_START}_{SEASON_START + 1}"]
    have = {s: load(s) for s in seasons}
    done = {str(m) for t in have.values() for m in t["match_id"]}
    idx = nation_index()
    refill_points(have, idx)
    ours = our_players()
    todo = [(fid, name, m) for fid, name, ms in comps(cutoff, idx) for m in ms if str(m["id"]) not in done]
    todo.sort(key=lambda x: str((x[2].get("status") or {}).get("utcTime") or ""), reverse=True)   # 최근 경기 먼저
    print(f"[intl-ratings] 새 경기 {len(todo)} (이번에 {min(len(todo), a.max)}) · 우리 선수 id {len(ours)}")
    new: list[dict] = []
    for i, (fid, name, m) in enumerate(todo[: a.max]):
        j = _get(f"https://www.fotmob.com/api/data/matchDetails?matchId={m['id']}")
        if not j:
            continue                                # 실패 — 표시를 안 남겨 다음에 다시
        new += match_rows(j, m, fid, name, ours, idx)
        time.sleep(0.4)
        if (i + 1) % 200 == 0:                      # 중간 저장 — 처음 채울 때 수천 경기라 끊겨도 받은 만큼은 남게
            save(new, have)
            new = []
    save(new, have)
    return 0


def save(new: list[dict], have: dict) -> None:
    if not new:
        return
    idx = nation_index()
    nd = pd.DataFrame(new, columns=COLS)
    nd["season"] = nd["date"].map(season_of)
    for se, g in nd.groupby("season"):
        if se not in have:
            continue
        out = pd.concat([have[se], g[COLS]], ignore_index=True).drop_duplicates(["match_id", "fotmob_id"], keep="last")
        have[se] = out.sort_values(["date", "match_id"])
        have[se].to_csv(data_path(TABLE, "EPL", se), index=False)
        print(f"[intl-ratings] {se}: +{len(g)} 줄 → {len(have[se])} (선수 줄 {have[se]['fotmob_id'].notna().sum()})", flush=True)
    unmatched = sorted({n for n in set(nd["nation"]) | set(nd["opponent"]) if n and nation_of(n, idx) is None})
    if unmatched:
        print(f"[intl-ratings] FIFA 랭킹에 없는 나라 이름 {len(unmatched)}: {', '.join(unmatched[:20])}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
