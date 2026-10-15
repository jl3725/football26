"""팀 화면 데이터 점검 — 8개 리그 전 팀을 API 로 열어 '보이면 이상한' 조합을 찾는다(2026-10-15).

계기: Arsenal 화면에서 (1) 떠난 선수(Hincapié)가 벤치에도 있음 (2) 2위 팀 공격 출력 43(포지션 분류 오류)
(3) 세트피스 0 같은 원천 의심값. 한 팀씩 눈으로 보지 않고 전 팀을 규칙으로 훑는다.

검사
  departed_in_squad : 떠난 선수가 시즌 XI·최근 XI·벤치에 함께 나옴
  profile_vs_table  : 공격 출력 순위 ↔ 경기당 득점 순위, 실점 억제 순위 ↔ 경기당 실점 순위가 10계단 이상 어긋남
  profile_missing   : 시즌 프로필 축이 4개 미만(원천 미수집)
  recent_no_logo    : 최근 5경기 상대 로고 없음(우리 리그 밖 상대 — 정보성)
사용: python scripts/audit_team_pages.py [--league EPL] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import api.main as api  # noqa: E402
import datastore as ds  # noqa: E402
from leagues import LEAGUES  # noqa: E402


def _last(n: str) -> str:
    """이름 전체(악센트 제거·소문자) — 성만 비교하면 Wesley Fofana(잔류)와 David Datro Fofana(이적)를 같은 사람으로 봤다."""
    from unidecode import unidecode  # noqa: PLC0415
    return " ".join(unidecode(str(n)).lower().split())


def audit_league(c: TestClient, league: str) -> list[dict]:
    st = ds.read_table("standings", league=league)
    if st is None or st.empty:
        return []
    out: list[dict] = []
    g = st.set_index("squad")
    played = g["played"].clip(lower=1)
    gf_rank = (g["gf"] / played).rank(ascending=False, method="min")
    ga_rank = (g["ga"] / played).rank(ascending=True, method="min")
    for team in st.sort_values("rank")["squad"]:
        ov = c.get(f"/api/overview/{team}", params={"league": league})
        ts = c.get(f"/api/team-season/{team}", params={"league": league})
        lu = c.get(f"/api/lineup/{team}", params={"league": league})
        if ov.status_code != 200 or ts.status_code != 200:
            out.append({"league": league, "team": team, "check": "api_error", "detail": f"overview {ov.status_code} · season {ts.status_code}"})
            continue
        ov, ts = ov.json(), ts.json()
        # 1) 떠난 선수가 스쿼드에도
        if lu.status_code == 200:
            lj = lu.json()
            names = {_last(p["player"]) for blk in ("season", "recent") if lj.get(blk) for p in lj[blk]["placements"]}
            names |= {_last(b["player"]) for b in lj.get("bench", [])}
            both = [d["player"] for d in ov.get("departed", []) if _last(d["player"]) in names]
            if both:
                out.append({"league": league, "team": team, "check": "departed_in_squad", "detail": ", ".join(both)})
        # 2) 프로필 순위 ↔ 실제 득실 순위
        prof = {p["key"]: p for p in ts.get("profile", [])}
        for key, ref, label in (("attack_output_index", gf_rank, "공격 출력↔득점"), ("defense_output_index", ga_rank, "실점 억제↔실점")):
            p = prof.get(key)
            if p and team in ref.index and abs(p["rank"] - int(ref[team])) >= 10:
                out.append({"league": league, "team": team, "check": "profile_vs_table",
                            "detail": f"{label}: 지수 {p['value']}({p['rank']}위) vs 실제 {int(ref[team])}위"})
        if len(prof) < 4:
            out.append({"league": league, "team": team, "check": "profile_missing", "detail": f"축 {len(prof)}개: {list(prof)}"})
        # 3) 최근 경기 상대 로고
        for m in ts.get("recent", []):
            op = m["away"] if m["home"]["team"] == team else m["home"]
            if not op.get("logo"):
                out.append({"league": league, "team": team, "check": "recent_no_logo", "detail": op["team"]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    ap.add_argument("--json")
    a = ap.parse_args()
    c = TestClient(api.app)
    leagues = [a.league] if a.league else [lg for lg in LEAGUES if lg in set(ds.available_leagues())]
    rows: list[dict] = []
    for lg in leagues:
        r = audit_league(c, lg)
        rows += r
        kinds: dict[str, int] = {}
        for x in r:
            kinds[x["check"]] = kinds.get(x["check"], 0) + 1
        print(f"[{lg}] {kinds or '이상 없음'}", flush=True)
    for x in rows:
        if x["check"] != "recent_no_logo":
            print(f"  {x['league']:16} {x['team']:22} {x['check']:18} {x['detail']}")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    serious = [x for x in rows if x["check"] in ("departed_in_squad", "api_error")]
    return 1 if serious else 0


if __name__ == "__main__":
    raise SystemExit(main())
