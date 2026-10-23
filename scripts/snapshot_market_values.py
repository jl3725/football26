"""
시장가치 변동 기록 agent — 리그마다 '값이 바뀐 선수만' 날짜와 함께 남긴다(변경분 기록).

2026-10-23 사용자 '시장가치 날짜별 기록을 13개 리그로'. 예전엔 data/market_value_history.csv 한 파일에 매일 전원을 쌓았는데,
① 파일 이름에 리그가 없어 tm_data 가 리그마다 부르면 첫 리그(EPL)만 오늘 날짜를 쓰고 나머지 12개는 '오늘 이미 있음'으로 건너뛰었고,
② 매일 전원을 쌓으면 13개 리그 1년에 수백만 줄이 된다. 그래서 평점 추이(src/rating_history.py)처럼 변경분만 쓴다.

파일(리그·시즌별 — build_db 가 market_value_log / market_value_changes 테이블로 싣는다)
  data/market_value_log[_리그]_<시즌>.csv     date · squad · player · tm_id · market_value_eur
      처음 = 그 리그 선수 전원(기준선), 그 뒤 = 값이나 소속이 바뀐 선수만. 'D 날의 값' = D 이전 마지막 줄.
  data/market_value_changes[_리그]_<시즌>.csv  run_date · squad · player · old_value · new_value · delta · pct
      최근 14일 큰 변동(€1M+ 또는 8%+) — 팀 화면 SIGNALS '시장가치 급등·급락'.
화면 쓰임: 선수 시장가치 추이 · 전체 홈 MARKET ▲ · TRACKING '시장가치·적정가' · 적정 이적료의 이적 직전 시장가치(src/fee_comps.py).

    python scripts/snapshot_market_values.py              # FB_LEAGUE 리그 하나(tm_data 가 리그마다 부른다)
    python scripts/snapshot_market_values.py --migrate    # 옛 EPL market_value_history.csv → 변경분 기록(한 번)
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import datastore as ds  # noqa: E402
from leagues import ACTIVE_LEAGUE, DATA_DIR, PRIMARY_LEAGUE, data_path  # noqa: E402

LOG_COLS = ["date", "squad", "player", "tm_id", "market_value_eur"]
CHANGE_COLS = ["run_date", "squad", "player", "old_value", "new_value", "delta", "pct"]
MIN_DELTA_EUR = 1_000_000     # 100만 유로 미만 변동은 노이즈로 무시
MIN_DELTA_PCT = 8.0           # 또는 8% 이상
KEEP_DAYS = 14                # 변동 기록 보관 기간(팀 화면 신호가 하루 만에 사라지지 않게)
OLD_HISTORY = DATA_DIR / "market_value_history.csv"


def _today() -> str:
    return datetime.date.today().isoformat()


def _pid(df: pd.DataFrame) -> pd.Series:
    """선수 식별 — TM id 가 있으면 그것(소속이 바뀌어도 같은 선수), 없으면 이름+소속.
    이름만 쓰면 TM id 없는 동명이인 둘이 하루씩 번갈아 '소속 변경'으로 찍혔다(EPL 옮기기에서 매일 4줄)."""
    tid = pd.to_numeric(df.get("tm_id"), errors="coerce")
    return tid.map(lambda v: f"tm{int(v)}" if v == v else "").where(
        tid.notna(), "nm:" + df["player"].astype(str) + "|" + df["squad"].astype(str))


def latest(log: pd.DataFrame) -> pd.DataFrame:
    """선수마다 마지막 줄(지금 기록된 값·소속)."""
    if log is None or log.empty:
        return pd.DataFrame(columns=LOG_COLS + ["_pid"])
    lg = log.copy()
    lg["_pid"] = _pid(lg)
    return lg.sort_values("date").groupby("_pid", as_index=False).tail(1)


def diff_rows(log: pd.DataFrame | None, snap: pd.DataFrame, today: str) -> pd.DataFrame:
    """오늘 스냅샷에서 기록에 새로 남길 줄 — 처음 보는 선수, 값이나 소속이 바뀐 선수."""
    snap = snap.copy()
    snap["_pid"] = _pid(snap)
    last = latest(log).set_index("_pid")
    # 한 날 같은 선수가 두 구단 줄에 다 있으면(임대·이적 선수가 원 소속·새 소속 표에 모두) 지난번 기록한 소속을 쓴다 —
    # 아니면 하루씩 번갈아 '소속 변경'으로 찍혔다(Guessand·Elliott·Ward-Prowse, EPL 옮기기에서 매일 4줄)
    prev_sq = {k: str(v) for k, v in last["squad"].items()} if len(last) else {}
    snap["_keep"] = [0 if prev_sq.get(k) == str(sq) else 1 for k, sq in zip(snap["_pid"], snap["squad"])]
    snap = snap.sort_values("_keep", kind="stable").drop_duplicates("_pid", keep="first")
    keep = []
    for r in snap.to_dict("records"):
        prev = last.loc[r["_pid"]] if r["_pid"] in last.index else None
        if prev is None or float(prev["market_value_eur"]) != float(r["market_value_eur"]) or str(prev["squad"]) != str(r["squad"]):
            keep.append({**{k: r.get(k) for k in LOG_COLS if k != "date"}, "date": today})
    return pd.DataFrame(keep, columns=LOG_COLS)


def changes_from(log: pd.DataFrame, run_date: str, old: pd.DataFrame | None) -> pd.DataFrame:
    """run_date 에 바뀐 값 중 큰 변동(같은 소속 안) + 최근 14일 누적."""
    lg = log.copy()
    lg["_pid"] = _pid(lg)
    lg = lg.sort_values("date")
    rows = []
    for _, g in lg.groupby("_pid"):
        if len(g) < 2 or str(g["date"].iloc[-1]) != run_date:
            continue
        a, b = g.iloc[-2], g.iloc[-1]
        if str(a["squad"]) != str(b["squad"]):
            continue                                        # 이적은 시장가치 급등·급락이 아니다
        ov, nv = float(a["market_value_eur"]), float(b["market_value_eur"])
        d = nv - ov
        pct = round(d / ov * 100, 1) if ov else None
        if abs(d) >= MIN_DELTA_EUR or (pct is not None and abs(pct) >= MIN_DELTA_PCT):
            rows.append({"run_date": run_date, "squad": b["squad"], "player": b["player"], "old_value": ov, "new_value": nv,
                         "delta": d, "pct": pct})
    out = pd.DataFrame(rows, columns=CHANGE_COLS)
    if old is not None and not old.empty:
        cut = (pd.Timestamp(run_date) - pd.Timedelta(days=KEEP_DAYS)).date().isoformat()
        old = old[old["run_date"].astype(str) >= cut]
        out = pd.concat([out, old], ignore_index=True).drop_duplicates(["squad", "player"], keep="first")
    if out.empty:
        return pd.DataFrame(columns=CHANGE_COLS)
    return out.sort_values(["run_date", "delta"], key=lambda s: s.abs() if s.name == "delta" else s, ascending=False)


def snapshot(league: str | None = None) -> int:
    league = league or ACTIVE_LEAGUE
    full = ds.read_table("players_full", league=league)
    if full is None or full.empty:
        print(f"! {league} players_full 없음 — 중단")
        return 1
    if "left_for" in full.columns:                           # 떠난 선수 줄(이적·임대로 나감)은 새 소속 쪽에서 센다
        full = full[full["left_for"].isna() | (full["left_for"].astype(str).str.strip() == "")]
    cols = [c for c in ["squad", "player", "tm_id", "market_value_eur"] if c in full.columns]
    snap = full[cols].copy()
    snap["market_value_eur"] = pd.to_numeric(snap["market_value_eur"], errors="coerce")
    snap = snap.dropna(subset=["market_value_eur"])
    snap = snap[snap["market_value_eur"] > 0]
    if "tm_id" not in snap.columns:
        snap["tm_id"] = None
    today = _today()
    log_p, chg_p = data_path("market_value_log", league), data_path("market_value_changes", league)
    log = pd.read_csv(log_p) if log_p.exists() else None
    new = diff_rows(log, snap, today)
    if log is not None and not new.empty:
        log = log[log["date"].astype(str) != today]          # 같은 날 다시 돌면 오늘 줄만 새로
        new = diff_rows(log, snap, today)
    if new.empty and log is not None:
        print(f"= {league} 시장가치 변화 없음({len(snap)}명)")
        return 0
    out = new if log is None else pd.concat([log, new], ignore_index=True)
    out[LOG_COLS].to_csv(log_p, index=False, encoding="utf-8", lineterminator="\n")
    first = log is None
    print(f"+ {league} {'기준선' if first else '변경'} {len(new)}명 → {log_p.name}")
    if not first:
        old = pd.read_csv(chg_p) if chg_p.exists() else None
        changes_from(out, today, old).to_csv(chg_p, index=False, encoding="utf-8", lineterminator="\n")
    elif not chg_p.exists():
        pd.DataFrame(columns=CHANGE_COLS).to_csv(chg_p, index=False)
    return 0


def migrate() -> int:
    """옛 EPL 일일 스냅샷(market_value_history.csv, 2026-07-01~) → 변경분 기록. 이력 날짜는 그대로 보존."""
    if not OLD_HISTORY.exists():
        print("옛 기록 없음")
        return 0
    h = pd.read_csv(OLD_HISTORY)
    h["market_value_eur"] = pd.to_numeric(h["market_value_eur"], errors="coerce")
    h = h.dropna(subset=["market_value_eur"])
    log = None
    for d in sorted(h["date"].astype(str).unique()):
        snap = h[h["date"].astype(str) == d][["squad", "player", "tm_id", "market_value_eur"]]
        new = diff_rows(log, snap, d)
        if log is None:
            log = new
        elif not new.empty:
            log = pd.concat([log, new], ignore_index=True)
    p = data_path("market_value_log", PRIMARY_LEAGUE)
    log[LOG_COLS].to_csv(p, index=False, encoding="utf-8", lineterminator="\n")
    print(f"옛 EPL 기록 {len(h)}줄 → 변경분 {len(log)}줄 → {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(migrate() if "--migrate" in sys.argv[1:] else snapshot())
