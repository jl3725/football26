"""
감독 프로필 빈칸 채우기 — 부임일(appointed)·전술 성향(style/focus), 전 리그. 매일 감독 수집 단계들 뒤에 돈다.

2026-10-23 사용자 '라이트 리그 빈칸(감독 부임일·스타일)'. 재 보니 EPL 을 뺀 12개 리그 모두 부임일·스타일이 비어 있었다
(EPL 만 예전 손 정리 값). 빅리그 감독 수집기는 매일 프로필을 새로 쓰고(빈칸으로), 라이트 리그는 이름·사진만 받는다.
  부임일 → Overview 감독 카드('부임 Dec 2019')·NETWORK 감독·재임 가중치(manager_tactics.tenure_context)
  스타일 → 감독 장기 성향 태그(manager_tactics.descriptor_tags → 영입 적합도·IDENTITY)

부임일 = FotMob 감독 경력의 지금 팀 시작일(careerItems.coach, active) → 없으면 위키데이터 구단 항목 감독(P286) 시작일(P580).
  위키데이터는 구단 항목이 늦게 고쳐져(감독 교체 미반영) 단독으론 절반쯤만 맞았다 — FotMob 이 먼저다.
스타일 = 감독 영어 위키 전술 섹션 분류(enrich_manager_profiles._classify_tactics, EPL 과 같은 규칙). 섹션 없는 감독은 빈칸.
찾은 값은 data/manager_fill_cache.json 에 감독 단위(부임일 = 구단+이름, 스타일 = 이름)로 남겨 매일 다시 받지 않는다 —
감독이 바뀌면 이름이 달라 새로 받는다. 못 찾은 것도 남기고 14일(부임일)·30일(스타일) 뒤 다시 본다.
손 정리·다른 원천 값(출처 표시 없음)은 덮지 않는다.

    python src/manager_fill.py [--league LaLiga] [--write] [--no-style]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import requests
from unidecode import unidecode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import LEAGUES, data_path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "manager_fill_cache.json"
UA = {"User-Agent": "football26-research/1.0 (manager appointed dates; contact via github)"}
WIKI = "https://en.wikipedia.org/w/api.php"
WD = "https://www.wikidata.org/w/api.php"
FM = "https://www.fotmob.com/api/data"
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
AUTO = ("fotmob", "wikidata")
RETRY_APPT, RETRY_STYLE = 14, 30
PHOTO = "https://images.fotmob.com/image_resources/playerimages/{}.png"
# 감독 교체 대조 — 같은 감독은 7일마다 다시 보고, FotMob 이 120일 안에 시작한 '지금' 감독일 때만 우리 프로필을 바꾼다
RECHECK_COACH, NEW_COACH_DAYS = 7, 120
# 축구인 문서인지(동명이인 거르기) — 라이트 리그 감독은 위키 제목이 이름 그대로라 다른 사람 문서일 수 있다
FOOTBALL_SECTIONS = re.compile(r"(manag|coach|playing) career|club career|international career", re.I)


def _get(url: str, params: dict) -> dict:
    for i in range(4):
        try:
            r = requests.get(url, params={**params, "format": "json"}, headers=UA, timeout=30)
            if r.status_code == 429:
                time.sleep(5 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            time.sleep(2 * (i + 1))
    return {}


def _fold(s: str) -> str:
    return " ".join(unidecode(str(s or "")).lower().replace("-", " ").replace(".", " ").split())


def same_person(a: str, b: str) -> bool:
    """감독 이름 맞추기 — 접은 글이 같거나, 짧은 쪽 낱말이 모두 긴 쪽에 있고 이름이 같거나(스페인식 두 성
    'Luis García' ↔ 'Luis García Plaza'), 성이 같고 이름 첫 글자가 같으면."""
    fa, fb = _fold(a), _fold(b)
    if not fa or not fb:
        return False
    if fa == fb:
        return True
    wa, wb = fa.split(), fb.split()
    short, long_ = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    if len(short) >= 2 and short[0] == long_[0] and set(short) <= set(long_):
        return True
    return wa[-1] == wb[-1] and wa[0][0] == wb[0][0]


def fmt(start: str, precision: int) -> str:
    """'2025-07-01', 정밀도 11(날)·10(달) → 'Jul 2025', 9(해) → '2025'."""
    if not start or precision < 9:
        return ""
    y, m = start[:4], int(start[5:7] or 0)
    return f"{MON[m - 1]} {y}" if precision >= 10 and 1 <= m <= 12 else y


# ── FotMob ────────────────────────────────────────────────────────────────────
def fotmob_start(prof: dict, team_id: int | None, get) -> dict | None:
    """FotMob 감독 경력에서 지금 팀 시작일. 감독 id 는 프로필(라이트 리그) 또는 팀 응답의 coach 칸(이름이 같을 때만)."""
    name = str(prof.get("name") or "")
    cid = prof.get("fotmob_id")
    if not cid and team_id:
        d = get(f"{FM}/teams?id={team_id}") or {}
        for g in ((d.get("squad") or {}).get("squad")) or []:
            if str(g.get("title")) == "coach" and g.get("members"):
                m = g["members"][0]
                if same_person(m.get("name"), name):
                    cid = m.get("id")
                break
    if not cid:
        return None
    d = get(f"{FM}/playerData?id={cid}") or {}
    if not same_person(d.get("name"), name):
        return None
    ents = ((((d.get("careerHistory") or {}).get("careerItems") or {}).get("coach") or {}).get("teamEntries")) or []
    act = [e for e in ents if e.get("active") and str(e.get("startDate") or "")[:4].isdigit()]
    hit = [e for e in act if team_id and str(e.get("teamId")) == str(team_id)] or (act if len(act) == 1 else [])
    if not hit:
        return None
    start = max(str(e["startDate"])[:10] for e in hit)
    return {"start": start, "precision": 11, "src": "fotmob"}


def team_coach(team_id, get) -> dict | None:
    d = get(f"{FM}/teams?id={team_id}") or {}
    for g in ((d.get("squad") or {}).get("squad")) or []:
        if str(g.get("title")) == "coach" and g.get("members"):
            m = g["members"][0]
            return {"id": m.get("id"), "name": str(m.get("name") or ""), "nationality": str(m.get("cname") or "")}
    return None


def active_start(coach_id, team_id, get) -> str | None:
    """그 감독 경력에 이 팀이 '지금'(active)으로 있으면 시작일."""
    d = get(f"{FM}/playerData?id={coach_id}") or {}
    ents = ((((d.get("careerHistory") or {}).get("careerItems") or {}).get("coach") or {}).get("teamEntries")) or []
    hit = [str(e["startDate"])[:10] for e in ents
           if e.get("active") and str(e.get("teamId")) == str(team_id) and str(e.get("startDate") or "")[:4].isdigit()]
    return max(hit) if hit else None


def newer_coach(prof: dict, team_id, get, today: dt.date) -> dict | None:
    """우리 프로필이 감독 교체를 놓쳤나 — FotMob 팀 감독이 다르고, 그 감독 경력에 이 팀이 '지금'·최근 NEW_COACH_DAYS 일 안
    시작이면 그렇다. FotMob 팀 감독 칸만 다른 건 믿지 않는다(Estoril·Famalicão 는 FotMob 칸이 옛 감독이었다, 2026-10-23)."""
    c = team_coach(team_id, get)
    if not c or not c["id"] or not c["name"] or same_person(c["name"], prof.get("name")):
        return None
    start = active_start(c["id"], team_id, get)
    if not start or (today - dt.date.fromisoformat(start)).days > NEW_COACH_DAYS:
        return None
    if str(prof.get("appointed_date") or "") >= start:                  # 우리 쪽 부임일이 더 늦다 — 우리가 최신
        return None
    return {"name": c["name"], "fotmob_id": c["id"], "nationality": c["nationality"], "start": start,
            "from": str(prof.get("name") or ""), "at": today.isoformat()}


def apply_override(p: dict, o: dict) -> None:
    """FotMob 이 먼저 안 감독 교체를 프로필에 — 이전 감독은 previous_*, 소개·전술은 새 감독 것(없으면 빈칸)."""
    fresh = same_person(p.get("name"), o["from"])           # 수집기가 쓴 옛 감독 프로필 위에 처음 덮는가(아니면 이미 덮인 것)
    p.update({"previous_name": o["from"], "previous_photo": p.get("photo_url", "") if fresh else p.get("previous_photo", ""),
              "change_detected_at": o["start"],
              "name": o["name"], "wiki_title": o.get("wiki_title") or o["name"], "fotmob_id": o["fotmob_id"],
              "nationality": o["nationality"] or "", "photo_url": PHOTO.format(o["fotmob_id"]),
              "bio_ko": o.get("bio_ko", ""), "bio_source": o.get("bio_source", ""), "tactics_ko": o.get("tactics_ko", ""),
              "style": "", "focus": "", "formation": "",
              "appointed": fmt(o["start"], 11), "appointed_date": o["start"], "appointed_source": "fotmob",
              "name_source": "fotmob"})


def _due(at: str, days: int, today: dt.date) -> bool:
    try:
        return not at or (today - dt.date.fromisoformat(at)).days >= days
    except ValueError:
        return True


def override_bio(o: dict, today: dt.date) -> None:
    """새 감독 소개 — 라이트 리그 감독 소개와 같은 방법(이름 문서 후보 → 축구인 소개만, 한글 위키 → 영어 위키 번역).
    결과는 교체 기록에 남겨 매일 다시 받지 않는다(못 찾으면 30일 뒤 다시)."""
    if o.get("bio_ko") or not _due(o.get("bio_at", ""), RETRY_STYLE, today):
        return
    from enrich_manager_profiles import enrich_one  # noqa: PLC0415
    from lite_league import _football_bio  # noqa: PLC0415
    o["bio_at"] = today.isoformat()
    for title in (f"{o['name']} (football manager)", f"{o['name']} (footballer)", o["name"]):
        try:
            e = enrich_one({"name": o["name"], "wiki_title": title})
        except Exception:  # noqa: BLE001  (문서 없음·네트워크)
            continue
        if _football_bio(str(e.get("bio_ko") or "")):
            o.update({k: e[k] for k in ("bio_ko", "bio_source", "tactics_ko") if e.get(k)})
            o["wiki_title"] = title
            return


# ── 위키데이터 ────────────────────────────────────────────────────────────────
def club_titles(league: str) -> dict[str, str]:
    """{우리 구단 표기: 영어 위키 문서 제목} — 위키 스쿼드 수집과 같은 순서(data/wiki_titles.json 우선)."""
    import pandas as pd  # noqa: PLC0415
    p = data_path("standings", league)
    if not p.exists():
        return {}
    cache = {}
    for f in (ROOT / "data" / "wiki_titles.json", ROOT / "data" / "team_profiles.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for k, v in d.items():
            t = v if isinstance(v, str) else (v or {}).get("wiki_title")
            if t:
                cache.setdefault(k, t)
    return {s: cache[s] for s in pd.read_csv(p)["squad"].astype(str) if cache.get(s)}


def qids(titles: list[str]) -> dict[str, str]:
    """{문서 제목: 위키데이터 id} — 넘겨주기·표기 정규화까지 따라간다(50개씩)."""
    out: dict[str, str] = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        d = _get(WIKI, {"action": "query", "prop": "pageprops", "ppprop": "wikibase_item", "redirects": 1, "titles": "|".join(chunk)})
        q = d.get("query") or {}
        back = {x["to"]: x["from"] for x in (q.get("normalized") or []) + (q.get("redirects") or [])}
        for pg in (q.get("pages") or {}).values():
            qid = (pg.get("pageprops") or {}).get("wikibase_item")
            if not qid:
                continue
            t = pg.get("title")
            while t in back and t not in chunk:
                t = back[t]
            out[t] = qid
    return out


def _time(snak: dict) -> tuple[str, int] | None:
    v = ((snak or {}).get("datavalue") or {}).get("value") or {}
    t = str(v.get("time") or "")
    if len(t) < 11:
        return None
    return t[1:11], int(v.get("precision") or 11)


def current_coaches(club_qids: list[str]) -> dict[str, list[dict]]:
    """{구단 id: [{coach, start, precision, name}]} — P286 중 끝난 날(P582)이 없는 기록(지금 감독)."""
    stm: dict[str, list[dict]] = {}
    coach_ids: set[str] = set()
    for i in range(0, len(club_qids), 50):
        d = _get(WD, {"action": "wbgetentities", "ids": "|".join(club_qids[i:i + 50]), "props": "claims"})
        for q, ent in (d.get("entities") or {}).items():
            for c in ((ent.get("claims") or {}).get("P286") or []):
                quals = c.get("qualifiers") or {}
                if c.get("rank") == "deprecated" or quals.get("P582"):
                    continue
                cid = (((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}).get("id")
                st = _time((quals.get("P580") or [{}])[0]) if quals.get("P580") else None
                if cid:
                    stm.setdefault(q, []).append({"coach": cid, "start": st[0] if st else "", "precision": st[1] if st else 0})
                    coach_ids.add(cid)
    names: dict[str, str] = {}
    ids = sorted(coach_ids)
    for i in range(0, len(ids), 50):
        # 언어 제한 없이 — 에레디비시 감독 다수는 영어 이름표가 없고 네덜란드어·'mul' 만 있다
        d = _get(WD, {"action": "wbgetentities", "ids": "|".join(ids[i:i + 50]), "props": "labels"})
        for q, ent in (d.get("entities") or {}).items():
            lab = ent.get("labels") or {}
            names[q] = next((lab[k]["value"] for k in ("en", "mul") if k in lab), "") or \
                next((v["value"] for v in lab.values()), "")
    for v in stm.values():
        for x in v:
            x["name"] = names.get(x["coach"], "")
    return stm


def pick(coaches: list[dict], name: str) -> dict | None:
    """지금 감독 기록 중 프로필 이름과 같은 사람(없으면 None — 위키데이터가 늦었거나 다른 사람)."""
    hit = [c for c in coaches if same_person(c.get("name", ""), name) and c.get("start")]
    return max(hit, key=lambda c: c["start"]) if hit else None


def wikidata_starts(league: str, want: dict[str, str]) -> dict[str, dict]:
    """{구단: 감독 이름} → {구단: {start, precision, src}} — 구단 항목 P286. 종합 스포츠 클럽(갈라타사라이 등)은
    축구팀 문서 안내문으로 한 번 더(한꺼번에)."""
    titles = {sq: t for sq, t in club_titles(league).items() if sq in want}
    if not titles:
        return {}
    tq = qids(list(dict.fromkeys(titles.values())))
    co = current_coaches(list(dict.fromkeys(tq.values())))
    out = {sq: c for sq, t in titles.items() if (c := pick(co.get(tq.get(t, ""), []), want[sq]))}
    miss = {sq: t for sq, t in titles.items() if sq not in out}
    if miss:
        import club_rivals  # noqa: PLC0415
        import fetch_wiki_squads as wiki  # noqa: PLC0415
        try:
            texts = wiki.wikitexts(list(dict.fromkeys(miss.values())))
        except requests.RequestException:
            texts = {}
        ft = {sq: m.group(1).strip() for sq, t in miss.items()
              if (m := club_rivals.FOOTBALL_ARTICLE.search((texts.get(t) or "")[:2500]))}
        if ft:
            fq = qids(list(dict.fromkeys(ft.values())))
            fco = current_coaches(list(dict.fromkeys(fq.values())))
            out.update({sq: c for sq, t in ft.items() if (c := pick(fco.get(fq.get(t, ""), []), want[sq]))})
    return {sq: {"start": c["start"], "precision": c["precision"], "src": "wikidata"} for sq, c in out.items()}


# ── 스타일 ────────────────────────────────────────────────────────────────────
def wiki_style(title: str) -> tuple[str, str] | None:
    """감독 영어 위키 전술 섹션 → (style, focus). 문서가 없거나 축구인 문서가 아니면 ('','')."""
    import enrich_manager_profiles as emp  # noqa: PLC0415
    try:
        secs = emp._wiki_sections("en", title)
    except Exception:  # noqa: BLE001  (문서 없음·네트워크)
        return None
    if not any(FOOTBALL_SECTIONS.search(str(s.get("line") or "")) for s in secs):
        return "", ""
    idx = [s.get("index") for s in secs if emp._MGR_SECTION_RE.search(str(s.get("line") or ""))][:3]
    texts = []
    for i in idx:
        try:
            texts.append(emp._section_text("en", title, i))
        except Exception:  # noqa: BLE001
            continue
    return emp._classify_tactics(" ".join(texts))


# ── 채우기 ────────────────────────────────────────────────────────────────────
def _fresh(rec: dict | None, days: int, today: dt.date) -> bool:
    if not rec:
        return False
    if rec.get("val") or rec.get("style"):
        return True
    try:
        return (today - dt.date.fromisoformat(rec.get("at", ""))).days < days
    except ValueError:
        return False


def fill(league: str, cache: dict, team_ids: dict, get, style: bool = True, write: bool = False) -> dict:
    path = data_path("manager_profiles", league, ext="json")
    if not path.exists():
        return {"appt": 0, "appt_miss": 0, "style": 0, "override": 0}
    profiles = json.loads(path.read_text(encoding="utf-8"))
    today = dt.date.today()
    ca, cs = cache.setdefault("appointed", {}), cache.setdefault("style", {})
    ovr, chk = cache.setdefault("override", {}), cache.setdefault("coach_check", {})
    n = {"appt": 0, "appt_miss": 0, "style": 0, "override": 0}
    def due(at, days):
        return _due(at, days, today)
    # 0) 감독 교체를 우리 수집기(위키)보다 FotMob 이 먼저 안 팀 — 'Kortrijk: Christophe Lepoint' 가 FotMob 엔 10/9 부임
    #    Daniel Beichler 였다(2026-10-23). 캐시로 매일 다시 입히고, 위키가 따라오면(수집기 이름이 바뀌면) 그만둔다
    for sq, p in profiles.items():
        tid = team_ids.get(sq)
        o = ovr.get(sq)
        # 프로필이 이미 우리가 덮어 쓴 새 감독이면(수집기가 안 돌았거나 실패한 날) 계속 덮는다
        mine = bool(o) and p.get("name_source") == "fotmob" and same_person(p.get("name"), o["name"])
        if o and not mine and not same_person(p.get("name"), o["from"]):
            ovr.pop(sq)                                  # 수집기가 새 감독을 따라왔거나 또 다른 사람 — 덮기 끝
        elif o and (not due(o["at"], RECHECK_COACH) or (tid and active_start(o["fotmob_id"], tid, get))):
            if due(o["at"], RECHECK_COACH):
                o["at"] = today.isoformat()
            override_bio(o, today)
            apply_override(p, o)
            n["override"] += 1
            continue
        elif o:
            ovr.pop(sq)                                  # FotMob 에서도 더는 지금 감독이 아니다
        if p.get("fotmob_id") or not tid or not p.get("name"):
            continue                                     # 라이트 리그 프로필은 원래 FotMob 감독
        key = f"{sq}|{_fold(p['name'])}"
        if not due(chk.get(key, ""), RECHECK_COACH):
            continue
        chk[key] = today.isoformat()
        o = newer_coach(p, tid, get, today)
        if o:
            ovr[sq] = o
            override_bio(o, today)
            apply_override(p, o)
            n["override"] += 1
            print(f"  {league:18} {sq:24} 감독 교체(FotMob): {o['from']} → {o['name']} ({o['start']})")
    # 1) 부임일 — 캐시 → FotMob → 위키데이터(못 찾은 것만 한꺼번에)
    todo = {sq: p for sq, p in profiles.items()
            if p.get("name") and not (p.get("appointed") and p.get("appointed_source") not in AUTO)}
    need: dict[str, str] = {}
    for sq, p in todo.items():
        key = f"{sq}|{_fold(p['name'])}"
        if _fresh(ca.get(key), RETRY_APPT, today):
            continue
        r = fotmob_start(p, team_ids.get(sq), get)
        if r:
            ca[key] = {"val": fmt(r["start"], r["precision"]), "date": r["start"], "src": r["src"], "at": today.isoformat()}
        else:
            need[sq] = str(p["name"])
        time.sleep(0.3)
    if need:
        wd = wikidata_starts(league, need)
        for sq, name in need.items():
            r = wd.get(sq)
            ca[f"{sq}|{_fold(name)}"] = ({"val": fmt(r["start"], r["precision"]), "date": r["start"], "src": r["src"],
                                          "at": today.isoformat()} if r else {"val": "", "at": today.isoformat()})
    for sq, p in todo.items():
        rec = ca.get(f"{sq}|{_fold(p['name'])}") or {}
        if not rec.get("val"):
            n["appt_miss"] += 1
            continue
        if p.get("appointed") != rec["val"]:
            p["appointed"], p["appointed_date"], p["appointed_source"] = rec["val"], rec["date"], rec["src"]
            n["appt"] += 1
            print(f"  {league:18} {sq:24} {p['name']:24} 부임 {rec['val']} ({rec['src']})")
    # 2) 스타일 — 감독 이름 단위(감독 속성, 구단을 옮겨도 따라간다)
    for sq, p in profiles.items() if style else ():
        if not p.get("name") or (p.get("style") and p.get("focus")):
            continue
        key = _fold(p.get("wiki_title") or p["name"])
        if not _fresh(cs.get(key), RETRY_STYLE, today):
            r = wiki_style(str(p.get("wiki_title") or p["name"]))
            if r is None:
                continue
            cs[key] = {"style": r[0], "focus": r[1], "at": today.isoformat()}
            time.sleep(0.3)
        rec = cs.get(key) or {}
        if rec.get("style"):
            p["style"], p["focus"], p["style_source"] = rec["style"], rec["focus"], "en-wiki"
            n["style"] += 1
            print(f"  {league:18} {sq:24} {p['name']:24} 스타일 {rec['style']}")
    if write and (n["appt"] or n["style"] or n["override"]):
        # 원래 들여쓰기 그대로(라이트 리그 수집기는 1칸) — 다르면 매일 파일 전체가 바뀐 것처럼 커밋된다
        raw = path.read_text(encoding="utf-8")
        m = re.match(r"\{\r?\n( +)", raw)
        path.write_text(json.dumps(profiles, ensure_ascii=False, indent=len(m.group(1)) if m else 2)
                        + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")
    return n


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--no-style", action="store_true")
    a = ap.parse_args()
    from functools import lru_cache  # noqa: PLC0415

    from fetch_fotmob_ratings import _get  # noqa: PLC0415
    fm_get = lru_cache(maxsize=None)(_get)              # 같은 팀·감독 응답은 한 실행에 한 번(교체 대조·부임일이 같이 씀)
    try:
        from news_wires import fotmob_team_ids  # noqa: PLC0415
        team_ids = fotmob_team_ids()
    except Exception as e:  # noqa: BLE001  (팀 id 없이도 라이트 리그·위키데이터는 된다)
        print(f"[manager_fill] FotMob 팀 id 실패: {type(e).__name__}")
        team_ids = {}
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    tot = {"appt": 0, "appt_miss": 0, "style": 0, "override": 0}
    for lg in ([a.league] if a.league else list(LEAGUES)):
        r = fill(lg, cache, team_ids, fm_get, style=not a.no_style, write=a.write)
        tot = {k: tot[k] + r[k] for k in tot}
        if a.write:                                     # 리그마다 저장 — 중간에 끊겨도 받은 만큼은 남는다
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"manager_fill: 부임일 새로 {tot['appt']} · 못 찾음 {tot['appt_miss']} · 스타일 새로 {tot['style']} · "
          f"FotMob 감독 교체 {tot['override']} ({dt.date.today()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
