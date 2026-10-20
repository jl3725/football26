"""
뉴스 선수 태깅 — 기사(영어 원문 제목+요약)에 나온 우리 8개 리그 선수를 찾아 news.db article_players 에 남긴다
(설계도 3단계 '뉴스 선수·팀 태깅'. 팀 태그는 수집 때 이미 있다 — 피드 단위라 리그 전체 기사도 섞여 있다).

규칙(정확도 우선 — 무료·결정적, LLM 없음):
  full     이름 전체가 나오면 태그(예: 'Bukayo Saka')
  surname  성만 나오면(4글자 이상) 그 선수의 클럽 이름(또는 ESPN 표기 별칭)이 같은 기사에 함께 나올 때만
           — 'Rice' 같은 흔한 단어·같은 성의 다른 선수를 막는다. 막는 경우:
           · 같은 클럽에 같은 성이 둘(윌리엄스 형제) · 그 클럽 감독과 같은 성(시메오네 감독 → 줄리아노 시메오네 아님)
           · 성 앞 단어가 다른 사람의 이름(Diego Simeone·Manolo González — 선수·감독 이름 첫 단어 목록)
           클럽 별칭 한 단어는 그 단어를 가진 클럽이 하나뿐일 때만('madrid' 는 레알·아틀레티코 둘이라 제외).

    python src/news_tags.py            # 아직 태깅 안 한 기사만(수집 직후 fetch_news_daily 가 부름)
    python src/news_tags.py --all      # 전부 다시
"""
from __future__ import annotations

import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from unidecode import unidecode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espn_common import LEAGUE_DISPLAY  # noqa: E402
from leagues import LEAGUES, data_path  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "news.db"
_WORD = re.compile(r"[a-z0-9]+")
_GENERIC = {"united", "city", "real", "club", "athletic", "sporting", "football", "fc", "afc", "cf", "sc", "ac", "as",
            "de", "la", "le", "the", "town", "county", "albion", "rovers", "wanderers", "hotspur", "olympique", "racing",
            "stade", "borussia", "vfb", "vfl", "tsg", "rb", "1", "04", "05", "inter", "sport", "royal", "union"}


def toks(s: str) -> list[str]:
    return _WORD.findall(unidecode(str(s or "")).lower())


class Index:
    """선수 이름·성·클럽 별칭 색인."""

    def __init__(self, players: pd.DataFrame, managers: dict[str, str] | None = None):
        self.full: dict[str, list[tuple[tuple[str, ...], tuple]]] = defaultdict(list)    # 첫 토큰 → [(이름 토큰, 선수)]
        self.surname: dict[str, list[tuple]] = defaultdict(list)                          # 성 → [선수]
        self.club_alias: dict[str, list[tuple[str, ...]]] = {}                            # 클럽 → [별칭 토큰열]
        self.first_names: set[str] = set()                                                # 사람 이름 첫 단어
        self.mgr_surname = {sq: toks(m)[-1] for sq, m in (managers or {}).items() if toks(m)}
        self.first_names |= {toks(m)[0] for m in (managers or {}).values() if len(toks(m)) >= 2}
        rows = players[["league", "squad", "player"]].drop_duplicates()
        word_clubs: dict[str, set[str]] = defaultdict(set)
        for sq in rows["squad"].astype(str).unique():
            for w in toks(sq):
                word_clubs[w].add(sq)
        for lg, sq, pl in rows.itertuples(index=False):
            t = tuple(toks(pl))
            if not t:
                continue
            who = (str(pl), str(sq), str(lg))
            if len(t) >= 2:
                self.full[t[0]].append((t, who))
                if len(t[0]) >= 3:
                    self.first_names.add(t[0])
            if len(t[-1]) >= 4:
                self.surname[t[-1]].append(who)
            if sq not in self.club_alias:
                al = {tuple(toks(sq))} | {tuple(toks(k)) for k, v in LEAGUE_DISPLAY.get(lg, {}).items() if v == sq}
                # 클럽 이름 속 특징 단어(5글자+, 일반어 제외, 그 단어를 가진 클럽이 하나뿐) — 'Tottenham Hotspur' → 'tottenham'
                al |= {(w,) for w in toks(sq) if len(w) >= 5 and w not in _GENERIC and len(word_clubs[w]) == 1}
                self.club_alias[sq] = [a for a in al if a and (len(a) > 1 or len(word_clubs.get(a[0], ())) <= 1)]

    @staticmethod
    def _has(words: list[str], seq: tuple[str, ...]) -> bool:
        n = len(seq)
        return any(tuple(words[i:i + n]) == seq for i in range(len(words) - n + 1))

    def tag(self, text: str) -> list[tuple[str, str, str, str]]:
        """[(선수, 클럽, 리그, how)]."""
        words = toks(text)
        out: dict[tuple, str] = {}
        covered: set[int] = set()                                 # 이름 전체로 잡힌 자리 — 'Pedro Neto' 의 Pedro 는 주앙 페드루가 아니다
        for i, w in enumerate(words):
            for seq, who in self.full.get(w, ()):
                if tuple(words[i:i + len(seq)]) == seq:
                    out[who] = "full"
                    covered.update(range(i, i + len(seq)))
        for w in set(words):
            holders = self.surname.get(w, ())
            if not holders:
                continue
            by_club: dict[str, list[tuple]] = defaultdict(list)
            for c in holders:                                     # 이미 이름 전체로 잡힌 선수도 '같은 성' 수에 넣는다
                by_club[c[1]].append(c)
            for sq, cs in by_club.items():
                c = cs[0]
                if len(cs) > 1 or c in out or self.mgr_surname.get(sq) == w:
                    continue
                first = toks(c[0])[0]
                # 성 앞 단어가 다른 사람 이름이면(Diego Simeone) 그 자리는 다른 사람 — 깨끗한 자리가 하나라도 있어야
                clean = any(x == w and i not in covered
                            and (i == 0 or words[i - 1] == first or words[i - 1] not in self.first_names)
                            for i, x in enumerate(words))
                if clean and any(self._has(words, a) for a in self.club_alias.get(sq, [])):
                    out[c] = "surname"
        return [(p, s, lg, how) for (p, s, lg), how in out.items()]


def load_players() -> pd.DataFrame:
    frames = []
    for lg in LEAGUES:
        p = data_path("players_full", lg)
        if p.exists():
            d = pd.read_csv(p, usecols=["player", "squad"])
            d["league"] = lg
            frames.append(d)
    return pd.concat(frames) if frames else pd.DataFrame(columns=["player", "squad", "league"])


def load_managers() -> dict[str, str]:
    import json
    out: dict[str, str] = {}
    for lg in LEAGUES:
        p = data_path("manager_profiles", lg, ext="json")
        if p.exists():
            for sq, v in json.loads(p.read_text(encoding="utf-8")).items():
                name = v.get("name") if isinstance(v, dict) else v
                if name:
                    out[str(sq)] = str(name)
    return out


def init(c: sqlite3.Connection) -> None:
    c.execute("""CREATE TABLE IF NOT EXISTS article_players (
                   link TEXT NOT NULL, player TEXT NOT NULL, squad TEXT, league TEXT, how TEXT, tagged_at TEXT,
                   PRIMARY KEY (link, player, squad))""")
    c.execute("CREATE TABLE IF NOT EXISTS article_tagged (link TEXT PRIMARY KEY, tagged_at TEXT)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ap_player ON article_players(player, squad)")


def run(all_: bool = False, db: Path = DB_PATH) -> tuple[int, int]:
    idx = Index(load_players(), load_managers())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(db) as c:
        init(c)
        if all_:
            c.execute("DELETE FROM article_players")
            c.execute("DELETE FROM article_tagged")
        rows = c.execute("""SELECT link, MAX(headline), MAX(descr) FROM articles
                            WHERE link NOT IN (SELECT link FROM article_tagged) GROUP BY link""").fetchall()
        n_tags = 0
        for link, head, descr in rows:
            for p, s, lg, how in idx.tag(f"{head or ''}. {descr or ''}"):
                c.execute("INSERT OR REPLACE INTO article_players VALUES (?,?,?,?,?,?)", (link, p, s, lg, how, now))
                n_tags += 1
            c.execute("INSERT OR REPLACE INTO article_tagged VALUES (?,?)", (link, now))
    return len(rows), n_tags


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    n, t = run(all_="--all" in args)
    print(f"[news-tags] 기사 {n}건 태깅 · 선수 태그 {t}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
