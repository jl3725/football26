"""
선수 평점(OVR·폼) 품질 평가 — 모델을 바꾸기 전후를 같은 잣대로 비교한다.

8개 리그 현재 시즌 전 선수의 OVR·폼을 API 와 같은 함수로 계산해 스냅샷으로 남기고, 아래를 점검한다.
  분포      OVR 상위 분위수·90+ 인원, 폼 95+·99 인원(포지션별) — 포화(99 남발) 탐지
  리그 편향  리그별 평균 (OVR − 시장가치 기준점) — 약한 리그 선수가 평점 보정으로 부풀려지는지
  시장 정합  OVR 과 시장가치의 순위 상관(Spearman), 상위 30명 리그 구성 비교
  기준 선수  data/eval/golden.csv — 사용자 지적·스카우트 기준표의 범위(range)·대소(pair) 기대치 위반 목록
  스카우트  data/eval/scout_reference.csv — 프로 스카우트 시선의 선수별 기대 범위(우리 척도 ≈ FC 능력치 +2).
            벗어난 선수와 폭을 보여 주고, 3 이상 벗어나면 watchdog 이 이슈를 연다(golden 처럼 CI 를 막지는 않음).
  자동 점검  audit() — 사람이 보기 전에 이상한 숫자를 잡는다(한 시즌 급등·급락, 평균 이하 경기력인데 고평점,
            21세 이하 고평점, 시장가치 없는 고평점). 화면의 '지난 시즌 대비 ±' 와 같은 값으로 본다.

사용:
    python scripts/eval_ratings.py --tag before            # 스냅샷 저장 + 리포트
    python scripts/eval_ratings.py --tag after --compare before
    python scripts/eval_ratings.py --tag ci --check        # golden 위반이 있으면 종료코드 1 (CI)
    python scripts/eval_ratings.py --audit-json data/eval/rating_audit.json --no-snapshot   # daily_data → watchdog
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import ratings_v3 as rv3  # noqa: E402
from leagues import LEAGUES  # noqa: E402

EVAL_DIR = ROOT / "data" / "eval"


def _num(v):
    v = pd.to_numeric(v, errors="coerce")
    return None if pd.isna(v) else float(v)


def snapshot() -> pd.DataFrame:
    """API 와 같은 입구(player_frame: 대회별 선발 수 병합·`_ovr`·`_form` 선계산)로 계산.

    api.main 을 import 하지 않는다 — daily_data(FastAPI 미설치)에서도 돌게. 값은 API 의
    _player_ovr·_player_form·_trend(ovr_prev)와 같다.
    """
    import rating_history as rh  # noqa: PLC0415
    from api.services.player_data import player_frame  # noqa: PLC0415
    prev = rh.prev_season_ovr()
    rows = []
    for lg in LEAGUES:
        df = player_frame(lg)
        if df is None:
            continue
        for _, r in df.iterrows():
            ovr = r.get("_ovr")
            ovr = int(ovr) if ovr is not None and ovr == ovr else rv3.ovr_of_row(r)
            form = r.get("_form")
            form = int(form) if form is not None and form == form else None
            ln = rv3.line_of_row(r)
            p = rh.lookup_prev(prev, r)
            cls = rv3.class_ss(r.get("ss_rating"), r.get("minutes"), r.get("prev_ss_rating"), r.get("prev_minutes"),
                               ln, r.get("_league_level"), rv3._prev_level(r))
            rows.append({"league": lg, "player": r["player"], "squad": r.get("squad"), "line": ln,
                         "age": r.get("age"), "minutes": _num(r.get("minutes")),
                         "prev_minutes": _num(r.get("prev_minutes")),
                         "ss_rating": _num(r.get("ss_rating")),
                         "value": _num(r.get("market_value_eur")),
                         "class_vs_mid": round(cls - rv3._SS_MID[ln], 3) if cls > 0 else None,
                         "ovr_prev": p["ovr"] if p and p.get("minutes", 0) >= 300 else None,
                         "prev_season_min": p.get("minutes") if p else None,
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


# 자동 점검 기준 — 이 수를 넘으면 watchdog 이 이슈를 연다(정상 범위는 2026-10-15 v3.4 기준 측정치의 약 2배)
AUDIT_LIMITS = {"rise": 25, "fall": 25, "underperf_high": 10, "young_elite": 6, "no_value_high": 10}


def audit(s: pd.DataFrame) -> dict:
    """이상 수치 자동 점검 — {이름: {n, limit, desc, examples}}. 화면의 '지난 시즌 대비 ±'(ovr_prev)와 같은 값."""
    d = s.copy()
    d["delta"] = d["ovr"] - d["ovr_prev"]
    full_prev = d["prev_season_min"].fillna(0) >= 1500
    rules = {
        "rise": ("지난 시즌(1,500분+) 대비 +6 이상 — 한 시즌 급등", full_prev & (d["delta"] >= 6)),
        "fall": ("지난 시즌(1,500분+) 대비 −8 이하 — 급락(부상·이적·데이터 오류?)",
                 full_prev & (d["delta"] <= -8) & (d["minutes"].fillna(0) >= 450)),
        "underperf_high": ("OVR 86+ 인데 리그 보정 평점이 포지션 평균보다 0.1 넘게 낮음(900분+)",
                           (d["ovr"] >= 86) & (d["class_vs_mid"] < -0.1)
                           & (d["minutes"].fillna(0) + d["prev_minutes"].fillna(0) >= 900)),
        "young_elite": ("21세 이하 OVR 88+", (d["age"] <= 21) & (d["ovr"] >= 88)),
        "no_value_high": ("시장가치 없이 OVR 80+ (TM 매칭 실패·이적 잔류 행)", d["value"].isna() & (d["ovr"] >= 80)),
    }
    out = {}
    for k, (desc, m) in rules.items():
        x = d[m].sort_values("ovr", ascending=False)
        ex = [f"{r.player}({r.squad}, {'' if pd.isna(r.age) else int(r.age)}) {r.ovr}"
              + ("" if pd.isna(r.ovr_prev) else f" ← {int(r.ovr_prev)}") for r in x.head(8).itertuples()]
        out[k] = {"n": int(m.sum()), "limit": AUDIT_LIMITS[k], "desc": desc, "examples": ex}
    return out


def scout(s: pd.DataFrame) -> list[dict]:
    """스카우트 기준표 이탈 — [{player, league, ovr, lo, hi, off}] (off = 범위 밖으로 벗어난 폭, 큰 순)."""
    path = EVAL_DIR / "scout_reference.csv"
    if not path.exists():
        return []
    look = {(r.league, r.player): r.ovr for r in s.sort_values("minutes").itertuples()}
    out = []
    for g in pd.read_csv(path).itertuples():
        v = look.get((g.league, g.player))
        if v is None:
            continue
        off = (g.lo - v) if v < g.lo else (v - g.hi) if v > g.hi else 0
        if off:
            out.append({"player": g.player, "league": g.league, "ovr": int(v), "lo": int(g.lo), "hi": int(g.hi),
                        "off": int(off) if v > g.hi else -int(off)})
    return sorted(out, key=lambda x: -abs(x["off"]))


def golden(s: pd.DataFrame) -> list[str]:
    """data/eval/golden.csv — kind=range(lo≤값≤hi) | pair(a 값 ≥ b 값). 위반만 돌려준다."""
    path = EVAL_DIR / "golden.csv"
    if not path.exists():
        return []
    # 같은 리그 동명 행(이적 전 팀 잔류 행 등)은 출전이 많은 쪽
    look = {(r.league, r.player): r for r in s.sort_values("minutes").itertuples()}
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
    ap.add_argument("--tag", default="latest")
    ap.add_argument("--compare", default="")
    ap.add_argument("--show", default="", help="쉼표로 구분한 선수 이름 — 전후 값 출력")
    ap.add_argument("--check", action="store_true", help="golden 위반이 있으면 종료코드 1")
    ap.add_argument("--audit-json", default="", help="자동 점검 결과를 JSON 으로(watchdog 이 읽음)")
    ap.add_argument("--no-snapshot", action="store_true", help="ratings_<tag>.csv 를 남기지 않음")
    args = ap.parse_args(argv)

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    s = snapshot()
    if not args.no_snapshot:
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
    sc = scout(s)
    far = [x for x in sc if abs(x["off"]) >= 3]
    print(f"  스카우트 기준 이탈 {len(sc)}건 (3 이상 {len(far)}건)")
    if sc:
        print("      " + " | ".join(f"{x['player']} {x['ovr']} ({x['lo']}~{x['hi']}, {x['off']:+d})" for x in sc))
    au = audit(s)
    print("  자동 점검")
    for k, v in au.items():
        flag = "  ← 기준 초과" if v["n"] > v["limit"] else ""
        print(f"    {k:15} {v['n']:3d}건 (한도 {v['limit']}) {v['desc']}{flag}")
        if v["examples"]:
            print("      " + " | ".join(v["examples"]))
    if args.audit_json:
        Path(args.audit_json).write_text(json.dumps(
            {"date": dt.date.today().isoformat(), "model": rv3.MODEL_VERSION, "players": len(s),
             "golden": bad, "scout": sc, "scout_far": far, "audit": au}, ensure_ascii=False, indent=1),
            encoding="utf-8")
    if args.show:
        names = [n.strip() for n in args.show.split(",")]
        cur = s[s.player.isin(names)][["league", "player", "line", "minutes", "ss_rating", "value", "ovr", "form"]]
        if prev is not None:
            cur = cur.merge(prev[["league", "player", "ovr", "form"]], on=["league", "player"], suffixes=("", "_이전"))
        print(cur.to_string(index=False))
    return 1 if (args.check and bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())
