"""
포지션 템플릿 — 세부 포지션마다 다른 지표·레이더 축, 같은 템플릿 선수끼리 백분위(선수 화면·리포트·비교).

템플릿(TM 세부 포지션 → 8개):
  GK  Goalkeeper
  CB  Centre-Back
  FB  Left-Back · Right-Back(윙백 포함)
  DM  Defensive Midfield          — 끊기·회수·경합 + 안전한 배급
  CM  Central Midfield            — 전진 배급·연결 + 양방향 활동
  AM  Attacking Midfield · Second Striker — 찬스 메이킹·박스 근처 위협
  W   Left/Right Winger · Left/Right Midfield — 1대1 돌파·크로스·마무리
  ST  Centre-Forward              — 득점·슈팅 질·공중볼·연계
TM 포지션이 없으면 FBref 대분류(GK·DF·MF·FW)로 CB·CM·ST 에 둔다.

백분위 비교 대상 = 같은 리그 같은 템플릿(최소 출전 450′, GK 300′). 20명 미만이면 8개 리그 같은 템플릿으로 넓힌다
(EPL CM·AM 이 시즌 초 13명뿐이라 백분위가 0·8·15… 로 거칠었다).
동률은 중간 순위 — 대부분 0 인 '실수' 에서 실수 0 인 선수가 낮게 나오지 않게.
성공률(%) 지표는 시도 수를 성공 수 ÷ 성공률로 되짚어 10회 미만이면 low(표본 부족) — 화면은 회색, 평균·레이더·강약점에서 뺀다.
낮을수록 좋은 지표(실수·파울)는 inv 로 뒤집는다.
"""
from __future__ import annotations

import pandas as pd

MIN_ATTEMPTS = 10
MIN_PEERS = 20

TM_TEMPLATE = {
    "Goalkeeper": "GK", "Centre-Back": "CB", "Left-Back": "FB", "Right-Back": "FB",
    "Defensive Midfield": "DM", "Central Midfield": "CM", "Attacking Midfield": "AM", "Second Striker": "AM",
    "Left Winger": "W", "Right Winger": "W", "Left Midfield": "W", "Right Midfield": "W", "Centre-Forward": "ST",
}
LABEL = {
    "GK": ("GOALKEEPER", "골키퍼"), "CB": ("CENTRE-BACK", "센터백"), "FB": ("FULL-BACK", "풀백·윙백"),
    "DM": ("DEFENSIVE MIDFIELDER", "수비형 미드필더"), "CM": ("CENTRAL MIDFIELDER", "중앙 미드필더"),
    "AM": ("ATTACKING MIDFIELDER", "공격형 미드필더"), "W": ("WINGER", "윙어"), "ST": ("STRIKER", "스트라이커"),
}

# 지표 — (라벨, 열, 낮을수록 좋음, 시도 수 규칙)
M = {
    "npg": ("비PK골/90", "npg_per90", False, None),
    "npxg": ("npxG/90", "npxg_p90", False, None),
    "shots": ("슈팅/90", "shots_p90", False, None),
    "sot": ("유효슈팅/90", "sot_per90", False, None),
    "finish": ("결정력(골−xG)/90", "_finish", False, None),
    "xa": ("xA/90", "xa_p90", False, None),
    "kp": ("키패스/90", "key_passes_per90", False, None),
    "bigc": ("빅찬스 창출/90", "big_chances_created_per90", False, None),
    "f3": ("파이널서드 패스/90", "final_third_passes_per90", False, None),
    "pass": ("패스성공%", "pass_pct", False, None),
    "long": ("롱패스%", "long_ball_pct", False, None),
    "drib": ("드리블 성공/90", "successful_dribbles_per90", False, None),
    "dribp": ("드리블 성공%", "dribble_success_pct", False, "dribble"),
    "cross": ("크로스/90", "crosses_per90", False, None),
    "crossp": ("크로스 정확%", "cross_acc_pct", False, "cross"),
    "tkl": ("태클 성공/90", "tackles_won_per90_ss", False, None),
    "tklp": ("태클 성공%", "tackles_won_pct", False, "tackle"),
    "int": ("인터셉트/90", "interceptions_per90_ss", False, None),
    "rec": ("볼 회수/90", "recoveries_per90", False, None),
    "clr": ("클리어링/90", "clearances_per90", False, None),
    "blk": ("슈팅 블록/90", "blocked_shots_per90", False, None),
    "aer": ("공중볼 승/90", "aerial_won_per90", False, None),
    "aerp": ("공중볼%", "aerial_won_pct", False, "aerial"),
    "grdp": ("지상 경합%", "ground_duels_won_pct", False, "ground"),
    "duelp": ("경합 승률%", "total_duels_won_pct", False, "duel"),
    "press": ("전방 볼 탈취/90", "possession_won_att_per90", False, None),
    "err": ("실수(적을수록)/90", "errors_per90", True, None),
    "foul": ("파울(적을수록)/90", "fouls_per90", True, None),
    "save": ("선방%", "gk_save_pct", False, "save"),
    "saves": ("선방/90", "gk_saves_per90", False, None),
    "cs": ("클린시트%", "gk_cs_pct", False, None),
    "claim": ("하이 클레임/90", "gk_high_claims_per90", False, None),
    "sweep": ("스위핑/90", "gk_runs_out_per90", False, None),
    "punch": ("펀칭/90", "gk_punches_per90", False, None),
}

# 템플릿 — 레이더 8축 + 지표 묶음(이름, 지표들)
TEMPLATES: dict[str, dict] = {
    "GK": {"radar": ["save", "saves", "cs", "claim", "sweep", "pass", "long", "err"],
           "cats": [("선방", ["save", "saves", "cs"]), ("박스 지배", ["claim", "punch", "sweep"]), ("빌드업", ["pass", "long"]), ("안정성", ["err"])]},
    "CB": {"radar": ["aerp", "aer", "tklp", "int", "clr", "blk", "pass", "long"],
           "cats": [("경합", ["aerp", "aer", "grdp", "tklp"]), ("수비 행동", ["int", "clr", "blk", "rec"]),
                    ("빌드업", ["pass", "long", "f3"]), ("안정성", ["err", "foul"])]},
    "FB": {"radar": ["cross", "crossp", "kp", "drib", "f3", "tkl", "int", "grdp"],
           "cats": [("측면 공격", ["cross", "crossp", "kp", "xa"]), ("전진", ["drib", "dribp", "f3"]),
                    ("수비", ["tkl", "tklp", "int", "rec"]), ("경합", ["grdp", "aerp"])]},
    "DM": {"radar": ["tkl", "int", "rec", "grdp", "aerp", "pass", "long", "f3"],
           "cats": [("끊기", ["tkl", "tklp", "int", "rec"]), ("경합", ["grdp", "aerp", "duelp"]),
                    ("배급", ["pass", "long", "f3"]), ("규율", ["foul", "err"])]},
    "CM": {"radar": ["f3", "pass", "long", "kp", "xa", "drib", "rec", "tkl"],
           "cats": [("전진 배급", ["f3", "pass", "long"]), ("창조", ["kp", "xa", "bigc"]),
                    ("운반", ["drib", "dribp"]), ("수비 기여", ["rec", "tkl", "int"])]},
    "AM": {"radar": ["kp", "bigc", "xa", "npxg", "shots", "drib", "f3", "press"],
           "cats": [("찬스 메이킹", ["kp", "bigc", "xa"]), ("득점 위협", ["npxg", "npg", "shots"]),
                    ("볼 운반", ["drib", "dribp", "f3"]), ("전방 압박", ["press", "rec"])]},
    "W": {"radar": ["drib", "dribp", "npxg", "shots", "xa", "kp", "crossp", "press"],
          "cats": [("1대1 돌파", ["drib", "dribp"]), ("득점", ["npxg", "npg", "shots", "finish"]),
                   ("찬스 메이킹", ["xa", "kp", "cross", "crossp"]), ("전방 압박", ["press", "rec"])]},
    "ST": {"radar": ["npg", "npxg", "shots", "sot", "finish", "aerp", "kp", "press"],
           "cats": [("득점", ["npg", "npxg", "finish"]), ("슈팅", ["shots", "sot"]),
                    ("연계·창조", ["kp", "xa", "bigc"]), ("공중볼·압박", ["aerp", "aer", "press"])]},
}


def template_of(tm_position, fb_pos=None) -> str:
    t = TM_TEMPLATE.get(str(tm_position or "").strip())
    if t:
        return t
    p = str(fb_pos or "").upper()
    return "GK" if p.startswith("GK") else "CB" if p.startswith("DF") else "ST" if p.startswith("FW") else "CM"


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """계산 지표 — 결정력 = 비PK골/90 − npxG/90. 템플릿 열도 붙인다."""
    df = df.copy()
    num = lambda c: pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series(float("nan"), index=df.index)  # noqa: E731
    df["_finish"] = num("npg_per90") - num("npxg_p90")
    df["_template"] = [template_of(t, p) for t, p in zip(df.get("tm_position", pd.Series(index=df.index)),
                                                         df.get("pos", pd.Series(index=df.index)))]
    return df


def attempts(row, rule: str | None) -> float | None:
    """성공률 지표의 시도 수(시즌) — 성공 수/90 ÷ 성공률 × 출전 분/90. 규칙 없으면 None."""
    if not rule:
        return None

    def f(c):
        try:
            v = float(row.get(c))
            return v if v == v else 0.0
        except (TypeError, ValueError):
            return 0.0
    mins = f("minutes") / 90

    def per(won, pct):
        p = f(pct)
        return f(won) / (p / 100) * mins if p > 0 else (0.0 if f(won) == 0 else None)
    if rule == "aerial":
        return per("aerial_won_per90", "aerial_won_pct")
    if rule == "dribble":
        return per("successful_dribbles_per90", "dribble_success_pct")
    if rule == "tackle":
        return per("tackles_won_per90_ss", "tackles_won_pct")
    if rule == "ground":
        return per("ground_duels_won_per90", "ground_duels_won_pct")
    if rule == "duel":
        a, g = per("aerial_won_per90", "aerial_won_pct"), per("ground_duels_won_per90", "ground_duels_won_pct")
        return (a or 0) + (g or 0)
    if rule == "cross":
        return f("crosses_per90") * mins
    if rule == "save":
        return per("gk_saves_per90", "gk_save_pct")
    return None


def percentile(pool: pd.DataFrame, col: str, v: float, inv: bool) -> int | None:
    if col not in pool.columns:
        return None
    s = pd.to_numeric(pool[col], errors="coerce").dropna()
    if s.empty or v != v:
        return None
    below = (s > v).mean() if inv else (s < v).mean()
    p = (below + 0.5 * (s == v).mean()) * 100              # 중간 순위(동률 절반)
    return int(round(p))


def profile(row, pool: pd.DataFrame, template: str) -> dict:
    """한 선수 → {categories, radar, metrics}. pool = 같은 템플릿 비교 대상(출전 기준 통과)."""
    tpl = TEMPLATES[template]

    def metric(k: str) -> dict | None:
        label, col, inv, rule = M[k]
        try:
            v = float(row.get(col))
        except (TypeError, ValueError):
            return None
        if v != v:
            return None
        p = percentile(pool, col, v, inv)
        if p is None:
            return None
        att = attempts(row, rule)
        low = att is not None and att < MIN_ATTEMPTS
        return {"key": k, "label": label, "pct": p, "raw": round(v, 2), "inv": inv, "low": low,
                "att": None if att is None else int(round(att))}

    cats = []
    for name, keys in tpl["cats"]:
        ms = [m for m in (metric(k) for k in keys) if m]
        if not ms:
            continue
        ok = [m["pct"] for m in ms if not m["low"]]
        cats.append({"name": name, "avg": int(round(sum(ok) / len(ok))) if ok else None, "metrics": ms})
    radar = []
    for k in tpl["radar"]:
        m = metric(k)
        if m:
            radar.append({"axis": m["label"].split("(")[0].replace("/90", ""), "value": m["pct"], "low": m["low"],
                          "full": m["label"]})
    return {"categories": [c for c in cats if c["avg"] is not None or c["metrics"]], "radar": radar}
