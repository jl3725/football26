"""
뉴스 2단계 — 매체·기자 신뢰도: 이적 루머 기사가 실제 이적으로 이어졌는지(TM 이적 기록)로 적중률을 학습.

루머 한 건(claim) = 이적 기사(news_classify kind=transfer)에 나온 선수(article_players, 이름 전체 태그) +
  제목에 나온 '행선지' 클럽(그 선수의 원래 클럽이 아닌 클럽 — 우리 8개 리그 클럽과 이적 기록에 나온 상대 클럽 이름).
목표 이적시장 = 기사 날짜로(6/1~9/1 → 그해 여름, 9/2~2/3 → 다음 겨울, 2/4~5/31 → 그해 여름).
판정 = 그 시장이 닫히고 7일 뒤(season_context 의 여름 9/1·겨울 2/3):
  hit   그 시장에 그 선수가 그 클럽으로 옮겼다(TM transfers: squad=행선지 in, 또는 out 의 상대 클럽=행선지)
  miss  안 옮겼다(다른 곳으로 갔거나 남음). 단계가 denied(부인)면 반대로 — 안 옮겼으면 적중
  열린 시장의 루머는 pending.
매체·기자마다 적중률(베타 사전분포로 표본이 적으면 전체 평균 쪽으로) → data/news_reliability.csv,
루머 판정 목록 → data/news_claims.csv. 화면(뉴스 탭)은 매체 칩·STORY 에 '적중 n/m' 을 붙인다.

    python src/news_reliability.py
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
from unidecode import unidecode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import LEAGUES, data_path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NEWS_DB = ROOT / "data" / "news.db"
OUT_REL = ROOT / "data" / "news_reliability.csv"
OUT_CLAIMS = ROOT / "data" / "news_claims.csv"
GRACE_DAYS = 7
PRIOR = 4.0          # 베타 사전분포 세기(가상 표본 수) — 판정 4건짜리 매체가 100% 로 1등이 되지 않게
MIN_N = 3            # 이보다 적게 판정된 매체·기자는 표에 'few' 로
STAGES = {"interest", "talks", "agreed", "done", "denied"}
# 경기 리포트·평점 기사 — 분류기가 이적 기사로 잘못 본 것(ESPN /report/_/gameId · Guardian /match-report).
# 예: "Madueke sinks Nottingham Forest with Arsenal's only shot" 이 Madueke → Forest 관심으로 잡혔다(2026-10-21)
MATCH_REPORT = re.compile(r"match-?report|/report/|player-ratings|/live/|/match/", re.I)
ROUNDUP = re.compile(r"round-?up|gossip|rumou?rs?\s*[:,]|transfer news|live\b|latest\b|\bas it happened|recap", re.I)


def _fold(s) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", unidecode(str(s or "")).lower()).split())


def target_window(day: dt.date) -> tuple[int, str, dt.date]:
    """기사 날짜 → (season_id, 'summer'|'winter', 시장 마감일)."""
    y = day.year
    if (day.month, day.day) >= (6, 1) and (day.month, day.day) <= (9, 1):
        return y, "summer", dt.date(y, 9, 1)
    if (day.month, day.day) > (9, 1):
        return y, "winter", dt.date(y + 1, 2, 3)
    if (day.month, day.day) <= (2, 3):
        return y - 1, "winter", dt.date(y, 2, 3)
    return y, "summer", dt.date(y, 9, 1)


def load_transfers() -> pd.DataFrame:
    frames = []
    for lg in LEAGUES:
        p = data_path("transfers", lg)
        if p.exists():
            d = pd.read_csv(p, usecols=lambda c: c in {"squad", "season_id", "window", "direction", "player", "norm_key", "club"})
            d["league"] = lg
            frames.append(d)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


class ClubIndex:
    """제목에서 클럽 찾기 — 클럽마다 이름 낱말열, 여러 클럽이 나눠 가진 말('manchester', 'real')은 안 쓴다."""

    STOP = {"fc", "cf", "sc", "ac", "afc", "cd", "ud", "sd", "rc", "as", "ss", "us", "sv", "vfb", "vfl", "fk", "sk", "kv",
            "club", "de", "la", "le", "the", "united", "city", "real", "sporting", "athletic", "atletico", "inter", "royal",
            "u21", "u23", "u19", "b", "ii"}

    def __init__(self, names_by_club: dict[str, set[str]], ours: set[str] | None = None):
        """ours = 우리 8개 리그 클럽 — 구별되는 한 낱말('Brugge')로도 찾는다. 그 밖(이적 기록의 상대 클럽)은 이름 전체만
        ('Defensa y Justicia' 의 'Defensa' 가 '수비진'으로 읽히지 않게)."""
        term_clubs: dict[str, set[str]] = defaultdict(set)
        for club, names in names_by_club.items():
            for n in names:
                f = _fold(n)
                if not f:
                    continue
                term_clubs[f].add(club)
                ws = [w for w in f.split() if w not in self.STOP and len(w) >= 4]
                if len(ws) == 1 and (ours is None or club in ours):
                    term_clubs[ws[0]].add(club)
        self.terms = {t: next(iter(cs)) for t, cs in term_clubs.items() if len(cs) == 1}
        self.by_len = sorted(self.terms, key=len, reverse=True)

    # 출신을 나타내는 앞말 — 'from Real Madrid', 'del Betis', 'van Ajax' 뒤 클럽은 행선지가 아니다
    ORIGIN_BEFORE = {"from", "de", "del", "dal", "dalla", "van", "von", "vom", "du", "do", "da", "ex", "of"}

    def find(self, text: str, drop_names=()) -> list[str]:
        """제목에 나온 클럽(나온 순서). drop_names(선수 이름)는 먼저 지운다 — 'Andrey Santos' 의 Santos 가 클럽이 되지 않게.
        출신 앞말 바로 뒤 클럽은 'from:' 을 붙여 돌려준다."""
        f = f" {_fold(text)} "
        orig = unidecode(str(text or ""))
        for n in sorted((_fold(x) for x in drop_names if x), key=len, reverse=True):
            if n:
                f = f.replace(f" {n} ", " # ")
        hits: list[tuple[int, str]] = []
        for t in self.by_len:
            i = f.find(f" {t} ")
            while i >= 0:
                c = self.terms[t]
                before = f[:i].split()[-1:] or [""]
                # 한 낱말 이름은 원문에서 대문자로 시작할 때만 — 스페인어 'como'(~로서)가 Como 가 되지 않게
                if " " in t or re.search(rf"\b({re.escape(t.capitalize())}|{re.escape(t.upper())})\b", orig):
                    hits.append((i, ("from:" if before[0] in self.ORIGIN_BEFORE else "") + c))
                f = f[:i] + " " + "|" * len(t) + " " + f[i + len(t) + 2:]   # 같은 길이로 가려 위치 유지
                i = f.find(f" {t} ")
        out: list[str] = []
        for _, c in sorted(hits):
            if c not in out:
                out.append(c)
        return out


def club_names(tr: pd.DataFrame) -> tuple[dict[str, set[str]], set[str]]:
    """(클럽 → 이름들, 우리 클럽). 우리 8개 리그 클럽(정식 이름·현지 표기) + 이적 기록의 상대 클럽(TM 표기)."""
    import news_sources  # noqa: PLC0415
    import teammeta as tm  # noqa: PLC0415
    out: dict[str, set[str]] = defaultdict(set)
    for lg in LEAGUES:
        p = data_path("standings", lg)
        if p.exists():
            for sq in pd.read_csv(p)["squad"].astype(str):
                out[sq] |= {sq, tm.team_fullname(sq), *news_sources.cached_local_names(sq)}
    ours = set(out)
    for c in tr.get("club", pd.Series(dtype=str)).dropna().astype(str).unique():
        if not re.search(r"\b(u\d{2}|ii|b|youth|reserves?|without club|retired|career break|unknown)\b", c.lower()):
            out[c].add(c)
    return out, ours


def _same_club(a: str, b: str) -> bool:
    fa, fb = _fold(a), _fold(b)
    return bool(fa) and (fa == fb or fa in fb or fb in fa)


def claims(today: dt.date | None = None) -> pd.DataFrame:
    today = today or dt.date.today()
    tr = load_transfers()
    if tr.empty or not NEWS_DB.exists():
        return pd.DataFrame()
    idx = ClubIndex(*club_names(tr))
    con = sqlite3.connect(NEWS_DB)
    try:
        arts = pd.read_sql(
            """SELECT a.link, max(a.headline) AS headline, max(a.source) AS source, max(a.published) AS published,
                      max(a.first_seen) AS first_seen, m.stage, m.journalists
               FROM articles a JOIN article_meta m ON m.link = a.link
               WHERE m.kind = 'transfer' GROUP BY a.link""", con)
        tags = pd.read_sql("SELECT link, player, squad, how FROM article_players", con)
    finally:
        con.close()
    names_by_link = tags.groupby("link")["player"].apply(list).to_dict()
    tags = tags[tags["how"] == "full"].drop_duplicates(["link", "player"])
    have = set(zip(tr["season_id"].astype(int), tr["window"].astype(str)))      # 이적 기록이 있는 시장만 판정
    tr["key"] = tr["player"].map(_fold)
    moves = {k: g for k, g in tr.groupby("key")}
    rows = []
    by_link = {k: g for k, g in tags.groupby("link")}
    for a in arts.itertuples(index=False):
        g = by_link.get(a.link)
        if g is None or a.stage not in STAGES:                     # 단계 낱말이 없는 이적 기사는 루머로 안 본다
            continue
        if MATCH_REPORT.search(str(a.link)):
            continue
        try:
            day = dt.date.fromisoformat(str(a.published or a.first_seen)[:10])
        except ValueError:
            continue
        sid, win, close = target_window(day)
        if (sid, win) not in have:
            continue
        found = idx.find(a.headline, names_by_link.get(a.link, []))
        clubs = [c for c in found if not c.startswith("from:")]
        if len(found) >= 3 or ROUNDUP.search(str(a.headline)):     # 여러 이적을 한 줄에 묶은 제목(라운드업·가십)은 누구 얘긴지 모른다
            continue
        head = f" {_fold(a.headline)} "
        for p in g.itertuples(index=False):
            if f" {_fold(p.player).split()[-1]} " not in head:      # 제목에 그 선수(성)가 있어야 — 요약에만 나온 선수는 딴 얘기
                continue
            mv = moves.get(_fold(p.player))
            mv_w = mv[(mv["season_id"] == sid) & (mv["window"] == win)] if mv is not None else None
            # 원래 클럽 — 그 시장에 들어온 기록이 있으면 그 전 클럽, 아니면 지금 클럽(태그)
            ins = mv_w[mv_w["direction"] == "in"] if mv_w is not None else None
            origin = str(ins["club"].iloc[0]) if ins is not None and len(ins) else str(p.squad)
            new_club = str(ins["squad"].iloc[0]) if ins is not None and len(ins) else ""
            dests = [c for c in clubs if not _same_club(c, origin) and not _same_club(c, p.squad if not new_club else origin)]
            if new_club:   # 이 시장에 옮긴 선수 — 태그 클럽(squad)이 이미 새 클럽이라 그건 행선지 후보로 남긴다
                dests = [c for c in clubs if not _same_club(c, origin)]
            for d in dests[:1]:                                  # 첫 클럽 = 보통 주어(사는 쪽) — 'Fulham agree to sign X from Real Madrid'
                moved_to_d = False
                if mv_w is not None and len(mv_w):
                    moved_to_d = any((r.direction == "in" and _same_club(r.squad, d)) or
                                     (r.direction == "out" and _same_club(r.club, d)) for r in mv_w.itertuples())
                resolved = today > close + dt.timedelta(days=GRACE_DAYS) or moved_to_d
                denied = a.stage == "denied"
                hit = (not moved_to_d) if denied else moved_to_d
                rows.append({"link": a.link, "date": day.isoformat(), "source": a.source or "", "journalists": a.journalists or "",
                             "stage": a.stage or "", "player": p.player, "origin": origin, "dest": d,
                             "window": f"{sid} {win}", "status": ("hit" if hit else "miss") if resolved else "pending",
                             "headline": a.headline})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # 사후 보도 빼기 — 그 이적(선수→행선지)이 처음 '확정'으로 보도된 날 뒤의 기사는 예측이 아니다(인터뷰·후일담)
    first_done = out[(out["stage"] == "done") & (out["status"] == "hit")].groupby(["player", "dest"])["date"].min()
    late = out.apply(lambda r: (r["player"], r["dest"]) in first_done.index and r["date"] > first_done[(r["player"], r["dest"])], axis=1)
    return out[~late].reset_index(drop=True)


def reliability(cl: pd.DataFrame) -> pd.DataFrame:
    """매체·기자별 적중률 — 판정된 루머만, 베타 사전분포(전체 적중률)로 줄인 점수."""
    done = cl[cl["status"] != "pending"].drop_duplicates(["link", "player", "dest"])
    if done.empty:
        return pd.DataFrame(columns=["kind", "name", "n", "hits", "rate", "score", "pending", "by_stage"])
    base = float((done["status"] == "hit").mean())
    out = []

    def add(kind: str, name: str, g: pd.DataFrame, pend: int):
        n, h = len(g), int((g["status"] == "hit").sum())
        st = {s: f"{int((x['status'] == 'hit').sum())}/{len(x)}" for s, x in g.groupby("stage") if s}
        out.append({"kind": kind, "name": name, "n": n, "hits": h, "rate": round(h / n, 3),
                    "score": round((h + PRIOR * base) / (n + PRIOR), 3), "pending": pend,
                    "by_stage": " ".join(f"{k}:{v}" for k, v in sorted(st.items()))})

    pend_src = cl[cl["status"] == "pending"].groupby("source").size()
    for src, g in done.groupby("source"):
        add("outlet", str(src), g, int(pend_src.get(src, 0)))
    jr = done.assign(j=done["journalists"].fillna("").str.split("|")).explode("j")
    jr = jr[jr["j"].astype(str).str.len() > 0]
    for j, g in jr.groupby("j"):
        add("journalist", str(j), g, 0)
    add("all", "ALL", done, int((cl["status"] == "pending").sum()))
    res = pd.DataFrame(out)
    res["few"] = res["n"] < MIN_N
    return res.sort_values(["kind", "score", "n"], ascending=[True, False, False])


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cl = claims()
    if cl.empty:
        print("[reliability] 루머 0건 — 기존 파일 유지")
        return 0
    cl.to_csv(OUT_CLAIMS, index=False)
    rel = reliability(cl)
    rel.to_csv(OUT_REL, index=False)
    st = cl["status"].value_counts().to_dict()
    print(f"[reliability] 루머 {len(cl)}건 {st} · 매체 {int((rel['kind'] == 'outlet').sum())} · 기자 {int((rel['kind'] == 'journalist').sum())}")
    allr = rel[rel["kind"] == "all"]
    if len(allr):
        print(f"[reliability] 전체 적중 {int(allr['hits'].iloc[0])}/{int(allr['n'].iloc[0])} · 단계별 {allr['by_stage'].iloc[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
