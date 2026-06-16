"""
fl_to_slots.py — football-lineups 포지션 데이터를 player_slots_2025_2026.csv로 변환.

FL 약식명(B. Silva, Reijnde.) → FBref 풀네임 매칭 + 포메이션 슬롯 배정.

사용:
    python src/fl_to_slots.py "Manchester City"     # 단일 팀
    python src/fl_to_slots.py --all                 # 전 팀
    python src/fl_to_slots.py "Manchester City" --dry  # 결과만 출력
"""
from __future__ import annotations

import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
from unidecode import unidecode

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
DATA = ROOT / "data"

FL_CSV     = DATA / "fl_positions_2025_2026.csv"
PLAYERS    = DATA / "players_2025_2026.csv"
SLOTS_CSV  = DATA / "player_slots_2025_2026.csv"
FORMS_JSON = DATA / "team_formations.json"

# ─── 포지션 → 슬롯 우선순위 ──────────────────────────────────────────────────
# 두 단계 배정:
#   PASS-1: 포지션이 슬롯과 1:1 대응(GK/RB/LB/DM/ST)인 선수를 먼저 고정
#   PASS-2: CB → RCB/LCB, 나머지 미드 포지션 → 남은 미드 슬롯
SPECIFIC_MAP = {
    "GK":  "GK",
    "RB":  "RB",
    "LB":  "LB",
    "RWB": "RWB",
    "LWB": "LWB",
    "DM":  "CM",   # 4-1-X-Y에서 단일 피벗 슬롯은 CM
    "ST":  "ST",
}

# 슬롯 우선순위 (fl_pos → 선호 슬롯 목록, 좌/우 구분 전)
BASE_PREFS: dict[str, list[str]] = {
    "GK":  ["GK"],
    "CB":  ["RCB", "LCB", "CB"],
    "RB":  ["RB", "RWB", "RCB"],
    "LB":  ["LB", "LWB", "LCB"],
    "RWB": ["RWB", "RB"],
    "LWB": ["LWB", "LB"],
    "DM":  ["CM", "RDM", "LDM"],
    "BX":  ["RCM", "LCM", "CM", "RM", "LM"],   # 박스투박스
    "AM":  ["RCM", "LCM", "RM", "LM"],          # 공격형 미드
    "RM":  ["RM", "RCM"],
    "LM":  ["LM", "LCM"],
    "MF":  ["RCM", "CM", "LCM", "RM", "LM"],
    "RW":  ["RM", "RCM", "RW", "LM", "LCM"],     # 오른쪽 와이드 (+반대편 폴백)
    "LW":  ["LM", "LCM", "LW", "RM", "RCM"],     # 왼쪽 와이드 (+반대편 폴백)
    "WF":  ["RM", "LM", "RW", "LW", "RCM", "LCM"],
    "DF":  ["RCB", "LCB", "CB", "RB", "LB"],
    "FW":  ["ST", "RST", "LST", "RM", "LM", "RW", "LW"],
    "SS":  ["RCM", "LCM", "ST"],
}

RIGHT_SIDE = {"RB", "RWB", "RCB", "RST", "RM", "RW", "RDM", "RCM"}
LEFT_SIDE  = {"LB", "LWB", "LCB", "LST", "LM", "LW", "LDM", "LCM"}

# fl_group(해결된 실측 포지션) → 슬롯배정용 유효 fl_pos.
# fl_pos는 FL 1차 표기(예: O'Reilly=BX)지만, 멀티포지션은 FBref 출전시간으로
# 해결된 fl_group(O'Reilly=LB)이 진짜 주포지션 → 이를 배정 기준으로 쓴다.
GROUP_TO_POS: dict[str, str] = {
    "GK": "GK", "CB": "CB", "RB": "RB", "LB": "LB",
    "DM": "DM", "CM": "BX", "AM": "AM",
    "RW": "RW", "LW": "LW", "W": "WF", "ST": "ST",
}


# ─── 이름 정규화 ────────────────────────────────────────────────────────────
def norm(s: str) -> str:
    """엑센트 제거, 소문자, 캡틴/이적 접미사 제거, 후행 점 제거."""
    s = str(s)
    s = re.sub(r"\s*\(c\)\s*", " ", s)
    s = re.sub(r"\s*(in|out)\d{2}\w{3}.*$", "", s)
    s = unidecode(s).lower().strip()
    s = s.rstrip(".")
    s = re.sub(r"[^a-z0-9 '\-]", "", s).strip()
    return s


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


# ─── FL 약식명 → FBref 풀네임 매칭 ─────────────────────────────────────────
def match_name(fl_raw: str, fbs_names: list[str]) -> str | None:
    fn = norm(fl_raw)
    if not fn or fn in ("-", ""):
        return None

    tokens_fn = fn.split()
    last_fn   = tokens_fn[-1].rstrip(".")

    # "B. Silva" 또는 "M. Nunes" 스타일 감지
    init_m = re.match(r"^([a-z])\.?\s+(.+)$", fn)

    scored: list[tuple[float, str]] = []
    for fbs in fbs_names:
        nb      = norm(fbs)
        toks    = nb.split()
        last_nb = toks[-1]
        first_nb = toks[0] if len(toks) > 1 else ""

        # 초기+성 매칭 ("B. Silva" → Bernardo Silva)
        if init_m:
            init, rest = init_m.groups()
            rest = rest.rstrip(".")
            if first_nb.startswith(init) and (last_nb == rest or last_nb.startswith(rest)):
                scored.append((4.0, fbs))
                continue

        # 정확한 성 매칭
        if last_nb == last_fn:
            scored.append((3.0, fbs))
            continue

        # 성 접두어 매칭 (Reijnde. → Reijnders)
        if len(last_fn) >= 4 and last_nb.startswith(last_fn):
            scored.append((2.5, fbs))
            continue

        # 풀네임 안에 FL 이름이 포함 (복합성)
        if len(last_fn) >= 5 and last_fn in nb:
            scored.append((2.0, fbs))
            continue

        # 유사도 폴백
        s = max(_sim(fn, nb), _sim(last_fn, last_nb))
        if s > 0.72:
            scored.append((s, fbs))

    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]


# ─── 슬롯 우선순위 계산 (fl_pos2로 좌/우 편향) ──────────────────────────────
def slot_prefs(fl_pos: str, fl_pos2: str | float | None) -> list[str]:
    base = BASE_PREFS.get(fl_pos.upper(), ["CM"])
    raw  = fl_pos2 if (fl_pos2 and str(fl_pos2) != "nan") else ""
    p2   = str(raw).upper()

    if p2 in RIGHT_SIDE:
        # 오른쪽 슬롯 먼저
        right = [s for s in base if s in RIGHT_SIDE or s in ("GK", "ST", "CB", "CM")]
        left  = [s for s in base if s not in right]
        return right + left
    if p2 in LEFT_SIDE:
        left  = [s for s in base if s in LEFT_SIDE or s in ("GK", "ST", "CB", "CM")]
        right = [s for s in base if s not in left]
        return left + right

    # fl_pos 자체가 오른쪽 wide이면 wide 슬롯 먼저
    if fl_pos.upper() in ("RW", "RM"):
        return [s for s in base if "R" in s] + [s for s in base if "R" not in s]
    if fl_pos.upper() in ("LW", "LM"):
        return [s for s in base if "L" in s] + [s for s in base if "L" not in s]

    return base


# ─── 슬롯 배정 ──────────────────────────────────────────────────────────────
def formation_slots_list(formation: str) -> list[str]:
    """포메이션 → 11슬롯 목록."""
    sys.path.insert(0, str(SRC))
    from team_analysis import formation_slots  # noqa: PLC0415
    return formation_slots(formation)


def assign_slots(
    fl_players: list[dict],
    formation: str,
    fbs_minutes: dict[str, int],
) -> list[tuple[str, dict]]:  # [(slot, player_dict)]
    """두 패스 슬롯 배정 — DM/RB/LB/GK/ST를 먼저 고정, 나머지 순서대로."""
    all_slots = formation_slots_list(formation)
    available = list(all_slots)  # 남은 슬롯

    def starts_int(p: dict) -> int:
        s = str(p.get("starts", "-"))
        return int(s) if s.isdigit() else -1

    def key(p: dict) -> tuple:
        return (starts_int(p), fbs_minutes.get(p.get("_fbs", ""), 0))

    result: list[tuple[str, dict]] = []
    used_names: set[str] = set()

    def _take(slot: str, p: dict) -> None:
        available.remove(slot)
        used_names.add(p.get("_fbs", p["fl_name"]))
        result.append((slot, p))

    def eff(p: dict) -> str:
        # fl_group 해결 포지션(_eff_pos) 우선, 없으면 원시 fl_pos
        return str(p.get("_eff_pos") or p.get("fl_pos") or "").upper()

    # PASS 1 — 포지션이 슬롯과 1:1인 선수 고정 (DM, RB, LB, GK, ST ...)
    for pos, target_slot in SPECIFIC_MAP.items():
        if target_slot not in available:
            continue
        cands = [
            p for p in fl_players
            if eff(p) == pos
            and p.get("_fbs") not in used_names
        ]
        if not cands:
            continue
        best = max(cands, key=key)
        _take(target_slot, best)

    # PASS 2 — 남은 선수 중 CB → RCB/LCB, 그 외 → 남은 미드 슬롯
    remaining = sorted(
        [p for p in fl_players if p.get("_fbs") not in used_names],
        key=key, reverse=True,
    )
    for p in remaining:
        if not available:
            break
        prefs = slot_prefs(eff(p), p.get("fl_pos2", "") or "")
        for slot in prefs:
            if slot in available:
                _take(slot, p)
                break

    return result


# ─── 팀 처리 ────────────────────────────────────────────────────────────────
def process_team(
    team: str,
    fl_df: pd.DataFrame,
    fbs_df: pd.DataFrame,
    dry: bool = False,
) -> list[dict] | None:
    t_fl = fl_df[fl_df["squad"] == team]
    if t_fl.empty:
        print(f"  [{team}] FL 데이터 없음")
        return None

    formation = t_fl["formation"].iloc[0]
    fbs_team  = fbs_df[fbs_df["squad"] == team]
    if fbs_team.empty:
        print(f"  [{team}] FBref 데이터 없음")
        return None

    fbs_names   = fbs_team["player"].tolist()
    fbs_minutes = dict(zip(fbs_team["player"], fbs_team["minutes"].fillna(0).astype(int)))
    fbs_pos_map = dict(zip(fbs_team["player"], fbs_team["pos"].fillna("")))

    # FL 선수 목록에 매칭된 FBref 이름 붙이기
    players = []
    unmatched = []
    for _, row in t_fl.iterrows():
        p = row.to_dict()
        fbs_match = match_name(p["fl_name"], fbs_names)
        p["_fbs"] = fbs_match or ""
        # fl_group으로 해결된 실측 주포지션 → 슬롯배정용 _eff_pos
        fbs_pos = fbs_pos_map.get(fbs_match, "") if fbs_match else ""
        grp = compute_fl_group(str(p.get("fl_pos") or ""), p.get("fl_pos2"), fbs_pos)
        p["_grp"] = grp
        p["_eff_pos"] = GROUP_TO_POS.get(grp, str(p.get("fl_pos") or "").upper())
        if not fbs_match:
            unmatched.append(p["fl_name"])
        players.append(p)

    if unmatched:
        print(f"  [{team}] 매칭 실패 {len(unmatched)}명: {unmatched[:8]}")

    # 슬롯 배정
    assignment = assign_slots(players, formation, fbs_minutes)

    rows = []
    for slot, p in assignment:
        fbs_name = p.get("_fbs") or ""
        nb = fbs_df[fbs_df["player"] == fbs_name]
        # FL 'starts'는 사실 전 대회(EPL+챔스+컵) 출전 경기수(선발+교체 포함).
        # 선발 수가 아님 → apps(=appearances)로 저장. 슬롯 내 주전 판단에만 사용.
        starts_val = str(p.get("starts", "-"))
        rows.append({
            "squad":     team,
            "player":    fbs_name,
            "norm_key":  norm(fbs_name),
            "slot":      slot,
            "apps":      int(starts_val) if starts_val.isdigit() else 0,
            "slot_dist": 1.0,
            "formation": formation,
            "sofa_id":   "",
            "number":    p.get("fl_number", ""),
        })

    if dry:
        lines = [f"  [{team}] formation={formation}  XI {len(rows)} players"]
        for r in rows:
            p = r['player'].encode('ascii', 'replace').decode()
            lines.append(f"    {r['slot']:6} {p:32} apps={r['apps']}")
        print("\n".join(lines))
    return rows


# ─── 저장 ───────────────────────────────────────────────────────────────────
def save_slots(team: str, rows: list[dict], formation: str) -> None:
    df_new = pd.DataFrame(rows)
    if SLOTS_CSV.exists():
        old = pd.read_csv(SLOTS_CSV)
        old = old[(old["squad"] != team) | (old["formation"] != formation)]
        df_new = pd.concat([old, df_new], ignore_index=True)
    df_new.to_csv(SLOTS_CSV, index=False, encoding="utf-8")
    print(f"  [OK] {SLOTS_CSV.name} - {team} {len(rows)} slots")


def update_formations_json(team: str, formation: str) -> None:
    data = json.loads(FORMS_JSON.read_text(encoding="utf-8")) if FORMS_JSON.exists() else {}
    entry = data.get(team, {})
    if isinstance(entry, str):
        entry = {"main": entry, "sub": None}
    entry["main"] = formation
    data[team] = entry
    FORMS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [formation] {team} -> {formation}")


# FBref broad group (출전시간 순서 정렬 기준)
_FL_FBS: dict[str, str] = {
    "GK": "GK",
    "CB": "DF", "RB": "DF", "LB": "DF", "RWB": "DF", "LWB": "DF", "DF": "DF",
    "DM": "MF", "BX": "MF", "CM": "MF", "AM": "MF", "RM": "MF", "LM": "MF", "MF": "MF",
    "RW": "FW", "LW": "FW", "WF": "FW", "SS": "FW", "ST": "FW", "FW": "FW",
}
_RIGHT_WIDE = {"RW", "RM", "RWB", "RB"}
_LEFT_WIDE  = {"LW", "LM", "LWB", "LB"}


# ─── FL 그룹 계산 ─────────────────────────────────────────────────────────────
def compute_fl_group(fl_pos: str, fl_pos2: str | float | None,
                     fbs_pos: str = "") -> str:
    """FL 포지션 → 세분화 유사도 그룹.

    Groups: GK / CB / RB / LB / DM / CM / AM / RW / LW / W / ST

    처리 순서:
    1) fl_pos2 존재 + FBref pos 순서(=출전시간)로 어느 포지션이 주인지 결정
       (예: BX/LB + FBref="DF,MF" → DF 먼저 → LB가 주 → p1 교체)
    2) AM + pos2=wide → 방향성 wide (Rogers=AM/LW → LW, Odegaard=AM/RW → RW)
    3) AM + FBref[0]=FW → ST (Havertz=FW 기록 → ST)
    4) WF + pos2로 방향 결정, 없으면 W(비방향)
    """
    p1 = str(fl_pos or "").strip().upper()
    raw2 = fl_pos2 if (fl_pos2 and str(fl_pos2) != "nan") else ""
    p2 = str(raw2).strip().upper()

    # ── Step 1: FBref pos로 주 포지션 교체 ──────────────────────────────────
    if p2 and fbs_pos:
        fbs_parts = [x.strip().upper() for x in str(fbs_pos).split(",")]
        g1 = _FL_FBS.get(p1, "")
        g2 = _FL_FBS.get(p2, "")
        if g1 and g2 and g1 != g2:
            idx1 = fbs_parts.index(g1) if g1 in fbs_parts else 999
            idx2 = fbs_parts.index(g2) if g2 in fbs_parts else 999
            if idx2 < idx1:
                p1, p2 = p2, p1

    # ── Step 2 & 3: 포지션 → 그룹 매핑 ─────────────────────────────────────
    if p1 == "GK":                  return "GK"
    if p1 in ("CB", "DF"):         return "CB"
    if p1 in ("RB", "RWB"):        return "RB"
    if p1 in ("LB", "LWB"):        return "LB"
    if p1 == "DM":                  return "DM"
    if p1 in ("BX", "CM", "MF"):   return "CM"

    if p1 == "AM":
        # FBref가 FW를 먼저 기록 → 실질적 FW 역할 (Havertz)
        if fbs_pos:
            fbs_parts = [x.strip().upper() for x in str(fbs_pos).split(",")]
            if fbs_parts and fbs_parts[0] == "FW":
                return "ST"
        # pos2 방향으로 wide 그룹 결정 (Rogers=AM/LW → LW, Odegaard=AM/RW → RW)
        if p2 in _RIGHT_WIDE:       return "RW"
        if p2 in _LEFT_WIDE:        return "LW"
        return "AM"                 # 순수 중앙 AM (Foden, Buendia 등)

    if p1 == "WF":
        if p2 in _RIGHT_WIDE:       return "RW"
        if p2 in _LEFT_WIDE:        return "LW"
        return "W"                  # 방향 미확정 (Savinho 등)

    if p1 in ("RW", "RM"):         return "RW"
    if p1 in ("LW", "LM"):         return "LW"
    if p1 in ("ST", "FW", "SS"):   return "ST"
    return "OTH"


# ─── 선수 CSV에 FL 포지션 주입 ───────────────────────────────────────────────
def annotate_players_fl(players_path: Path = PLAYERS) -> None:
    """players_2025_2026.csv에 fl_pos / fl_pos2 / fl_group 컬럼을 추가/갱신.

    FL 약식명 → FBref 풀네임 매칭 후 팀+선수 기준으로 join.
    매칭 실패 선수는 기존 값(또는 빈 문자열) 유지.
    """
    fl_df  = pd.read_csv(FL_CSV)
    fbs_df = pd.read_csv(players_path)

    # (squad, fbs_name) → (fl_pos, fl_pos2, fl_group) 딕셔너리 구축
    mapping: dict[tuple[str, str], tuple[str, str, str]] = {}

    for team in fl_df["squad"].unique():
        t_fl  = fl_df[fl_df["squad"] == team]
        t_fbs = fbs_df[fbs_df["squad"] == team]
        fbs_names = t_fbs["player"].tolist()

        # FBref pos 조회용 딕셔너리 (player → pos)
        fbs_pos_map = dict(zip(t_fbs["player"], t_fbs["pos"].fillna("")))

        for _, row in t_fl.iterrows():
            fl_name = row["fl_name"]
            matched = match_name(str(fl_name), fbs_names)
            if not matched:
                continue
            fp1 = str(row.get("fl_pos") or "").strip()
            fp2 = str(row.get("fl_pos2") or "").strip()
            fp2 = "" if fp2 == "nan" else fp2
            fbs_pos = fbs_pos_map.get(matched, "")
            grp = compute_fl_group(fp1, fp2, fbs_pos)
            mapping[(team, matched)] = (fp1, fp2, grp)

    # 컬럼 추가/갱신
    fl_pos_vals, fl_pos2_vals, fl_group_vals = [], [], []
    for _, r in fbs_df.iterrows():
        key = (r["squad"], r["player"])
        if key in mapping:
            p1, p2, grp = mapping[key]
            fl_pos_vals.append(p1)
            fl_pos2_vals.append(p2)
            fl_group_vals.append(grp)
        else:
            fl_pos_vals.append(fbs_df.get("fl_pos", pd.Series()).get(_, ""))
            fl_pos2_vals.append(fbs_df.get("fl_pos2", pd.Series()).get(_, ""))
            fl_group_vals.append(fbs_df.get("fl_group", pd.Series()).get(_, ""))

    fbs_df["fl_pos"]   = fl_pos_vals
    fbs_df["fl_pos2"]  = fl_pos2_vals
    fbs_df["fl_group"] = fl_group_vals

    fbs_df.to_csv(players_path, index=False, encoding="utf-8")
    matched_count = sum(1 for v in fl_group_vals if v)
    print(f"[annotate] {players_path.name}: {matched_count}/{len(fbs_df)} rows annotated")


# ─── main ───────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    dry = "--dry" in args
    if dry:
        args.remove("--dry")
    all_teams_flag = "--all" in args
    if all_teams_flag:
        args.remove("--all")
    annotate_only = "--annotate" in args
    if annotate_only:
        args.remove("--annotate")

    if annotate_only:
        annotate_players_fl()
        return 0

    fl_df  = pd.read_csv(FL_CSV)
    fbs_df = pd.read_csv(PLAYERS)

    if all_teams_flag:
        teams = fl_df["squad"].unique().tolist()
    elif args:
        teams = args
    else:
        print("Usage: python src/fl_to_slots.py \"Manchester City\" [--dry]")
        print("       python src/fl_to_slots.py --annotate  (fl_group 컬럼 주입)")
        return 1

    for team in teams:
        print(f"\n{'='*50}")
        print(f" {team}")
        t_fl = fl_df[fl_df["squad"] == team]
        formation = t_fl["formation"].iloc[0] if not t_fl.empty else None
        rows = process_team(team, fl_df, fbs_df, dry=dry)
        if rows and not dry:
            save_slots(team, rows, formation)
            update_formations_json(team, formation)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
