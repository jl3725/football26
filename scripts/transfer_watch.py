"""
이적시장 감시(transfer watch) — 창이 열려 있는 동안 리그 이적 페이지를 주기적으로 보고, 새 이적이 생긴 클럽만 다시 받아
바로 커밋한다(설계도 2단계 '이적시장 기간 Transfer 시간당').

평소 이적 수집(tm_data)은 하루 2번 전 클럽 페이지(리그당 ~20, 8개 리그 ~150 요청)를 돈다. 그대로 매시간 돌리면
Transfermarkt 부하·차단 위험이 커서, 여기선 리그 전체 이적 페이지 1장(리그당 1 요청, 모든 클럽의 IN/OUT)을 보고
우리 데이터에 없는 이름이 있는 클럽만 src/fetch_transfers.py <클럽> 으로 다시 받는다(팀 단위 교체).

주기: 마감 7일 전부터는 60분, 그 전엔 180분. 창이 닫혀 있으면 바로 끝(season_context.current_window).
GH 작업 한 번에 최대 5.5시간, 창이 열려 있으면 자기 자신을 다시 실행(예약 실행 지연과 무관 — match_watch 와 같은 방식).

    python scripts/transfer_watch.py                  # GH Actions
    python scripts/transfer_watch.py --once --dry-run --force EPL   # 창이 닫혀 있어도 한 번 비교만(받지 않음)
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import player_registry as preg  # noqa: E402
import run_ledger  # noqa: E402
import team_names  # noqa: E402
import tm_http  # noqa: E402
from leagues import LEAGUES, data_path, league_config  # noqa: E402
from season_context import current_window  # noqa: E402

REPO = os.getenv("GITHUB_REPOSITORY", "jl3725/football26")
WINDOW_END = {"summer": (9, 1), "winter": (2, 3)}   # season_context 와 같은 마감일


def interval_min(today: dt.date, window: str) -> int:
    m, d = WINDOW_END[window]
    end = dt.date(today.year if not (window == "winter" and today.month > 6) else today.year + 1, m, d)
    return 60 if (end - today).days <= 7 else 180


def league_page(lg: str, season_id: int, window: str) -> str:
    cfg = league_config(lg)
    sw = "s" if window == "summer" else "w"
    url = (f"https://www.transfermarkt.com/{cfg.tm_slug}/transfers/wettbewerb/{cfg.tm_id}"
           f"/saison_id/{season_id}/s_w/{sw}/leihe//intern/0")
    r = tm_http.get(url, timeout=40)
    r.raise_for_status()
    return r.text


def parse_league_page(html: str) -> dict[str, dict[str, set[str]]]:
    """{TM 클럽 이름: {'in': {정규화 이름}, 'out': {…}}} — 클럽 상자마다 표 2개(In·Out)."""
    out: dict[str, dict[str, set[str]]] = {}
    for box in BeautifulSoup(html, "lxml").select("div.box"):
        h = box.select_one("h2")
        tables = box.select("table")
        name = h.get_text(" ", strip=True) if h else ""
        if not name or len(tables) < 2:
            continue
        sides = {}
        for key, t in zip(("in", "out"), tables[:2]):
            names = set()
            for tr in t.select("tbody tr"):
                a = tr.select_one("td a")
                if a and a.get_text(strip=True):
                    names.add(preg.norm(a.get_text(strip=True)))
            sides[key] = names
        out[name] = sides
    return out


def changed_clubs(page: dict[str, dict[str, set[str]]], ours: pd.DataFrame, season_id: int, window: str) -> list[str]:
    """TM 리그 페이지에 있는데 우리 데이터(같은 시즌·창)에 없는 이적이 있는 클럽 — 우리 표기로."""
    squads = sorted(ours["squad"].astype(str).unique()) if len(ours) else []
    mine = ours[(ours["season_id"] == season_id) & (ours["window"] == window)] if len(ours) else ours
    have: dict[tuple[str, str], set[str]] = {}
    for (sq, dr), g in (mine.groupby(["squad", "direction"]) if len(mine) else []):
        have[(str(sq), str(dr))] = {preg.norm(p) for p in g["player"]}
    out = []
    for club, sides in page.items():
        sq = team_names.best(club, squads)
        if not sq:
            continue
        if any(sides.get(dr, set()) - have.get((sq, dr), set()) for dr in ("in", "out")):
            out.append(sq)
    return sorted(set(out))


def refetch(lg: str, squad: str, dry: bool) -> bool:
    if dry:
        print(f"[transfer-watch] (dry-run) {lg} {squad} 다시 받았을 것")
        return True
    t0 = time.time()
    code = subprocess.run([sys.executable, str(ROOT / "src" / "fetch_transfers.py"), squad], cwd=ROOT,
                          env={**os.environ, "FB_LEAGUE": lg, "PYTHONIOENCODING": "utf-8"}).returncode
    run_ledger.record(run_ledger.runner_name("transfer_watch"), f"transfers {lg}", code, time.time() - t0,
                      note="" if code == 0 else squad)
    return code == 0


def _git(*args: str) -> int:
    return subprocess.run(["git", *args], cwd=ROOT).returncode


def sync() -> None:
    """(CI) 회차마다 최신 main 으로 — tm_data 가 같은 이적 파일을 하루 2번 커밋한다."""
    if os.getenv("GITHUB_ACTIONS") and _git("pull", "-q", "--rebase", "--autostash", "origin", "main") != 0:
        _git("rebase", "--abort")
        _git("fetch", "-q", "origin", "main")
        _git("reset", "-q", "--hard", "origin/main")


def commit(msg: str) -> None:
    _git("add", "--", "data/transfers_*.csv", "data/ops/runs/")
    if _git("diff", "--cached", "--quiet") == 0:
        return
    _git("commit", "-q", "-m", msg)
    for _ in range(3):
        if _git("pull", "-q", "--rebase", "--autostash", "origin", "main") == 0 and _git("push", "-q") == 0:
            print("[transfer-watch] 커밋·푸시")
            return
        _git("rebase", "--abort")
        time.sleep(5)
    # 같은 파일을 tm_data 가 막 바꿨다 — 이번 커밋은 버리고 다음 회차가 최신 데이터와 다시 비교해 받는다
    print("[transfer-watch] push 충돌 — 이번 회차 버리고 다음 회차에 다시")
    _git("fetch", "-q", "origin", "main")
    _git("reset", "-q", "--hard", "origin/main")


def dispatch_self(dry: bool) -> None:
    if dry:
        print("[transfer-watch] (dry-run) 이어 달리기 실행했을 것")
        return
    tok = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    r = requests.post(f"https://api.github.com/repos/{REPO}/actions/workflows/transfer_watch.yml/dispatches",
                      headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
                      json={"ref": "main"}, timeout=20)
    print(f"[transfer-watch] 이어 달리기 요청 → {r.status_code}")


def one_round(leagues: list[str], season_id: int, window: str, dry: bool) -> int:
    n_changed = 0
    for lg in leagues:
        p = data_path("transfers", lg)
        ours = pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["squad", "season_id", "window", "direction", "player"])
        try:
            page = parse_league_page(league_page(lg, season_id, window))
        except Exception as e:  # noqa: BLE001
            print(f"[transfer-watch] {lg} 리그 이적 페이지 실패: {type(e).__name__}")
            continue
        clubs = changed_clubs(page, ours, season_id, window)
        print(f"[transfer-watch] {lg} 클럽 {len(page)} · 새 이적 있는 클럽 {len(clubs)} {clubs[:6]}")
        for sq in clubs:
            n_changed += refetch(lg, sq, dry)
        time.sleep(3)
    return n_changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("leagues", nargs="*")
    ap.add_argument("--max-minutes", type=float, default=330)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="창이 닫혀 있어도(지난 여름 창 기준) 비교")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    win = current_window()
    if not win["is_open"] and not a.force:
        print(f"[transfer-watch] 이적시장 닫힘({win['state']}) — 종료")
        return 0
    window = win["window"] if win["is_open"] else "summer"
    leagues = a.leagues or list(LEAGUES)
    started = time.time()
    while True:
        today = dt.date.today()
        if not a.dry_run:
            sync()
        n = one_round(leagues, int(win["season_id"]), window, a.dry_run)
        if n and not a.dry_run:
            commit(f"chore(data): 이적시장 감시 — 새 이적 {n}개 클럽 [skip ci]")
        if a.once:
            return 0
        wait = interval_min(today, window) * 60
        if time.time() - started + wait > a.max_minutes * 60:
            if current_window()["is_open"]:
                dispatch_self(a.dry_run)
            return 0
        time.sleep(wait)


if __name__ == "__main__":
    raise SystemExit(main())
