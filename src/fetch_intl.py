"""
INTERNATIONAL 에이전트 — A매치 일정·기간(ESPN) + 대표팀 소집 명단(위키 'Current squad')을 우리 8개 리그 선수와 잇는다
(설계도 2단계 'A매치 일정·소집 명단').

  1. ESPN 국가대표 대회(네이션스리그·친선·CONCACAF 네이션스리그·각 대륙 예선·대륙 대회)의 경기 → data/intl_matches.csv
  2. 경기가 몰린 날짜 묶음 = A매치 기간 → data/intl_windows.json. 그 기간 우리 리그 경기가 거의 없으면 'break'(휴식기),
     리그가 계속되면 'tournament'(아시안컵·네이션스컵 — 소집 선수가 클럽 경기를 빠진다 → 예측 결장 반영)
  3. 대표팀 위키 문서의 'Current squad' 표({{nat fs g player|name=…|club=…|caps=…}})를 읽어, 소속 클럽 + 이름으로
     우리 선수와 매칭 → data/intl_callups.csv. 명단 머리글의 날짜(마지막 날짜)를 squad_for 로 남겨 '어느 기간 명단'인지 판단.
     문서 목록은 우리 선수 국적(TM)에서 만든다 — 실제 대표팀이 국적 첫 칸과 달라도 클럽+이름으로 잇기 때문에 상관없다.

위키 요청은 10문서씩 묶음(fetch_wiki_squads.wikitexts — 팀마다 1요청이면 429).

    python src/fetch_intl.py
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_wiki_squads as wiki  # noqa: E402
import player_registry as preg  # noqa: E402
import team_names  # noqa: E402
from espn_common import scoreboard_events  # noqa: E402
from leagues import LEAGUES, data_path  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
OUT_MATCHES = DATA / "intl_matches.csv"
OUT_WINDOWS = DATA / "intl_windows.json"
OUT_CALLUPS = DATA / "intl_callups.csv"

# ESPN 국가대표 대회 코드 — 대회가 없는 해엔 0경기(정상). 대륙(이동 거리)은 FIFA 랭킹 표의 confederation 으로 본다.
INTL_CODES = (
    "uefa.nations", "uefa.euroq", "fifa.worldq.uefa", "uefa.euro", "fifa.friendly", "fifa.world",
    "concacaf.nations.league", "concacaf.gold", "fifa.worldq.concacaf", "fifa.worldq.conmebol", "conmebol.america",
    "caf.nations_qual", "caf.nations", "fifa.worldq.caf", "afc.asian.cup", "afc.cupq", "fifa.worldq.afc",
)
# TM 국적 표기 → 위키 대표팀 문서 앞부분(나머지는 '<국가> national football team' + 위키 넘겨주기)
NATION_TITLE = {
    "Korea, South": "South Korea", "Cote d'Ivoire": "Ivory Coast", "Türkiye": "Turkey",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina", "The Gambia": "Gambia", "Curacao": "Curaçao",
    "Ireland": "Republic of Ireland", "Congo": "Congo",
}
FULL_TITLE = {   # 남자 대표팀 문서 제목이 'national football team' 꼴이 아닌 곳
    "United States": "United States men's national soccer team", "Canada": "Canada men's national soccer team",
    "Australia": "Australia men's national soccer team", "New Zealand": "New Zealand men's national football team",
    "Sweden": "Sweden men's national football team",
}
# TM 국적 표기 → FIFA 랭킹 표기(대륙·순위·국기, data/fifa_ranking.csv). ESPN 국가대표 이름과 맞출 때도 후보로 쓴다
FIFA_NAME = {
    "Bosnia-Herzegovina": "Bosnia and Herzegovina", "Cape Verde": "Cabo Verde", "Cote d'Ivoire": "Côte d'Ivoire",
    "Czech Republic": "Czechia", "DR Congo": "Congo DR", "Iran": "IR Iran", "Ireland": "Republic of Ireland",
    "Korea, South": "Korea Republic", "United States": "USA", "Curacao": "Curaçao",
}
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}


def nation_title(nat: str) -> str:
    return FULL_TITLE.get(nat) or f"{NATION_TITLE.get(nat, nat)} national football team"


def nation_keys(nat: str) -> set[str]:
    """국적 표기 하나의 여러 이름(TM·위키·FIFA) 정규화 — ESPN 국가대표 이름('Ivory Coast'·'Czechia')과 맞춘다."""
    base = FULL_TITLE.get(nat, "").replace(" men's national soccer team", "").replace(" men's national football team", "")
    return {preg.norm(x) for x in (nat, NATION_TITLE.get(nat, ""), FIFA_NAME.get(nat, ""), base) if x}


def fifa_info() -> dict[str, dict]:
    """FIFA 표기 → {conf, rank, flag}."""
    p = DATA / "fifa_ranking.csv"
    if not p.exists():
        return {}
    f = pd.read_csv(p)
    return {str(r.team): {"conf": str(r.confederation), "rank": int(r.rank), "flag": str(r.flag)} for r in f.itertuples()}


# ── 1·2. 경기·기간 ──────────────────────────────────────────────────────────
def fetch_matches(today: dt.date) -> pd.DataFrame:
    start, end = (today - dt.timedelta(days=120)).isoformat(), (today + dt.timedelta(days=240)).isoformat()
    rows = []
    for code in INTL_CODES:
        evs = scoreboard_events(code, start, end)
        if evs is None:
            print(f"[intl] {code} 조회 실패 — 건너뜀")
            continue
        for e in evs:
            c = (e.get("competitions") or [{}])[0]
            side = {t.get("homeAway"): t for t in c.get("competitors", [])}
            h, a = side.get("home", {}), side.get("away", {})
            st = (e.get("status") or {}).get("type") or {}
            rows.append({"event_id": str(e.get("id")), "kickoff": e.get("date"), "date": (e.get("date") or "")[:10],
                         "comp_code": code,
                         "home": (h.get("team") or {}).get("displayName", ""), "away": (a.get("team") or {}).get("displayName", ""),
                         "hg": h.get("score") if st.get("state") != "pre" else None,
                         "ag": a.get("score") if st.get("state") != "pre" else None, "state": st.get("state", "pre")})
    return pd.DataFrame(rows).drop_duplicates("event_id") if rows else pd.DataFrame()


def club_match_days() -> dict[str, int]:
    """날짜 → 우리 8개 리그 리그 경기 수(휴식기 판정)."""
    out: dict[str, int] = {}
    for lg in LEAGUES:
        p = data_path("schedule_full", lg)
        if not p.exists():
            continue
        d = pd.read_csv(p, usecols=["comp_code", "date", "event_id"])
        d = d[~d["comp_code"].astype(str).str.startswith(("uefa.", "eng.fa", "eng.league"))].drop_duplicates("event_id")
        for day, n in d.groupby("date").size().items():
            out[str(day)] = out.get(str(day), 0) + int(n)
    return out


def windows(matches: pd.DataFrame, club_days: dict[str, int], min_day: int = 6, gap: int = 4) -> list[dict]:
    """하루 min_day 경기 이상인 날을 gap 일 이내로 이어 붙인 묶음. 소집은 첫 경기 사흘 전부터라 start 는 그만큼 앞."""
    if matches.empty:
        return []
    per_day = matches.groupby("date").size()
    days = sorted(dt.date.fromisoformat(d) for d, n in per_day.items() if n >= min_day)
    groups: list[list[dt.date]] = []
    for d in days:
        if groups and (d - groups[-1][-1]).days <= gap:
            groups[-1].append(d)
        else:
            groups.append([d])
    out = []
    for g in groups:
        first, last = g[0], g[-1]
        n = int(per_day[(per_day.index >= first.isoformat()) & (per_day.index <= last.isoformat())].sum())
        if n < 20:
            continue
        span = [(first + dt.timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]
        club = sum(club_days.get(x, 0) for x in span)
        comps = sorted(matches[(matches["date"] >= first.isoformat()) & (matches["date"] <= last.isoformat())]["comp_code"].unique())
        kind = "tournament" if club >= 3 * max(1, len(span)) else "break"
        out.append({"start": (first - dt.timedelta(days=3)).isoformat(), "first_match": first.isoformat(),
                    "end": last.isoformat(), "matches": n, "club_matches": club, "kind": kind, "comps": comps,
                    "label": f"{first.month}월 A매치 기간" if kind == "break" else "국가대표 대회(리그 진행 중)"})
    return out


# ── 3. 소집 명단 ────────────────────────────────────────────────────────────
_SEC = re.compile(r"===\s*(?:Current|Latest) squad\s*===(.*?)(?=\n===?\s*[^=\n]|\Z)", re.S | re.I)
_PLAYER = re.compile(r"\{\{\s*nat fs (?:g )?player\s*\|(.*?)\}\}\s*(?=\n|\{\{|$)", re.S | re.I)
# 날짜 — '24 September 2026' · 'September 26 and 29, 2026'. 'October 2026' 의 '20' 을 날로 읽지 않게 앞뒤 숫자 금지
_DATE_DM = re.compile(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")(?:,?\s+(\d{4}))?", re.I)
_DATE_MD = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?!\d)((?:\s*(?:,|and|&)\s*\d{1,2}(?!\d))*)(?:,?\s+(\d{4}))?",
                      re.I)


def squad_for(intro: str, today: dt.date) -> str | None:
    """명단 머리글에서 가장 늦은 날짜 — 연도가 없으면 오늘에서 가장 가까운 해(앞으로 120일까지)."""
    text = re.sub(r"<ref.*?</ref>|<ref[^>]*/>|<!--.*?-->", "", intro, flags=re.S)
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", text)
    found = []
    for m in _DATE_DM.finditer(text):
        found.append((int(m.group(1)), MONTHS[m.group(2).lower()], m.group(3)))
    for m in _DATE_MD.finditer(text):                     # 'October 3 and 6, 2026' → 날 목록 중 마지막
        days = [int(m.group(2))] + [int(x) for x in re.findall(r"\d{1,2}", m.group(3) or "")]
        found.append((max(days), MONTHS[m.group(1).lower()], m.group(4)))
    dates = []
    for day, mon, yr in found:
        years = [int(yr)] if yr else [today.year - 1, today.year, today.year + 1]
        for y in years:
            try:
                d = dt.date(y, mon, day)
            except ValueError:
                continue
            if yr or (today - dt.timedelta(days=300)) <= d <= today + dt.timedelta(days=120):
                dates.append(d)
    return max(dates).isoformat() if dates else None


def parse_current_squad(wikitext: str, today: dt.date) -> tuple[list[dict], str | None]:
    m = _SEC.search(wikitext or "")
    if not m:
        return [], None
    sec = m.group(1)
    first_tpl = sec.find("{{nat fs")
    when = squad_for(sec[: first_tpl if first_tpl > 0 else 1500], today)
    rows = []
    for pm in _PLAYER.finditer(sec):
        f = wiki._fields(pm.group(1))
        name = wiki._link_text(f.get("name", ""))
        if not name:
            continue
        rows.append({"player": name, "club": wiki._link_text(f.get("club", "")), "pos": f.get("pos", "").strip().upper(),
                     "caps": pd.to_numeric(re.sub(r"\D", "", f.get("caps", "")) or None, errors="coerce"),
                     "goals": pd.to_numeric(re.sub(r"\D", "", f.get("goals", "")) or None, errors="coerce")})
    return rows, when


def our_players() -> tuple[pd.DataFrame, dict[str, str]]:
    """우리 선수(출전 있는) 표 + {클럽: 리그}."""
    frames = []
    for lg in LEAGUES:
        p = data_path("players_full", lg)
        if p.exists():
            d = pd.read_csv(p, usecols=["player", "squad", "nationality", "minutes"])
            d["league"] = lg
            frames.append(d)
    al = pd.concat(frames) if frames else pd.DataFrame(columns=["player", "squad", "nationality", "minutes", "league"])
    return al, {str(s): str(lg) for s, lg in zip(al["squad"], al["league"])}


def match_callups(rows: list[dict], al: pd.DataFrame, club_league: dict[str, str]) -> list[dict]:
    squads = list(club_league)
    by_squad = {sq: dict(zip(g["player"].astype(str), g["player"].astype(str))) for sq, g in al.groupby("squad")}
    out = []
    for r in rows:
        sq = team_names.best(r["club"], squads) if r["club"] else None
        if not sq:
            continue
        who, sc = preg.best_match(r["player"], by_squad.get(sq, {}))
        if not who:
            continue
        out.append({**r, "our_player": who, "our_squad": sq, "our_league": club_league[sq], "match_score": sc})
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    today = dt.date.today()
    m = fetch_matches(today)
    if m.empty:
        print("[intl] 국가대표 경기 0건 — ESPN 응답 확인(기존 파일 유지)")
        return 1
    m.sort_values(["date", "kickoff"]).to_csv(OUT_MATCHES, index=False)
    wins = windows(m, club_match_days())
    OUT_WINDOWS.write_text(json.dumps({"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                       "windows": wins}, ensure_ascii=False, indent=1), encoding="utf-8")
    nxt = next((w for w in wins if w["end"] >= today.isoformat()), None)
    print(f"[intl] 경기 {len(m)} · 기간 {len(wins)} · 다음 {nxt['start'] if nxt else '-'}~{nxt['end'] if nxt else '-'}")

    al, club_league = our_players()
    nations = sorted(al.loc[al["minutes"].fillna(0) > 0, "nationality"].dropna().astype(str).unique())
    texts = wiki.wikitexts([nation_title(n) for n in nations])
    fifa = fifa_info()
    rows_out, no_section = [], []
    for nat in nations:
        rows, when = parse_current_squad(texts.get(nation_title(nat), ""), today)
        if not rows:
            no_section.append(nat)
            continue
        fi = fifa.get(FIFA_NAME.get(nat, nat), {})
        for r in match_callups(rows, al, club_league):
            rows_out.append({"nation": nat, "nation_conf": fi.get("conf", ""), "fifa_rank": fi.get("rank"),
                             "flag": fi.get("flag", ""), "squad_for": when, **r})
    if not rows_out:
        print("[intl] 매칭된 소집 선수 0명 — 위키 응답 확인(기존 파일 유지)")
        return 1
    out = pd.DataFrame(rows_out).drop_duplicates(["our_squad", "our_player"])
    out.to_csv(OUT_CALLUPS, index=False)
    print(f"[intl] 대표팀 {len(nations) - len(no_section)}/{len(nations)}개 문서 · 우리 선수 소집 {len(out)}명"
          + (f" · Current squad 없음: {', '.join(no_section[:12])}" if no_section else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
