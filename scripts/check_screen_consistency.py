"""
화면 간 일치 점검 — 같은 숫자·같은 대상이 화면마다 다르게 나오면 매일 잡아 watchdog 이 알린다(사람이 화면을 보기 전에).

2026-10-20 대시보드 전면 점검에서 사람이 찾은 문제들을 규칙으로 바꾼 것이다(손으로 고친 값 없이, 전 리그·전 팀에 같은 규칙):
  1. season_log   선수 헤더(리그 분·골·도움) = SEASON LOG 리그 줄       (벨기에 리그 도움 0건·Vanaken 2A/0A)
  2. team_xg      Overview 경기당 xG = Analytics 리그 백분위의 xG       (1.71 vs 1.81)
  3. transfers    이적료 없는 IN(승격형)과 OUT 에 같은 선수가 없음        (2군 승격 후 판 선수 — 바이백·재판매는 정상)
  4. opponents    다음 경기 상대가 우리 8개 리그 팀이면 리그·순위가 붙음  (Paris Saint-Germain 연결 실패)
  5. leaders      TEAM LEADERS 90분당 1위가 최소 출전을 넘김             (10분 뛴 키패스 1위)
결과: data/eval/screen_audit.json (daily_data, watchdog 'screen' 점검이 읽음)

    python scripts/check_screen_consistency.py            # 표본(리그별 출전 상위 선수 4명·팀 4개)
    python scripts/check_screen_consistency.py --full     # 전 팀
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
OUT = ROOT / "data" / "eval" / "screen_audit.json"


def run(full: bool = False) -> dict:
    import pandas as pd

    import api.main as m
    from leagues import LEAGUES

    issues: list[dict] = []
    checked = {"season_log": 0, "team_xg": 0, "transfers": 0, "opponents": 0, "leaders": 0}
    ours = set(m._club_names())

    def bad(kind, team, detail):
        issues.append({"kind": kind, "team": team, "detail": detail})

    for lg in LEAGUES:
        try:
            pf = m._pf(lg)
            st = m.ds.read_table("standings", league=lg)
        except Exception:  # noqa: BLE001
            continue
        if pf is None or st is None or st.empty:
            continue
        teams = list(st.sort_values("rank")["squad"].astype(str))
        sample = teams if full else teams[:2] + teams[-2:]          # 위·아래(빅클럽·승격팀)
        mins = pd.to_numeric(pf["minutes"], errors="coerce").fillna(0)
        # 1) 선수 헤더 = SEASON LOG 리그 줄
        for _, r in pf.assign(_m=mins).sort_values("_m", ascending=False).head(12 if full else 4).iterrows():
            try:
                d = m.player_detail(str(r["squad"]), str(r["player"]), lg)
            except Exception:  # noqa: BLE001
                continue
            lig = [b for b in (d.get("season_log") or {}).get("by_comp", []) if b["comp"] == "리그"]
            if not lig:
                continue
            checked["season_log"] += 1
            b = lig[0]
            if (b["goals"], b["assists"]) != (d["goals"], d["assists"]) or abs(b["minutes"] - d["minutes"]) > 2:
                bad("season_log", r["squad"], f"{r['player']} 헤더 {d['minutes']}′ {d['goals']}G {d['assists']}A ≠ "
                                              f"SEASON LOG {b['minutes']}′ {b['goals']}G {b['assists']}A")
        for team in sample:
            # 2) 팀 xG — Overview vs Analytics
            try:
                ts = m.team_season(team, lg)
                tt = m.team_trends(team, lg)
                axg = next((p.get("value") for p in tt.get("percentiles", []) if (p.get("key") or "") == "xg"), None)
                if ts.get("xg_pg") is not None and axg is not None:
                    checked["team_xg"] += 1
                    if abs(float(ts["xg_pg"]) - float(axg)) > 0.02:
                        bad("team_xg", team, f"Overview {ts['xg_pg']} ≠ Analytics {axg}")
            except Exception:  # noqa: BLE001
                pass
            # 3) IN·OUT 중복
            try:
                tr = m.transfers(team, lg)
                # 이적료 없는 IN(승격형)이 OUT 과 겹칠 때만 문제 — 바이백(€3.45M) 후 재판매(€12M) 같은 실제 거래는 둘 다 맞다
                free_in = {x["player"] for x in tr["in"] if not x.get("fee_eur") and str(x.get("fee_text") or "").strip() in ("-", "")}
                both = free_in & {x["player"] for x in tr["out"]}
                checked["transfers"] += 1
                if both:
                    bad("transfers", team, "IN·OUT 동시: " + ", ".join(sorted(both)[:4]))
            except Exception:  # noqa: BLE001
                pass
            # 4) 다음 경기 상대 연결
            try:
                for fx in m.team_fixtures(team, lg, 3)["next"]:
                    checked["opponents"] += 1
                    for side in ("home", "away"):
                        t = fx[side]
                        if t["team"] in ours and not t.get("league"):
                            bad("opponents", team, f"{fx['date']} {t['team']} 리그 연결 안 됨")
            except Exception:  # noqa: BLE001
                pass
            # 5) 리더 90분당 최소 출전
            try:
                ov = m.overview(team, lg)
                floor = max(180, m._mm(1200, lg))
                byname = dict(zip(pf.loc[pf["squad"] == team, "player"].astype(str), mins[pf["squad"] == team]))
                for x in ov.get("leaders", []):
                    if "/90" in x["label"]:
                        checked["leaders"] += 1
                        if byname.get(x["player"], 0) < floor:
                            bad("leaders", team, f"{x['label']} {x['player']} {int(byname.get(x['player'], 0))}′ < {int(floor)}′")
            except Exception:  # noqa: BLE001
                pass
    return {"date": dt.date.today().isoformat(), "checked": checked, "issues": issues}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = argv if argv is not None else sys.argv[1:]
    res = run(full="--full" in args)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[screen] 점검 " + " · ".join(f"{k} {v}" for k, v in res["checked"].items()) + f" · 문제 {len(res['issues'])}")
    for x in res["issues"][:20]:
        print(f"  ✗ {x['kind']} {x['team']}: {x['detail']}")
    return 1 if "--check" in args and res["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
