"""선수 포지션 프로필 — 주포지션 · 2/3포지션을 '실제로 선 자리'로 정한다(2026-10-15).

계기: 스쿼드 뎁스 차트·Best XI 빌더가 Transfermarkt 주포지션 하나(또는 수비/중원/공격 라인)만 써서
  Hincapié(실제로는 주로 LB, 가끔 CB)가 CB 로만, Calafiori(LB)가 RB 칸에 들어갔다.

방법
  1) ESPN 라인업(선발) — 경기마다 포메이션을 슬롯으로 배정(team_analysis.espn_assign_slots)하고
     슬롯을 포메이션 맥락으로 10개 역할로 바꾼다: GK·LB·CB·RB·DM·CM·AM·LW·RW·ST
     (4-2-3-1 의 2선 좌우 = LW/RW, 가운데 = AM · 3백의 윙 미드 = LB/RB 윙백 · 단일 피벗 = DM)
  2) 이번 시즌 선발 1.0 + 지난 시즌 선발 0.5 가중(이적생은 전 소속 리그 파일에서 이름으로 찾는다)
  3) 선발 3회(가중) 이상이면 가장 많이 선 역할 = 주포지션, 20%+ 또는 3회+ = 2·3포지션
     부족하면 Transfermarkt 주포지션. TM 포지션이 데이터와 다르면 2포지션으로 붙인다.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache

import pandas as pd
from unidecode import unidecode

import team_analysis as ta

ROLES = ["GK", "LB", "CB", "RB", "DM", "CM", "AM", "LW", "RW", "ST"]
ROLE_KO = {"GK": "골키퍼", "LB": "레프트백", "CB": "센터백", "RB": "라이트백", "DM": "수비형MF", "CM": "중앙MF",
           "AM": "공격형MF", "LW": "좌측 윙", "RW": "우측 윙", "ST": "스트라이커"}
LINE_OF = {"GK": "GK", "LB": "DEF", "CB": "DEF", "RB": "DEF", "DM": "MID", "CM": "MID", "AM": "MID",
           "LW": "ATT", "RW": "ATT", "ST": "ATT"}

_TM_ROLE = {"goalkeeper": "GK", "centre-back": "CB", "left-back": "LB", "right-back": "RB",
            "defensive midfield": "DM", "central midfield": "CM", "attacking midfield": "AM",
            "left winger": "LW", "right winger": "RW", "left midfield": "LW", "right midfield": "RW",
            "centre-forward": "ST", "second striker": "AM"}


def norm_name(n) -> str:
    return _norm_name(str(n or ""))


@lru_cache(maxsize=131072)        # 순수 함수
def _norm_name(n: str) -> str:
    return " ".join(unidecode(n).lower().replace("-", " ").split())


def tm_role(tm_position) -> str | None:
    return _TM_ROLE.get(str(tm_position or "").strip().lower())


def slot_roles(formation: str) -> list[str]:
    """formation_slots(formation) 와 같은 순서의 역할 목록."""
    try:
        parts = [int(x) for x in str(formation).split("-")]
    except ValueError:
        return []
    nb = len(parts)
    back3 = parts[0] == 3
    roles = ["GK"]
    for bi, size in enumerate(parts):
        kind = "D" if bi == 0 else ("F" if bi == nb - 1 else "M")
        labels = ta.slot_labels(size, kind)
        for lab in labels:
            if kind == "D":
                roles.append("RB" if lab in ("RB", "RWB") else "LB" if lab in ("LB", "LWB") else "CB")
            elif kind == "F":
                roles.append("RW" if lab == "RW" else "LW" if lab == "LW" else "ST")
            else:
                high = nb >= 4 and bi == nb - 2           # 2선(4-2-3-1 의 3, 3-4-2-1 의 2, 4-4-1-1 의 1)
                deep = nb >= 4 and bi == 1                 # 수비형 줄(4-2-3-1 의 2, 4-1-4-1 의 1)
                if lab in ("RM", "LM"):
                    if back3 and not high:
                        roles.append("RB" if lab == "RM" else "LB")      # 3백의 윙 미드 = 윙백
                    else:
                        roles.append("RW" if lab == "RM" else "LW")
                elif high:
                    if size == 3:
                        roles.append({"RCM": "RW", "LCM": "LW"}.get(lab, "AM"))
                    elif size >= 4:
                        roles.append("CM")                 # 4-1-4-1 의 두 중앙 = 8번(CM)
                    else:
                        roles.append("AM")
                elif deep and size <= 2:
                    roles.append("DM")
                elif size == 1:
                    roles.append("DM")
                elif size == 3 and lab == "CM" and ta.display_slot("CM", formation) == "DM":
                    roles.append("DM")
                elif lab in ("RDM", "LDM"):
                    roles.append("DM")
                else:
                    roles.append("CM")
    return roles


def match_roles(espn_positions: list[str], formation: str) -> list[str | None]:
    """한 경기 선발 11명의 ESPN 위치 → 역할(같은 순서)."""
    try:
        slots = ta.espn_assign_slots([str(p) for p in espn_positions], formation)
        fslots = ta.formation_slots(formation)
    except Exception:  # noqa: BLE001
        return [None] * len(espn_positions)
    roles = slot_roles(formation)
    if len(roles) != len(fslots):
        return [None] * len(espn_positions)
    # 같은 슬롯 이름이 두 번 나오는 포메이션(4-3-1-2 의 CM)은 나온 순서대로 짝지음
    pool: dict[str, list[str]] = defaultdict(list)
    for s, r in zip(fslots, roles):
        pool[s].append(r)
    used: Counter = Counter()
    out = []
    for s in slots:
        if s is None or s not in pool:
            out.append(None)
            continue
        i = min(used[s], len(pool[s]) - 1)
        used[s] += 1
        out.append(pool[s][i])
    return out


def role_counts(lineups: list[pd.DataFrame], weights: list[float]) -> dict[str, Counter]:
    """ESPN 라인업 표들(시즌별) → {정규화 이름: Counter(역할→가중 선발 수)}."""
    acc: dict[str, Counter] = defaultdict(Counter)
    for df, w in zip(lineups, weights):
        if df is None or df.empty or "espn_pos" not in df.columns:
            continue
        st = df[pd.to_numeric(df["starter"], errors="coerce") == 1]
        for (_eid, _sq), g in st.groupby(["event_id", "squad"]):
            if len(g) < 10:
                continue
            g = g.sort_values("formation_place") if "formation_place" in g.columns else g
            form = str(g["formation"].iloc[0])
            for name, role in zip(g["player"], match_roles(g["espn_pos"].tolist(), form)):
                if role:
                    acc[norm_name(name)][role] += w
    return acc


def lookup(counts: dict, name) -> Counter | None:
    """이름으로 역할 집계 찾기 — 전체 이름이 다르면(ESPN 'Gabriel' vs 'Gabriel Magalhães') 성+이름 첫 글자로 한 명일 때만."""
    k = norm_name(name)
    if k in counts:
        return counts[k]
    t = k.split()
    if not t:
        return None
    hits = [v for kk, v in counts.items() if kk.split() and kk.split()[-1] == t[-1] and kk.split()[0][:1] == t[0][:1]]
    return hits[0] if len(hits) == 1 else None


def profile(counts: Counter | None, tm_position=None) -> dict:
    """역할 집계 + TM 포지션 → {"primary", "secondary": [...], "roles": {...}, "starts": n, "source"}."""
    c = Counter(counts or {})
    tot = sum(c.values())
    tmr = tm_role(tm_position)
    if tot >= 3:
        ranked = [r for r, _ in c.most_common()]
        primary, src = ranked[0], "lineups"
    else:
        primary, src = (tmr or (c.most_common(1)[0][0] if c else None)), "tm" if tmr else "lineups"
    sec = []
    for r, n in c.most_common():
        if r != primary and (n >= 3 or (tot and n / tot >= 0.2)):
            sec.append(r)
    if tmr and tmr != primary and tmr not in sec:
        sec.append(tmr)                     # 데이터상 주포지션과 다르면 TM 포지션을 2포지션으로
    return {"primary": primary, "secondary": sec[:2], "roles": {r: round(n, 1) for r, n in c.most_common()},
            "starts": round(tot, 1), "source": src}


# 빌더·뎁스용 적합도 — 주포지션 1.0, 2포지션 0.95, 비슷한 자리 0.85, 같은 라인 0.75, 그 외 0.55
_NEAR = {"LB": {"CB", "LW"}, "RB": {"CB", "RW"}, "CB": {"LB", "RB", "DM"}, "DM": {"CM", "CB"}, "CM": {"DM", "AM"},
         "AM": {"CM", "LW", "RW", "ST"}, "LW": {"RW", "AM", "ST", "LB"}, "RW": {"LW", "AM", "ST", "RB"},
         "ST": {"AM", "LW", "RW"}, "GK": set()}


def fit(prof: dict, role: str) -> float:
    if not prof or not prof.get("primary"):
        return 0.55
    p = prof["primary"]
    if role == p:
        return 1.0
    if role in prof.get("secondary", []):
        return 0.95
    if role == "GK" or p == "GK":
        return 0.2
    if role in _NEAR.get(p, set()):
        return 0.85
    return 0.75 if LINE_OF.get(role) == LINE_OF.get(p) else 0.55
