"""
뉴스 종류 분류 평가 표본 — 최근 기사 리그별 표본에 Gemini(무료) 정답 표시 → data/eval/news_kind_eval.csv.

2026-10-23 사용자 '뉴스 이적 분류 잡음 정리'. 규칙(src/news_classify.py)이 제목에 이적 낱말이 하나라도 있으면 '이적'으로 정해
비·대출·경기·핸드볼 기사가 걸렸고, 튀르키예어·덴마크어 낱말이 없어 쉬페르리그 기사 291건 중 214건이 '기타'였다.
낱말을 짐작으로 고치지 않고 이 표본으로 정밀도·재현율을 잰다(tests/test_news_classify_eval.py 가 기준선 아래로 떨어지면 실패).
정답은 AI 가 붙인 것이라 완벽하지 않다 — 규칙과 AI 가 다른 줄만 따로 모아 볼 수 있다(--diff).

    python scripts/build_news_eval.py [--per 30] [--days 10]
    python scripts/build_news_eval.py --diff
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "data" / "eval" / "news_kind_eval.csv"
COLS = ["link", "league", "team", "source", "headline", "descr", "ai_kind", "ai_stage"]


def sample(per: int, days: int) -> pd.DataFrame:
    import datetime as dt
    import news_store  # noqa: PLC0415
    from leagues import LEAGUES, data_path  # noqa: PLC0415
    db = news_store.ensure()
    con = sqlite3.connect(db)
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    parts = []
    for lg in LEAGUES:
        p = data_path("standings", lg)
        if not p.exists():
            continue
        teams = list(pd.read_csv(p)["squad"].astype(str))
        q = ",".join("?" * len(teams))
        df = pd.read_sql(f"SELECT link, team, source, headline, descr FROM articles WHERE team IN ({q}) AND published >= ? "
                         f"ORDER BY random() LIMIT {per}", con, params=[*teams, since])
        df["league"] = lg
        parts.append(df)
    out = pd.concat(parts, ignore_index=True).drop_duplicates("link")
    out["descr"] = out["descr"].fillna("").astype(str).str.slice(0, 200)
    return out


def sample_transfer(n: int, days: int) -> pd.DataFrame:
    """지금 '이적'으로 분류된 기사 표본(정밀도 재기용) — 리그 무관, 최근 days 일."""
    import datetime as dt
    import news_store  # noqa: PLC0415
    from leagues import LEAGUES, data_path  # noqa: PLC0415
    con = sqlite3.connect(news_store.ensure())
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    team_lg = {}
    for lg in LEAGUES:
        p = data_path("standings", lg)
        if p.exists():
            team_lg.update({t: lg for t in pd.read_csv(p)["squad"].astype(str)})
    df = pd.read_sql("SELECT a.link, a.team, a.source, a.headline, a.descr FROM articles a JOIN article_meta m ON a.link = m.link "
                     f"WHERE m.kind = 'transfer' AND a.published >= ? ORDER BY random() LIMIT {n}", con, params=[since])
    df["league"] = df["team"].map(team_lg).fillna("")
    df["descr"] = df["descr"].fillna("").astype(str).str.slice(0, 200)
    return df


def label(df: pd.DataFrame) -> pd.DataFrame:
    import llm  # noqa: PLC0415
    import news_classify as nc  # noqa: PLC0415
    llm.start("news_eval", daily=20)
    rows = df.to_dict("records")
    kinds, stages = {}, {}
    for i in range(0, len(rows), 40):
        chunk = rows[i:i + 40]
        items = "\n".join(f"{j}. [{r.get('source') or ''}] {r.get('headline') or ''}" + (f" — {r['descr']}" if r.get("descr") else "")
                          for j, r in enumerate(chunk))
        out = llm.generate_json(nc.PROMPT.format(items=items), nc.SYSTEM)
        for o in out if isinstance(out, list) else []:
            try:
                r = chunk[int(o.get("i"))]
            except (TypeError, ValueError, IndexError, AttributeError):
                continue
            k = str(o.get("kind") or "").lower()
            if k in nc.KINDS:
                kinds[r["link"]] = k
                stages[r["link"]] = str(o.get("stage") or "").lower() if k == "transfer" else ""
    llm.finish()
    df = df.copy()
    df["ai_kind"] = df["link"].map(kinds)
    df["ai_stage"] = df["link"].map(stages).fillna("")
    return df.dropna(subset=["ai_kind"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=30)
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--add-transfer", type=int, default=0, help="지금 '이적' 분류 기사 N건을 더해 정밀도 표본을 키운다")
    a = ap.parse_args()
    if a.diff:
        import news_classify as nc  # noqa: PLC0415
        e = pd.read_csv(OUT)
        e["rule"] = [nc.rule_kind(h, d) for h, d in zip(e["headline"].astype(str), e["descr"].fillna("").astype(str))]
        for r in e[e["rule"] != e["ai_kind"]].to_dict("records"):
            print(f"{r['league']:18} rule={r['rule']:9} ai={r['ai_kind']:9} | {str(r['headline'])[:100]}")
        return 0
    if a.add_transfer:
        old = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame(columns=COLS)
        add = sample_transfer(a.add_transfer, a.days)
        add = add[~add["link"].isin(set(old["link"]))]
        df = pd.concat([old, label(add)], ignore_index=True)
    else:
        df = label(sample(a.per, a.days))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df[COLS].to_csv(OUT, index=False, encoding="utf-8", lineterminator="\n")
    print(f"news eval {len(df)}건 → {OUT.name} · {df['ai_kind'].value_counts().to_dict()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
