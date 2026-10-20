"""
THIS WEEK — 감독용 한 블록(Overview 맨 위): 이번 주 경기 · 양 팀 결장 · 결장 반영 예상 XI · 로테이션 부담.

  pick_xi       최근 3경기 최빈 XI(전 대회)에서 결장 선수 자리를 메운다 — 빠진 선수 본인의 세부 포지션(TM, 예: Right Winger → W)
                같은 후보 중 OVR 최고 → 슬롯 세부 포지션 → 같은 라인 순. 4-2-3-1 의 RCM 칸에 선 윙어가 빠지면 윙어로.
  full_streak   가장 최근 경기부터 연속 풀타임(85′+) 경기 수
  rotation      최근 14일 출전 분(전 대회) 270′+ · 연속 풀타임 → 부담 high(360′+ 또는 4연속)·mid
"""
from __future__ import annotations

FULL_MIN = 85


def pick_xi(placements: list[dict], absent: dict, pool: list[dict], norm, own_bucket: dict | None = None,
            slot_bucket=None) -> tuple[list[dict], list[dict]]:
    """placements = [{slot, player, kind, ovr, photo, x, y}], absent = {정규화 이름: {injury, until}},
    pool = [{player, ovr, bucket, line, photo}](스쿼드 — 결장·떠난 선수 제외 전), own_bucket = {정규화 이름: 세부 버킷}.
    → (XI, 바뀐 자리 [{slot, out, in, reason}])."""
    own_bucket = own_bucket or {}
    used = {norm(p["player"]) for p in placements if norm(p["player"]) not in absent}
    cands = [c for c in pool if norm(c["player"]) not in absent and norm(c["player"]) not in used]
    xi, changes = [], []
    for p in placements:
        k = norm(p["player"])
        if k not in absent:
            xi.append({**p, "changed": False})
            continue
        targets = [own_bucket.get(k), slot_bucket(p["slot"]) if slot_bucket else None]
        pick = None
        for tb in [t for t in targets if t]:
            same = [c for c in cands if c.get("bucket") == tb]
            if same:
                pick = max(same, key=lambda c: c.get("ovr") or 0)
                break
        if pick is None:
            same = [c for c in cands if c.get("line") == p.get("kind")]
            pick = max(same, key=lambda c: c.get("ovr") or 0) if same else None
        info = absent[k]
        if pick is None:
            xi.append({**p, "changed": True, "out": p["player"], "player": "—", "ovr": None, "photo": "", "injured": True})
            changes.append({"slot": p["slot"], "out": p["player"], "in": None, "reason": info.get("injury") or "결장"})
            continue
        cands.remove(pick)
        xi.append({**p, "player": pick["player"], "ovr": pick.get("ovr"), "photo": pick.get("photo", ""),
                   "changed": True, "out": p["player"]})
        changes.append({"slot": p["slot"], "out": p["player"], "in": pick["player"], "reason": info.get("injury") or "결장",
                        "until": info.get("until") or "", "ovr_out": p.get("ovr"), "ovr_in": pick.get("ovr")})
    return xi, changes


def full_streak(rows: list[dict]) -> int:
    """rows = [{date, minutes}] 한 선수의 경기(아무 순서) → 최근부터 연속 풀타임 수."""
    n = 0
    for r in sorted(rows, key=lambda r: str(r.get("date")), reverse=True):
        try:
            m = float(r.get("minutes") or 0)
        except (TypeError, ValueError):
            m = 0
        if m >= FULL_MIN:
            n += 1
        else:
            break
    return n


def rotation(load: list[tuple[str, int]], streaks: dict[str, int], ovr_of: dict[str, int] | None = None,
             norm=lambda s: s) -> list[dict]:
    """[(선수, 14일 출전 분)] + {선수: 연속 풀타임} → 부담 목록(분 많은 순)."""
    out = []
    for name, mins in load:
        st = int(streaks.get(name, 0))
        level = "high" if mins >= 360 or st >= 4 else "mid"
        out.append({"player": name, "minutes14": int(mins), "full_streak": st, "level": level,
                    "ovr": (ovr_of or {}).get(norm(name))})
    return sorted(out, key=lambda x: (-x["minutes14"], -x["full_streak"]))
