"""
국가대표 대회 레지스트리 — 어떤 대회가 있고(자동 발견), 지금 어떤 상태인지(예정·진행·종료·우승팀) 대륙별로.

손으로 쓴 대회 목록 없이:
  1. ESPN 리그 목록(core API)에서 국제 대회 접두사(fifa·uefa·afc·caf·conmebol·concacaf·ofc) 리그를 받고
  2. 상세 정보로 남자(gender=MALE)만, 이름에 연령·올림픽·여자 표시가 없는 것만 남긴 뒤
  3. 실제 경기의 팀 이름이 나라(FIFA 랭킹 표)인지로 국가대표 대회를 가린다(챔스·리베르타도레스 같은 클럽 대회 제외).
대륙 = 코드 앞부분, 종류 = 이름·토너먼트 여부(본선 · 예선 · 네이션스리그 · 친선), 회차 = 경기의 ESPN 시즌 연도.
상태: 시작 전 = upcoming, 경기 중 = live(첫 경기 ~ 마지막 경기 + 1일), 끝 = finished(본선은 결승 승자 = 우승).
한글 이름은 무료 번역 체인(src/translate.py)으로 한 번 만들어 캐시.

산출: data/intl_competitions.json · 레지스트리 캐시 data/intl_registry.json(7일)
    python src/intl_comps.py
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espn_common import scoreboard_events  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "intl_registry.json"
OUT = ROOT / "data" / "intl_competitions.json"
CORE = "https://sports.core.api.espn.com/v2/sports/soccer/leagues"
H = {"User-Agent": "Mozilla/5.0 (football26 intl agent)"}
PREFIX = re.compile(r"^(fifa|uefa|afc|caf|conmebol|concacaf|ofc)\.")
NOT_SENIOR = re.compile(r"(u-?\d{2}|under-?\d{2}|olympic|women|womens|femenin|youth|futsal|beach)", re.I)
CONF = {"fifa": "GLOBAL", "uefa": "UEFA", "afc": "AFC", "caf": "CAF", "conmebol": "CONMEBOL", "concacaf": "CONCACAF", "ofc": "OFC"}
REG_DAYS = 7
PLACEHOLDER = re.compile(r"(winner|loser|place|group|tbd|runner|qualifier|/)", re.I)


def _fold(s) -> str:
    from unidecode import unidecode
    return re.sub(r"[^a-z]", "", unidecode(str(s or "")).lower())


def _countries() -> set[str]:
    """나라 이름(접은 형태) — FIFA 랭킹 표 + ESPN 표기 차이를 흡수할 흔한 변형."""
    import pandas as pd
    p = ROOT / "data" / "fifa_ranking.csv"
    names = set()
    if p.exists():
        names |= {_fold(x) for x in pd.read_csv(p)["team"].astype(str)}
    try:
        import fetch_intl as fi
        names |= {_fold(k) for k in fi.FIFA_NAME} | {_fold(v) for v in fi.FIFA_NAME.values()}
    except Exception:  # noqa: BLE001
        pass
    return names


def kind_of(code: str, name: str, is_tournament: bool) -> str:
    n = name.lower()
    if "friendly" in n or not is_tournament:
        return "friendly"
    if "qualif" in n or re.search(r"(q|_qual|qual)$", code) or ".worldq." in code or "playoff" in n:
        return "qualifier"
    if "nations league" in n:
        return "nations_league"
    return "tournament"


def discover(force: bool = False) -> list[dict]:
    """국가대표 남자 성인 대회 목록 — 7일 캐시. 실패하면 지난 캐시."""
    if REGISTRY.exists() and not force:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        if reg.get("date", "") >= (dt.date.today() - dt.timedelta(days=REG_DAYS)).isoformat():
            return reg["comps"]
    old = json.loads(REGISTRY.read_text(encoding="utf-8"))["comps"] if REGISTRY.exists() else []
    try:
        items = requests.get(CORE, params={"limit": 1000}, headers=H, timeout=30).json().get("items", [])
    except (requests.RequestException, ValueError):
        return old
    slugs = [m.group(1) for i in items if (m := re.search(r"/leagues/([^?]+)", i.get("$ref", "")))]
    countries = _countries()
    today = dt.date.today()
    known = {c["code"]: c for c in old}
    comps = []
    for code in [s for s in slugs if PREFIX.match(s)]:
        try:
            d = requests.get(f"{CORE}/{code}", headers=H, timeout=30).json()
        except (requests.RequestException, ValueError):
            if code in known:
                comps.append(known[code])
            continue
        name = str(d.get("name") or code)
        if d.get("gender") != "MALE" or NOT_SENIOR.search(name) or NOT_SENIOR.search(code):
            continue
        # 국가대표 대회인가 — 최근·다가올 경기 팀 이름 중 나라 비율(클럽 대회는 0에 가깝다)
        evs = scoreboard_events(code, (today - dt.timedelta(days=900)).isoformat(), (today + dt.timedelta(days=500)).isoformat()) or []
        teams = {t.get("team", {}).get("displayName", "") for e in evs for t in (e.get("competitions") or [{}])[0].get("competitors", [])}
        teams = {t for t in teams if t and not PLACEHOLDER.search(t)}    # 'Group A Winner' 같은 대진 자리표시 제외
        if len(teams) < 4:
            if code in known:
                comps.append(known[code])
            continue
        share = sum(1 for t in teams if _fold(t) in countries) / len(teams)
        if share < 0.5:
            continue
        comps.append({"code": code, "name": name, "conf": CONF[code.split(".")[0]],
                      "kind": kind_of(code, name, bool(d.get("isTournament"))), "name_ko": known.get(code, {}).get("name_ko")})
    if not comps:
        return old
    _korean_names(comps)
    REGISTRY.write_text(json.dumps({"date": today.isoformat(), "comps": comps}, ensure_ascii=False, indent=1), encoding="utf-8")
    return comps


def _korean_names(comps: list[dict]) -> None:
    need = [c for c in comps if not c.get("name_ko")]
    if not need:
        return
    try:
        import translate
        out = translate.translate_many([c["name"] for c in need])
    except Exception:  # noqa: BLE001
        return
    for c, ko in zip(need, out):
        if ko:
            c["name_ko"] = ko


def _winner(c: dict) -> tuple[str | None, str | None]:
    """경기의 승자·패자 — ESPN 'winner' 표시(승부차기 포함)."""
    cs = c.get("competitors", [])
    w = next((t for t in cs if t.get("winner") is True), None)
    lo = next((t for t in cs if t is not w), None)
    name = lambda t: (t or {}).get("team", {}).get("displayName")  # noqa: E731
    return (name(w), name(lo)) if w else (None, None)


def editions(code: str, today: dt.date, kind: str = "") -> list[dict]:
    """대회 회차(ESPN 시즌 연도)별 기간·경기 수·상태·우승. 본선은 2~4년 주기라 기간을 넓혀 직전·다음 대회까지."""
    back, ahead = (900, 900) if kind == "tournament" else (420, 520)
    evs = scoreboard_events(code, (today - dt.timedelta(days=back)).isoformat(), (today + dt.timedelta(days=ahead)).isoformat())
    if evs is None:
        return []
    by: dict[str, list] = {}
    for e in evs:
        by.setdefault(str((e.get("season") or {}).get("year") or (e.get("date") or "")[:4]), []).append(e)
    out = []
    for season, es in sorted(by.items()):
        es.sort(key=lambda e: e.get("date") or "")
        first, last = (es[0].get("date") or "")[:10], (es[-1].get("date") or "")[:10]
        done = sum(1 for e in es if ((e.get("status") or {}).get("type") or {}).get("state") == "post")
        status = ("upcoming" if today.isoformat() < first else
                  "live" if today.isoformat() <= (dt.date.fromisoformat(last) + dt.timedelta(days=1)).isoformat() and done < len(es)
                  else "finished")
        champ = runner = None
        fin = es[-1]
        fc = (fin.get("competitions") or [{}])[0]
        note = " ".join(n.get("headline", "") for n in fc.get("notes", []) if isinstance(n, dict)).lower()
        # 우승은 본선 결승에만('semifinal'·'3rd place' 아님) — 예선의 마지막 경기 승자를 우승으로 적던 것
        is_final = "final" in note and not re.search(r"semi|quarter|3rd|third|place", note)
        if status == "finished" and kind in ("tournament", "nations_league") and (is_final or kind == "tournament"):
            champ, runner = _winner(fc)
        out.append({"season": season, "start": first, "end": last, "matches": len(es), "played": done,
                    "status": status, "champion": champ, "runner_up": runner})
    return out


def build() -> dict:
    today = dt.date.today()
    comps = discover()
    res = []
    for c in comps:
        eds = editions(c["code"], today, c["kind"])
        if not eds:
            continue
        res.append({**c, "editions": eds})
    conf_order = ["GLOBAL", "UEFA", "AFC", "CAF", "CONMEBOL", "CONCACAF", "OFC"]
    res.sort(key=lambda c: (conf_order.index(c["conf"]) if c["conf"] in conf_order else 9,
                            ["tournament", "nations_league", "qualifier", "friendly"].index(c["kind"]), c["name"]))
    return {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "competitions": res}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    data = build()
    if not data["competitions"]:
        print("[intl-comps] 대회 0개 — ESPN 응답 확인(기존 파일 유지)")
        return 1
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in data["competitions"]:
        e = c["editions"][-1]
        print(f"[intl-comps] {c['conf']:9s} {c['kind']:15s} {c['code']:24s} {c.get('name_ko') or c['name']} · "
              f"{e['season']} {e['status']} {e['start']}~{e['end']}" + (f" · 우승 {e['champion']}" if e.get("champion") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
