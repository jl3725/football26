"""
화면 간 일치 점검 — 같은 숫자·같은 대상이 화면마다 다르게 나오면 매일 잡아 watchdog 이 알린다(사람이 화면을 보기 전에).

2026-10-20 대시보드 전면 점검에서 사람이 찾은 문제들을 규칙으로 바꾼 것이다(손으로 고친 값 없이, 전 리그·전 팀에 같은 규칙):
  1. season_log   선수 헤더(리그 분·골·도움) = SEASON LOG 리그 줄       (벨기에 리그 도움 0건·Vanaken 2A/0A)
  2. team_xg      Overview 경기당 xG = Analytics 리그 백분위의 xG       (1.71 vs 1.81)
  3. transfers    이적료 없는 IN(승격형)과 OUT 에 같은 선수가 없음        (2군 승격 후 판 선수 — 바이백·재판매는 정상)
  4. opponents    다음 경기 상대가 우리 8개 리그 팀이면 리그·순위가 붙음  (Paris Saint-Germain 연결 실패)
  5. leaders      TEAM LEADERS 90분당 1위가 최소 출전을 넘김             (10분 뛴 키패스 1위)
  7. injury_return '부상 복귀' 신호(Inbox·Signals)인데 지금도 결장 명단에 있음 — 아직 안 돌아온 선수(살리바, 2026-11-03)
  6. heatmap_side 화면 히트맵(공격 →, 위 = 왼쪽)의 좌우 = 이번 시즌 라인업 좌우(ESPN L*·R* 4선발+, 75%+ 한쪽)
                  (2026-11-03 사용자 '라이스·외데고르 히트맵이 같은 곳' — 라이스가 이번 시즌 RM 이라 맞았다. 214명 대조 반대 0명)
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


def _norm(name) -> str:
    import positions as ps  # noqa: PLC0415
    return ps.norm_name(name)


def _lineup_sides(lg: str) -> dict:
    """{(팀, 정규화 이름): 'L'|'R'} — 이번 시즌 리그 선발 위치(ESPN L*·R*)가 4경기 이상, 75% 넘게 한쪽인 선수."""
    from collections import Counter

    import pandas as pd

    from leagues import data_path
    from player_names import read_lineup_csv
    path = data_path("espn_lineups", lg)
    if not path.exists():
        return {}
    lu = read_lineup_csv(path, ["squad", "player", "starter", "espn_pos"])
    lu = lu[pd.to_numeric(lu["starter"], errors="coerce") == 1]
    out = {}
    for (sq, pl), g in lu.groupby(["squad", "player"]):
        c = Counter("L" if str(p).startswith("L") else "R" if str(p).startswith("R") else "C" for p in g["espn_pos"])
        n = sum(c.values())
        side = max(("L", "R"), key=lambda x: c[x])
        if n >= 4 and c[side] / n >= 0.75:
            out[(str(sq), _norm(pl))] = side
    return out


def run(full: bool = False) -> dict:
    import pandas as pd

    import api.main as m
    from leagues import LEAGUES

    issues: list[dict] = []
    checked = {"season_log": 0, "team_xg": 0, "transfers": 0, "opponents": 0, "leaders": 0, "heatmap_side": 0,
               "injury_return": 0}
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
        # 7) '부상 복귀'인데 지금도 결장 — 전 팀(리그 단위 신호라 싸다)
        try:
            out_now = {}
            for team in teams:
                for k, v in (m._active_injuries(team, lg) or {}).items():
                    out_now[(team, k)] = v
            recent = (dt.date.today() - dt.timedelta(days=14)).isoformat()
            evs = m._injury_events(lg)                           # 화면(홈·Signals)과 같은 60일 창, 최근 2주만
            later = {}                                           # 복귀 뒤 따로 잡힌 새 부상(우아이사 햄스트링 복귀 → 9일 뒤 무릎)은 정상
            for e in evs:
                if e["event"] == "new":
                    k = (e["squad"], _norm(e["player"]))
                    later[k] = max(later.get(k, ""), e["date"])
            for e in evs:
                if e["event"] != "return" or e.get("source") == "출전" or e["date"] < recent:
                    continue
                if later.get((e["squad"], _norm(e["player"])), "") > e["date"]:
                    continue
                checked["injury_return"] += 1
                v = out_now.get((e["squad"], _norm(e["player"])))
                if v:
                    bad("injury_return", e["squad"], f"{e['player']} {e['date']} '부상 복귀' 인데 지금도 결장({v.get('injury')} ~{v.get('until')})")
        except Exception:  # noqa: BLE001
            pass
        sides = _lineup_sides(lg)
        for team in sample:
            # 6) 히트맵 좌우 — 화면 그리드(API 가 행을 뒤집어 위 = 왼쪽)의 무게중심이 라인업 쪽과 같은가
            try:
                hm = m.heatmaps(team, lg)
                for hp in hm.get("players") or []:
                    sd = sides.get((team, _norm(hp["player"])))
                    if not sd or int(hp.get("n_points") or 0) < 80:
                        continue
                    g, gw = hp["grid"], int(hm.get("gw") or 12)
                    tot = sum(g)
                    if not tot:
                        continue
                    gh = len(g) // gw
                    cy = sum((i // gw) * v for i, v in enumerate(g)) / tot / max(1, gh - 1)
                    shown = "L" if cy < 0.45 else "R" if cy > 0.55 else "C"
                    checked["heatmap_side"] += 1
                    if shown != "C" and shown != sd:
                        bad("heatmap_side", team, f"{hp['player']} 라인업 {sd} · 화면 히트맵 {shown}(세로 {cy:.2f})")
            except Exception:  # noqa: BLE001
                pass
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
