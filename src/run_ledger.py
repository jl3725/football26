"""
실행 원장(run ledger) — 수집 단계 하나가 돌 때마다 한 줄씩 남긴다(설계도 1단계 '실행 원장').

전에는 실패가 Actions 로그·로컬 로그에만 있어, 어느 데이터가 언제 멈췄는지 알려면 사람이 로그를 뒤져야 했다.
이제 단계마다 {언제, 어디서, 무슨 단계, 리그, 성공 여부, 걸린 시간}을 data/ops/runs/<runner>.jsonl 에 남기고
DATA STATUS 화면(/status · /api/ops/status)과 watchdog 이 이 원장을 읽는다.

- 실행 주체(runner)마다 파일을 따로 둔다 — GH 워크플로·로컬 agent 가 동시에 push 해도 같은 파일을 고치지 않아
  rebase 충돌이 나지 않는다(같은 워크플로는 concurrency 로 한 번에 하나).
- KEEP_DAYS 보다 오래된 줄은 쓸 때 잘라낸다.
- 표준 라이브러리만 쓴다(ci_try.sh 가 pip 설치 전에 불러도 동작).

CLI (scripts/ci_try.sh):
    python src/run_ledger.py add <runner> "<라벨>" <종료코드> <초>
라벨은 '단계 [리그]' — 예: "schedule EPL", "fotmob_injuries". 단계 이름으로 에이전트를 찾는다(agent_registry).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER_DIR = ROOT / "data" / "ops" / "runs"
KEEP_DAYS = 14
LEAGUE_KEYS = {"EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1", "LigaPortugal", "Eredivisie", "BelgianProLeague"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def runner_name(default: str = "") -> str:
    """실행 주체 이름 — LEDGER_RUNNER > GH 워크플로 파일 이름(daily_data 등) > default."""
    if os.getenv("LEDGER_RUNNER"):
        return os.environ["LEDGER_RUNNER"]
    ref = os.getenv("GITHUB_WORKFLOW_REF", "")          # owner/repo/.github/workflows/daily_data.yml@refs/heads/main
    m = re.search(r"workflows/([\w.-]+?)\.ya?ml@", ref)
    return m.group(1) if m else (default or "manual")


def parse_label(label: str) -> tuple[str, str | None]:
    """'schedule EPL' → ('schedule', 'EPL') · 'fotmob_injuries' → ('fotmob_injuries', None)."""
    parts = label.split()
    if not parts:
        return "", None
    league = next((p for p in parts[1:] if p in LEAGUE_KEYS), None)
    return parts[0], league


def record(runner: str, label: str, code: int | None, seconds: float, note: str = "",
           when: dt.datetime | None = None) -> dict:
    step, league = parse_label(label)
    ent = {"t": (when or _now()).isoformat(timespec="seconds"), "runner": runner, "step": step,
           "league": league, "ok": code == 0, "code": code, "sec": round(float(seconds), 1)}
    if os.getenv("GITHUB_RUN_ID"):
        ent["run"] = os.environ["GITHUB_RUN_ID"]
    if note:
        ent["note"] = note[:160]
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    path = LEDGER_DIR / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', runner)}.jsonl"
    cutoff = (_now() - dt.timedelta(days=KEEP_DAYS)).isoformat(timespec="seconds")
    keep = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                if json.loads(line).get("t", "") >= cutoff:
                    keep.append(line)
            except json.JSONDecodeError:
                continue
    keep.append(json.dumps(ent, ensure_ascii=False))
    path.write_text("\n".join(keep) + "\n", encoding="utf-8")
    return ent


def read_all(ledger_dir: Path | None = None) -> list[dict]:
    """모든 원장 줄(시간순)."""
    d = ledger_dir or LEDGER_DIR
    out: list[dict] = []
    if not d.exists():
        return out
    for p in sorted(d.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return sorted(out, key=lambda e: e.get("t", ""))


def main(argv: list[str]) -> int:
    if len(argv) >= 5 and argv[0] == "add":
        code = None if argv[3] in ("", "timeout") else int(argv[3])
        record(argv[1] or runner_name(), argv[2], code, float(argv[4]), note=argv[5] if len(argv) > 5 else "")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
