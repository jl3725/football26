"""
운영 감시(Watchdog) — 사람이 화면을 보고 알아채기 전에 '조용한 고장'을 잡는다.

배경: 2026-07~10 사이 프론트 배포가 석 달간 실패(홈에 25/26 문구 잔류), 뉴스가 원문으로 쌓이고,
홈 스냅샷이 7/7 에 멈추고, TM 수집이 차단됐는데 아무도 몰랐다. 전부 '실행은 초록, 결과는 고장'.

점검 항목
  season    운영 /api/context — 데이터 시즌이 달력 시즌보다 뒤처졌는가(phase=stale)
  hub       운영 /api/home/all — 시즌 라벨이 context 와 같은가, 스냅샷 생성 36시간 이내인가
  frontend  web/ 를 바꾼 최신 커밋이 Vercel Production 에 배포됐는가
  workflows daily_data·daily_news·keep_alive·CI 최근 실행이 성공인가
  news      news.db 마지막 수집 1일 이내, 최근 2일 번역률 50% 이상
  tm_agent  로컬 TM agent(이 PC 작업 스케줄러) 산출물이 최근에 커밋됐는가
  coverage  현재 시즌 팀 전원에게 감독 프로필이 있는가(시즌 전환 뒤 승격팀 누락·강등팀 잔류 탐지)
  rating_history  선수 평점 일일 기록(▲▼ 추이 원천)이 3일 안에 갱신됐는가
  ratings   평점 자체 검증(data/eval/rating_audit.json, daily_data 가 매일 생성) — 사용자 기준(golden) 위반,
            스카우트 기준표 3 이상 이탈, 자동 점검(한 시즌 급등·급락·고평점 이상치) 한도 초과
  names     선수 이름 레지스트리(data/eval/name_audit.json) 3일 내 갱신, 기준 명단 밖 선발 3경기+ 이름 30개 이하

사용:
  python scripts/watchdog.py            # 결과 출력, 실패가 있으면 종료코드 1
  python scripts/watchdog.py --issue    # (GH Actions) 'watchdog' 이슈 열기·갱신·닫기
환경변수: GITHUB_TOKEN(또는 gh 로그인), GITHUB_REPOSITORY, BACKEND_URL
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from leagues import LEAGUES, data_path  # noqa: E402

REPO = os.getenv("GITHUB_REPOSITORY", "jl3725/football26")
BACKEND = os.getenv("BACKEND_URL", "https://football26-api.onrender.com").rstrip("/")
WORKFLOWS = ["daily_data.yml", "daily_news.yml", "keep_alive.yml", "ci.yml"]
NOW = dt.datetime.now(dt.timezone.utc)
LABEL = "watchdog"


def _token() -> str:
    tok = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if tok:
        return tok
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


_S = requests.Session()
_S.headers.update({"Accept": "application/vnd.github+json", "User-Agent": "football26-watchdog"})
if _token():
    _S.headers["Authorization"] = f"Bearer {_token()}"


def gh(path: str, method: str = "GET", **kw):
    r = _S.request(method, f"https://api.github.com/repos/{REPO}/{path}", timeout=30, **kw)
    r.raise_for_status()
    return r.json() if r.content else None


def _ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def _age_h(s: str) -> float:
    return (NOW - _ts(s)).total_seconds() / 3600


def _api(path: str) -> dict:
    # Render 무료 티어는 잠들어 있으면 깨어나는 데 1분 가까이 걸린다
    for attempt in range(3):
        try:
            r = requests.get(f"{BACKEND}{path}", timeout=90)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == 2:
                raise
    return {}


# ── 점검 ─────────────────────────────────────────────────────────────────────
def check_season() -> list[str]:
    ctx = _api("/api/context")
    w = ctx.get("window") or {}
    if w.get("phase") == "stale":
        return [f"운영 데이터 시즌 {ctx.get('data_season')} 이 달력 시즌 {w.get('label')} 보다 뒤처짐 "
                f"(Render FB_SEASON_START·시즌 빌드 확인)"]
    return []


def check_hub() -> list[str]:
    ctx, hub = _api("/api/context"), _api("/api/home/all")
    out = []
    if (hub.get("window") or {}).get("label") != ctx.get("data_season"):
        out.append(f"홈 스냅샷 시즌 {hub.get('window', {}).get('label')} ≠ 운영 시즌 {ctx.get('data_season')}")
    gen = hub.get("generated_at")
    if not gen:
        out.append("홈 스냅샷에 생성 시각 없음(precompute_hub 가 예전 코드로 돈 것)")
    elif _age_h(gen) > 36:
        out.append(f"홈 스냅샷이 {_age_h(gen):.0f}시간 전 생성 — daily_data 의 precompute_hub 확인")
    return out


def check_frontend() -> list[str]:
    web = gh("commits", params={"sha": "main", "path": "web", "per_page": 1})[0]
    web_sha, web_at = web["sha"], web["commit"]["committer"]["date"]
    deps = gh("deployments", params={"environment": "Production", "per_page": 15})
    latest_ok = None
    for d in deps:                                        # 최신순
        st = gh(f"deployments/{d['id']}/statuses", params={"per_page": 1})
        if st and st[0]["state"] == "success":
            latest_ok = d
            break
    if latest_ok is None:
        return ["Vercel Production 성공 배포 기록이 없음"]
    if latest_ok["sha"] == web_sha:
        return []
    cmp = gh(f"compare/{web_sha}...{latest_ok['sha']}")
    if cmp["status"] in ("identical", "ahead"):
        return []
    if _age_h(web_at) < 1:
        return []                                         # 방금 커밋 — 빌드 중일 수 있음
    return [f"web/ 변경 {web_sha[:7]}({web_at[:16]}) 이 운영에 없음 — 마지막 성공 배포 {latest_ok['sha'][:7]}"
            f"({latest_ok['created_at'][:16]}). Vercel 빌드 로그 확인"]


def check_workflows() -> list[str]:
    out = []
    for wf in WORKFLOWS:
        runs = gh(f"actions/workflows/{wf}/runs",
                  params={"branch": "main", "status": "completed", "per_page": 1}).get("workflow_runs", [])
        if not runs:
            continue
        r = runs[0]
        if r["conclusion"] not in ("success", "skipped"):
            out.append(f"{wf} 최근 실행 {r['conclusion']} ({r['created_at'][:16]}) {r['html_url']}")
    return out


def check_news() -> list[str]:
    db = ROOT / "data" / "news.db"
    if not db.exists():
        return ["data/news.db 없음"]
    c = sqlite3.connect(db)
    last = c.execute("SELECT max(first_seen) FROM articles").fetchone()[0] or ""
    since = (NOW.date() - dt.timedelta(days=2)).isoformat()
    tot, bad = c.execute(
        "SELECT count(*), sum(CASE WHEN headline_ko IS NULL OR headline_ko='' OR headline_ko=headline "
        "THEN 1 ELSE 0 END) FROM articles WHERE first_seen>=?", (since,)).fetchone()
    out = []
    if last < (NOW.date() - dt.timedelta(days=1)).isoformat():
        out.append(f"뉴스 마지막 수집 {last} — daily_news 확인")
    if tot and (tot - (bad or 0)) / tot < 0.5:
        out.append(f"최근 2일 뉴스 번역률 {100 * (tot - (bad or 0)) / tot:.0f}% ({bad}/{tot}건 원문) — "
                   "GEMINI_API_KEY·구글 차단 여부 확인")
    return out


def _last_commit_h(path: Path) -> float | None:
    rel = path.relative_to(ROOT).as_posix()
    c = gh("commits", params={"sha": "main", "path": rel, "per_page": 1})
    return _age_h(c[0]["commit"]["committer"]["date"]) if c else None


def check_tm_agent() -> list[str]:
    # 부상 목록은 8개 리그 중 어디선가 거의 매일 바뀐다 — 가장 최근 커밋이 3일을 넘으면 agent 정지로 본다
    ages = [a for a in (_last_commit_h(data_path("transfermarkt_injuries", lg)) for lg in LEAGUES) if a is not None]
    if not ages:
        return ["TM 부상 파일 커밋 기록 없음"]
    if min(ages) > 72:
        return [f"TM 수집 산출물이 {min(ages) / 24:.1f}일째 그대로 — GitHub Actions 'TM Data' 실행 기록 확인"
                "(WAF 토큰 실패면 로그에 '[tm_http]')"]
    return []


def check_coverage() -> list[str]:
    import csv
    out = []
    for lg in LEAGUES:
        st, mp = data_path("standings", lg), data_path("manager_profiles", lg, ext="json")
        if not st.exists():
            out.append(f"{lg} 현재 시즌 순위표 없음({st.name})")
            continue
        if not mp.exists():
            continue                                      # 감독 수집 미지원 리그(벨기에 — 위키 시즌 문서에 감독표 없음)
        with st.open(encoding="utf-8") as fh:
            teams = {r["squad"] for r in csv.DictReader(fh) if r.get("squad")}
        prof = set(json.loads(mp.read_text(encoding="utf-8")))
        miss, extra = sorted(teams - prof), sorted(prof - teams)
        if miss:
            out.append(f"{lg} 감독 프로필 누락 {miss}" + (f" · 다른 시즌 팀 잔류 {extra}" if extra else "")
                       + " — daily_data 감독 수집 단계 확인")
    return out


def check_rating_history() -> list[str]:
    """평점 추이 기록(daily_data → record_ratings)이 멈추면 ▲▼ 가 조용히 사라진다."""
    p = data_path("rating_history", "EPL")
    if not p.exists():
        return [f"{p.name} 없음 — daily_data 'Record player ratings' 단계 확인"]
    last = max((ln.split(",", 1)[0] for ln in p.read_text(encoding="utf-8").splitlines()[1:] if ln), default="")
    if last < (NOW.date() - dt.timedelta(days=3)).isoformat():
        return [f"평점 추이 마지막 기록 {last} — daily_data 'Record player ratings' 단계 확인"]
    return []


def check_ratings() -> list[str]:
    """선수 OVR 이 사람 눈에 이상해지기 전에 — daily_data 의 eval_ratings --audit-json 결과를 읽는다."""
    p = ROOT / "data" / "eval" / "rating_audit.json"
    if not p.exists():
        return [f"{p.name} 없음 — daily_data 'Rating audit' 단계 확인"]
    a = json.loads(p.read_text(encoding="utf-8"))
    out = []
    if a.get("date", "") < (NOW.date() - dt.timedelta(days=3)).isoformat():
        out.append(f"평점 자체 검증 마지막 실행 {a.get('date')} — daily_data 'Rating audit' 단계 확인")
    out += [f"사용자 기준 위반: {b}" for b in a.get("golden", [])]
    out += [f"스카우트 기준 이탈: {x['player']} {x['ovr']} (기대 {x['lo']}~{x['hi']})" for x in a.get("scout_far", [])]
    for k, v in (a.get("audit") or {}).items():
        if v.get("n", 0) > v.get("limit", 1e9):
            out.append(f"자동 점검 {k} {v['n']}건 > 한도 {v['limit']} — {v.get('desc', '')}: "
                       + ", ".join(v.get("examples", [])[:4]))
    return out


def check_names() -> list[str]:
    """선수 이름 레지스트리 — 기준 명단(players_full·TM 명단·위키) 밖에서 3경기+ 선발로 뛴 '고아' 이름이 많으면
    표기 규칙이 못 잡는 새 변형이 생긴 것(data/name_aliases.csv 에 수동 지정)."""
    p = ROOT / "data" / "eval" / "name_audit.json"
    if not p.exists():
        return [f"{p.name} 없음 — match_refresh·daily_data 'Player registry' 단계 확인"]
    a = json.loads(p.read_text(encoding="utf-8"))
    meta = a.get("_meta", {})
    out = []
    if meta.get("date", "") < (NOW.date() - dt.timedelta(days=3)).isoformat():
        out.append(f"이름 레지스트리 마지막 갱신 {meta.get('date')} — 'Player registry' 단계 확인")
    season = meta.get("season", "")
    orph = [(o["name"], o["squad"], o["starts"]) for k, v in a.items() if k != "_meta" and k.endswith(season)
            for s in v.values() for o in s.get("orphans", []) if o.get("starts", 0) >= 3]
    if len(orph) > 30:
        top = sorted(orph, key=lambda x: -x[2])[:6]
        out.append(f"기준 명단 밖 선발 3경기+ 이름 {len(orph)}개(>30) — 표기 변형 확인: "
                   + ", ".join(f"{n}({q} {s})" for n, q, s in top))
    return out


def check_ovr() -> list[str]:
    """OVR 검증 에이전트(scripts/check_ovr_consistency.py, daily_data) — 같은 선수 OVR 이 화면마다 다르면 알린다.
    2026-10-19 사용자: 하베르츠 포메이션 83 · 프로필 84."""
    p = ROOT / "data" / "eval" / "ovr_audit.json"
    if not p.exists():
        return [f"{p.name} 없음 — daily_data 'OVR consistency' 단계 확인"]
    a = json.loads(p.read_text(encoding="utf-8"))
    out = []
    if a.get("date", "") < (NOW.date() - dt.timedelta(days=3)).isoformat():
        out.append(f"OVR 검증 마지막 실행 {a.get('date')} — daily_data 'OVR consistency' 단계 확인")
    mism = a.get("mismatches") or []
    if mism:
        out.append(f"화면별 OVR 불일치 {len(mism)}건: " + ", ".join(
            f"{x['team']} {x['player']} {x['source']} {x['shown']}≠{x['final']}" for x in mism[:5]))
    return out


CHECKS = {"ovr": check_ovr, "season": check_season, "hub": check_hub, "frontend": check_frontend,
          "workflows": check_workflows, "news": check_news, "tm_agent": check_tm_agent,
          "coverage": check_coverage, "rating_history": check_rating_history, "ratings": check_ratings,
          "names": check_names}


def run() -> dict[str, list[str]]:
    res = {}
    for name, fn in CHECKS.items():
        try:
            res[name] = fn()
        except Exception as e:  # noqa: BLE001 — 점검 자체가 깨져도 다른 점검은 계속
            res[name] = [f"점검 실패: {type(e).__name__}: {str(e)[:160]}"]
    return res


# ── 이슈 ─────────────────────────────────────────────────────────────────────
def _body(res: dict[str, list[str]], failing: list[str]) -> str:
    lines = [f"<!-- watchdog:{','.join(failing)} -->",
             f"**{NOW:%Y-%m-%d %H:%M} UTC 점검 — 실패 {len(failing)}/{len(res)}**", ""]
    for name, probs in res.items():
        lines.append(f"- {'❌' if probs else '✅'} `{name}`" + ("" if probs else " 정상"))
        lines += [f"  - {p}" for p in probs]
    lines += ["", "scripts/watchdog.py 가 매일 갱신합니다. 전부 정상이 되면 자동으로 닫힙니다."]
    return "\n".join(lines)


def file_issue(res: dict[str, list[str]]) -> None:
    failing = [k for k, v in res.items() if v]
    open_ = gh("issues", params={"labels": LABEL, "state": "open", "per_page": 5})
    issue = open_[0] if open_ else None
    if not failing:
        if issue:
            gh(f"issues/{issue['number']}/comments", "POST", json={"body": _body(res, failing)})
            gh(f"issues/{issue['number']}", "PATCH", json={"state": "closed"})
            print(f"이슈 #{issue['number']} 닫음 — 전부 정상")
        return
    body = _body(res, failing)
    if issue is None:
        try:
            gh("labels", "POST", json={"name": LABEL, "color": "d93f0b", "description": "운영 감시 자동 이슈"})
        except requests.HTTPError:
            pass                                          # 이미 있음
        new = gh("issues", "POST", json={"title": f"[watchdog] 운영 점검 실패: {', '.join(failing)}",
                                         "body": body, "labels": [LABEL]})
        print(f"이슈 #{new['number']} 생성")
        return
    before = (issue.get("body") or "").split("\n", 1)[0]  # 첫 줄 = <!-- watchdog:실패항목 -->
    gh(f"issues/{issue['number']}", "PATCH",
       json={"title": f"[watchdog] 운영 점검 실패: {', '.join(failing)}", "body": body})
    if body.split("\n", 1)[0] != before:                 # 실패 항목이 바뀌었을 때만 알림(댓글)
        gh(f"issues/{issue['number']}/comments", "POST", json={"body": "실패 항목이 바뀌었습니다.\n\n" + body})
    print(f"이슈 #{issue['number']} 갱신")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = argv if argv is not None else sys.argv[1:]
    res = run()
    for name, probs in res.items():
        print(f"[{'FAIL' if probs else ' OK '}] {name}")
        for p in probs:
            print(f"        {p}")
    if "--issue" in args:
        file_issue(res)
        return 0                                          # 알림은 이슈로 — 실행까지 빨갛게 해 이중 알림 내지 않음
    return 1 if any(res.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
