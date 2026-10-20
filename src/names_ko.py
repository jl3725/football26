"""
한글 이름 사전 — 클럽·선수의 한국어 위키백과 제목(영문 위키 언어 링크) → data/names_ko.csv.

Ask Scout 무료 모드(규칙 기반 라우터, src/scout_router.py)가 '사카 최근 뉴스', '아스날 다음 경기' 같은 한글 질문에서
팀·선수를 찾는 데 쓴다. 손으로 쓰지 않고 위키 언어 링크로 모은다(동음이의 문서는 건너뜀). 표기 차이(아스날↔아스널)는
라우터가 자모 단위 유사도로 흡수한다.

    python src/names_ko.py            # 8개 리그 클럽 + 출전 선수(약 3천 명, 50개씩 묶음 요청)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_wiki_squads as wiki  # noqa: E402
from leagues import LEAGUES, data_path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "names_ko.csv"
BATCH = 50


def langlinks_ko(titles: list[str]) -> dict[str, str]:
    """{요청 제목: 한국어 제목} — 동음이의 문서·한국어 링크 없는 문서는 빠진다."""
    out: dict[str, str] = {}
    for i in range(0, len(titles), BATCH):
        chunk = titles[i:i + BATCH]
        j = wiki._get({"action": "query", "prop": "langlinks|pageprops", "lllang": "ko", "lllimit": 500,
                       "ppprop": "disambiguation", "redirects": 1, "titles": "|".join(chunk)})
        q = j.get("query", {})
        back = {t: t for t in chunk}
        for m in q.get("normalized", []) + q.get("redirects", []):
            for k, v in list(back.items()):
                if v == m["from"]:
                    back[k] = m["to"]
        ko = {pg["title"]: pg["langlinks"][0]["title"] for pg in q.get("pages", [])
              if pg.get("langlinks") and "disambiguation" not in (pg.get("pageprops") or {})}
        for req, final in back.items():
            if final in ko:
                out[req] = ko[final]
        time.sleep(1.0)
    return out


KO_API = "https://ko.wikipedia.org/w/api.php"


def ko_redirects(titles: list[str]) -> dict[str, list[str]]:
    """{한국어 제목: [그 문서로 넘겨주는 다른 표기]} — '아스날 FC'·'맨시티'·'클럽 브뤼헤' 같은 흔한 표기를
    손으로 적지 않고 위키 넘겨주기에서 모은다(Ask Scout 애칭 사전, 2026-10-20)."""
    import requests  # noqa: PLC0415
    out: dict[str, list[str]] = {}
    for i in range(0, len(titles), 20):                # 넘겨주기 수 한도(500)가 묶음 전체에 걸려 작게 나눈다
        chunk = titles[i:i + 20]
        params = {"action": "query", "prop": "redirects", "rdlimit": "max", "rdprop": "title",
                  "titles": "|".join(chunk), "format": "json", "formatversion": 2}
        while True:
            for _ in range(4):
                r = requests.get(KO_API, params=params, headers=wiki.HEADERS, timeout=60)
                if r.status_code != 429:
                    break
                time.sleep(min(60, int(r.headers.get("retry-after") or 10) + 2))
            r.raise_for_status()
            j = r.json()
            for pg in j.get("query", {}).get("pages", []):
                out.setdefault(pg["title"], []).extend(x["title"] for x in pg.get("redirects", []))
            if "continue" not in j:
                break
            params = {**params, **j["continue"]}
        time.sleep(1.0)
    return out


NICK_PROMPT = """다음은 유럽 축구 클럽(영문 이름 → 한국어 위키 제목) 목록이다. 한국 축구 팬이 흔히 부르는 한글 애칭·줄임말을
JSON 으로만 답하라: {{"영문 이름": ["애칭", ...]}}.
- 실제로 널리 쓰는 것만(예: Tottenham Hotspur → 스퍼스, 토트넘). 확실하지 않으면 빈 목록.
- 한글만, 2~8자. 위키 제목과 같은 말은 빼라. 다른 클럽도 그렇게 부를 수 있는 말(예: '시티', '유나이티드')은 빼라.
목록:
{clubs}"""


def fan_nicknames(rows: list[dict], club_league: dict) -> list[dict]:
    """한국 팬 애칭(kind=club_nick) — 위키 넘겨주기에 없는 '스퍼스' 같은 말을 Gemini 무료 등급에 묻는다(src/llm.py).
    다른 클럽의 이름·별칭과 겹치거나 두 클럽에 나온 말은 버린다. 키가 없으면 빈 목록(라우터는 위키 별칭만 쓴다)."""
    import re  # noqa: PLC0415
    try:
        import llm  # noqa: PLC0415
    except ImportError:
        return []
    if not llm.available():
        return []
    ko_title = {r["name"]: r["ko"] for r in rows if r["kind"] == "club"}
    taken: dict[str, set] = {}                          # 다른 클럽 이름·별칭(FC 등을 뗀 형태까지) — '파리'는 Paris FC 이름
    for r in rows:
        if r["kind"] in ("club", "club_alias"):
            raw = re.sub(r"\s+", " ", str(r["ko"])).strip()
            for k in {raw, re.sub(r"\b(FC|F\.C\.?|AFC|CF|SC|KV|AC|SSC|AS|RC|FK|CD|UD|SD)(?=\s|$)", "", raw).strip()}:
                taken.setdefault(k, set()).add(r["name"])
    llm.start("names_ko", 12)
    got: dict[str, list] = {}
    names = sorted(ko_title)
    try:
        for i in range(0, len(names), 40):
            part = {n: ko_title[n] for n in names[i:i + 40]}
            res = llm.generate_json(NICK_PROMPT.format(clubs=json.dumps(part, ensure_ascii=False)))
            if isinstance(res, dict):
                for n, v in res.items():
                    if n in part and isinstance(v, list):
                        got[n] = [str(x).strip() for x in v if isinstance(x, str)]
    finally:
        llm.finish()
    count: dict[str, set] = {}
    for n, vs in got.items():
        for v in vs:
            if re.fullmatch(r"[가-힣 ]{2,8}", v):
                count.setdefault(v, set()).add(n)
    out = []
    for v, ns in count.items():
        n = next(iter(ns))
        if len(ns) == 1 and not (taken.get(v, set()) - {n}) and v != ko_title.get(n):
            out.append({"kind": "club_nick", "league": club_league[n], "name": n, "ko": v})
    print(f"[names-ko] 팬 애칭(Gemini) {len(out)}개")
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = []
    titles = json.loads((ROOT / "data" / "wiki_titles.json").read_text(encoding="utf-8"))
    club_league = {}
    for lg in LEAGUES:
        st = data_path("standings", lg)
        if st.exists():
            for s in pd.read_csv(st)["squad"].astype(str):
                club_league[s] = lg
    clubs = {c: t for c, t in titles.items() if c in club_league}
    for lg in LEAGUES:                                    # 위키 스쿼드 표의 문서 제목(전 클럽) — wiki_titles.json 은 일부만
        p = data_path("wiki_squads", lg)
        if p.exists():
            d = pd.read_csv(p, usecols=["squad", "wiki_title"]).dropna().drop_duplicates("squad")
            for sq, t in zip(d["squad"].astype(str), d["wiki_title"].astype(str)):
                if sq in club_league:
                    clubs.setdefault(sq, t)
    ck = langlinks_ko(list(clubs.values()))
    for c, t in clubs.items():
        if t in ck:
            rows.append({"kind": "club", "league": club_league[c], "name": c, "ko": ck[t]})
    # 클럽 별칭 — 한국어 문서로 넘겨주는 표기 전부(kind=club_alias). 라우터·검색이 그대로 쓴다
    ko_of = {ck[t]: c for c, t in clubs.items() if t in ck}
    for ko_title, alts in ko_redirects(list(ko_of)).items():
        c = ko_of.get(ko_title)
        if not c:
            continue
        for a in dict.fromkeys(alts):
            rows.append({"kind": "club_alias", "league": club_league[c], "name": c, "ko": a})
    players = []
    for lg in LEAGUES:
        p = data_path("players_full", lg)
        if p.exists():
            d = pd.read_csv(p, usecols=["player", "squad", "minutes"])
            for r in d[d["minutes"].fillna(0) > 0].itertuples():
                players.append((lg, str(r.squad), str(r.player)))
    names = sorted({pl for _, _, pl in players})
    pk = langlinks_ko(names)
    for lg, sq, pl in players:
        if pl in pk:
            rows.append({"kind": "player", "league": lg, "name": pl, "squad": sq, "ko": pk[pl]})
    if len(rows) < 100:
        print(f"[names-ko] {len(rows)}건 — 너무 적어 기존 파일 유지")
        return 1
    nick = fan_nicknames(rows, club_league)
    if not nick and OUT.exists():                       # 키가 없거나 실패하면 지난 애칭을 그대로(매주 지워지지 않게)
        old = pd.read_csv(OUT, dtype=str).fillna("")
        nick = old[old["kind"] == "club_nick"].to_dict("records")
    rows += nick
    df = pd.DataFrame(rows)
    multi = df["kind"].isin(["club_alias", "club_nick"])                              # 별칭·애칭은 클럽당 여러 개
    alias = df[multi].drop_duplicates(["kind", "league", "name", "ko"])
    pd.concat([df[~multi].drop_duplicates(["kind", "league", "name"]), alias]).to_csv(
        OUT, index=False, encoding="utf-8")
    print(f"[names-ko] 클럽 {sum(r['kind'] == 'club' for r in rows)} · 별칭 {len(alias)} · "
          f"선수 {sum(r['kind'] == 'player' for r in rows)}/{len(players)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
