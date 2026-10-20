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
    pd.DataFrame(rows).drop_duplicates(["kind", "league", "name"]).to_csv(OUT, index=False, encoding="utf-8")
    print(f"[names-ko] 클럽 {sum(r['kind'] == 'club' for r in rows)} · 선수 {sum(r['kind'] == 'player' for r in rows)}"
          f"/{len(players)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
