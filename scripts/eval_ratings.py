"""
선수 평점(OVR·폼) 품질 평가 — 모델을 바꾸기 전후를 같은 잣대로 비교한다.

8개 리그 현재 시즌 전 선수의 OVR·폼을 API 와 같은 함수로 계산해 스냅샷으로 남기고, 아래를 점검한다.
  분포      OVR 상위 분위수·90+ 인원, 폼 95+·99 인원(포지션별) — 포화(99 남발) 탐지
  리그 편향  리그별 평균 (OVR − 시장가치 기준점) — 약한 리그 선수가 평점 보정으로 부풀려지는지
  시장 정합  OVR 과 시장가치의 순위 상관(Spearman), 상위 30명 리그 구성 비교
  기준 선수  data/eval/golden.csv — 사용자가 정한 범위(range)·대소(pair) 기대치 위반 목록

사용:
    python scripts/eval_ratings.py --tag before            # 스냅샷 저장 + 리포트
    python scripts/eval_ratings.py --tag after --compare before
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import ratings_v3 as rv3  # noqa: E402
from leagues import LEAGUES  # noqa: E402

EVAL_DIR = ROOT / "data" / "eval"


def snapshot() -> pd.DataFrame:
    """API 와 같은 입구(player_frame: 대회별 선발 수 병합)와 같은 함수(_player_ovr·_player_form)로 계산."""
    import api.main as api  # noqa: PLC0415
    from api.services.player_data import player_frame  # noqa: PLC0415
    rows = []
    for lg in LEAGUES:
        df = player_frame(lg)
        if df is None:
            continue
        for _, r in df.iterrows():
            ovr, form = api._player_ovr(r), api._player_form(r)
            rows.append({"league": lg, "player": r["player"], "squad": r.get("squad"), "line": rv3.line_of_row(r),
                         "age": r.get("age"), "minutes": pd.to_numeric(r.get("minutes"), errors="coerce"),
                         "ss_rating": pd.to_numeric(r.get("ss_rating"), errors="coerce"),
                         "value": pd.to_numeric(r.get("market_value_eur"), errors="coerce"),
                         "ovr": ovr, "form": form})
    s = pd.DataFrame(rows)
    s["value_base"] = s["value"].map(lambda v: rv3.value_ovr(v) if pd.notna(v) else None)
    return s


def report(s: pd.DataFrame) -> dict:
    out: dict = {}
    reg = s[s.minutes >= 450]
    out["OVR p50/p90/p99/최대"] = "/".join(str(int(reg.ovr.quantile(q))) for q in (0.5, 0.9, 0.99)) + f"/{int(s.ovr.max())}"
    out["OVR 90+ 인원"] = int((s.ovr >= 90).sum())
    f = s.dropna(subset=["form"])
    out["폼 산정 인원"] = len(f)
    out["폼 95+ 인원"] = int((f.form >= 95).sum())
    out["폼 99 인원"] = int((f.form >= 99).sum())
    out["폼 중앙값(포지션별)"] = " ".join(f"{k}:{int(v)}" for k, v in f.groupby("line").form.median().items())
    b = reg.dropna(subset=["value_base"])
    bias = (b.ovr - b.value_base).groupby(b.league).mean()
    out["리그 편향(OVR−시장가치 기준점)"] = " ".join(f"{k}:{v:+.1f}" for k, v in bias.items())
    out["OVR~시장가치 순위상관"] = round(b.ovr.rank().corr(b.value.rank()), 3)
    top_o = s.nlargest(30, "ovr").league.value_counts()
    top_v = s.nlargest(30, "value").league.value_counts()
    out["상위30 리그구성 OVR | 시장가치"] = (" ".join(f"{k}:{v}" for k, v in top_o.items()) + "  |  "
                                    + " ".join(f"{k}:{v}" for k, v in top_v.items()))
    return out


def golden(s: pd.DataFrame) -> list[str]:
    """data/eval/golden.csv — kind=range(lo≤값≤hi) | pair(a 값 ≥ b 값). 위반만 돌려준다."""
    path = EVAL_DIR / "golden.csv"
    if not path.exists():
        return []
    look = {(r.league, r.player): r for r in s.itertuples()}
    bad = []
    with path.open(encoding="utf-8") as fh:
        for g in csv.DictReader(fh):
            a = look.get((g["league"], g["player"]))
            if a is None:
                bad.append(f"[없음] {g['league']} {g['player']}")
                continue
            va = getattr(a, g["metric"])
            if g["kind"] == "range":
                if not (float(g["lo"]) <= va <= float(g["hi"])):
                    bad.append(f"[범위] {g['player']} {g['metric']}={va} (기대 {g['lo']}~{g['hi']}) — {g['note']}")
            elif g["kind"] == "pair":
                b = look.get((g["league_b"], g["player_b"]))
                vb = getattr(b, g["metric"]) if b is not None else None
                if vb is not None and va < vb:
                    bad.append(f"[대소] {g['player']} {va} < {g['player_b']} {vb} (기대 ≥) — {g['note']}")
    return bad


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--compare", default="")
    ap.add_argument("--show", default="", help="쉼표로 구분한 선수 이름 — 전후 값 출력")
    args = ap.parse_args(argv)

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    s = snapshot()
    s.to_csv(EVAL_DIR / f"ratings_{args.tag}.csv", index=False)
    rep = report(s)
    prev = None
    if args.compare:
        prev = pd.read_csv(EVAL_DIR / f"ratings_{args.compare}.csv")
        prep = report(prev)
    print(f"== 평점 평가 [{args.tag}] 선수 {len(s)}명")
    for k, v in rep.items():
        print(f"  {k:28} {v}" + (f"\n  {'':28} (이전 {prep[k]})" if prev is not None else ""))
    bad = golden(s)
    print(f"  기준 선수 위반 {len(bad)}건")
    for b in bad:
        print("   ", b)
    if args.show:
        names = [n.strip() for n in args.show.split(",")]
        cur = s[s.player.isin(names)][["league", "player", "line", "minutes", "ss_rating", "value", "ovr", "form"]]
        if prev is not None:
            cur = cur.merge(prev[["league", "player", "ovr", "form"]], on=["league", "player"], suffixes=("", "_이전"))
        print(cur.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
