"""이적창 반영 스쿼드 재구성 — 팀 rating 의 유기적 반영용.

players_full(지난 시즌 스쿼드)에 **이번 창의 영구 이적(IN/OUT)** 을 적용해
'현재 스쿼드' DataFrame 을 만든다. 그러면 ratings.compute_team_ratings 의
스쿼드 품질 항목이 자동으로 이적을 반영한다(영입↑·방출↓).

규칙:
- 임대·임대복귀("loan")는 제외 — 영구이적이 아니라 노이즈.
- 리그 내 이동: 선수의 실제 레이팅 행(ss/가치/출전)을 목적팀으로 이전.
- 리그 밖 영입: players_full 에 없으므로 이적료(fee_eur)를 시장가치로 근사.
- 방출: 해당 팀 스쿼드에서 제거.
리그 전체에 적용해야 (상대) 순위 기반 지표가 정확하다.
"""
from __future__ import annotations

import pandas as pd
from unidecode import unidecode


def _norm(x) -> str:
    return unidecode(str(x)).lower().strip()


# transfermarkt 포지션 문자열 → fl_group 코드 (ratings._role_quality_pct 가 인식)
_POS_MAP = [
    ("goalkeeper", "GK"), ("keeper", "GK"),
    ("centre-back", "CB"), ("center-back", "CB"), ("centre back", "CB"),
    ("left-back", "FB"), ("right-back", "FB"), ("full-back", "FB"), ("wing-back", "FB"),
    ("defensive midfield", "DM"), ("central midfield", "CM"),
    ("attacking midfield", "AM"), ("midfield", "CM"),
    ("winger", "W"), ("wing", "W"),
    ("centre-forward", "ST"), ("second striker", "ST"), ("striker", "ST"), ("forward", "ST"),
    ("back", "CB"),  # 마지막 폴백(그 외 'back')
]

_SYNTH_MINUTES = 1000  # 신규 영입 가정 출전(스쿼드 품질 계산에 포함되도록)


def _fl_from_pos(pos) -> str:
    p = _norm(pos)
    for key, code in _POS_MAP:
        if key in p:
            return code
    return ""


def build_adjusted_full(full_df, transfers, win) -> "pd.DataFrame | None":
    """이번 창 영구 이적을 반영한 players_full 사본. 데이터 없으면 원본 그대로."""
    if full_df is None or transfers is None or not win:
        return full_df
    need = {"squad", "direction", "player"}
    if not need.issubset(transfers.columns):
        return full_df

    tt = transfers.copy()
    if "season_id" in tt.columns:
        tt = tt[pd.to_numeric(tt["season_id"], errors="coerce") == win.get("season_id")]
    if "window" in tt.columns:
        tt = tt[tt["window"].astype(str) == str(win.get("window"))]
    if tt.empty:
        return full_df

    valid_squads = set(full_df["squad"].astype(str)) if "squad" in full_df.columns else set()
    adj = full_df.copy()
    adj["_norm"] = adj["player"].map(_norm)

    ins = tt[tt["direction"] == "in"].copy()
    outs = tt[tt["direction"] == "out"].copy()
    # 임대는 영구 스쿼드 변화가 아님. 단, OUT 의 '임대 종료(End of loan)'는 로anee 반환 = 실제 이탈.
    if "fee_text" in ins.columns:
        ins = ins[~ins["fee_text"].astype(str).str.lower().str.contains("loan", na=False)]
    if "fee_text" in outs.columns:
        ofee = outs["fee_text"].astype(str).str.lower()
        outs = outs[~(ofee.str.contains("loan", na=False) & ~ofee.str.contains("end of loan", na=False))]
    if ins.empty and outs.empty:
        return full_df

    consumed: set[str] = set()      # 리그 내 이동으로 원 소속에서 빠질 선수(norm)
    relocated: list = []            # 목적팀으로 옮긴 실제 행
    synth: list = []                # 리그 밖 영입(이적료 근사)

    for _, r in ins.iterrows():
        dest = str(r.get("squad"))
        if dest not in valid_squads:
            continue
        nm = _norm(r.get("player"))
        src = adj[adj["_norm"] == nm]
        if not src.empty:
            row = src.iloc[0].copy()
            row["squad"] = dest
            relocated.append(row)
            consumed.add(nm)
        else:
            fee = pd.to_numeric(pd.Series([r.get("fee_eur")]), errors="coerce").iloc[0]
            if pd.notna(fee) and float(fee) > 0:
                new = {c: None for c in adj.columns}
                new.update({
                    "player": r.get("player"), "squad": dest, "_norm": nm,
                    "market_value_eur": float(fee), "minutes": _SYNTH_MINUTES,
                    "goals": 0, "assists": 0, "ss_rating": None,
                    "fl_group": _fl_from_pos(r.get("pos")), "pos": r.get("pos"),
                })
                synth.append(new)

    depart = {(str(r.get("squad")), _norm(r.get("player"))) for _, r in outs.iterrows()}

    def _keep(row) -> bool:
        if row["_norm"] in consumed:
            return False
        if (str(row["squad"]), row["_norm"]) in depart:
            return False
        return True

    base = adj[adj.apply(_keep, axis=1)]
    parts = [base]
    if relocated:
        parts.append(pd.DataFrame(relocated))
    if synth:
        parts.append(pd.DataFrame(synth))
    out = pd.concat(parts, ignore_index=True)
    return out.drop(columns=["_norm"], errors="ignore")
