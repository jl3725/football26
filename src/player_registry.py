"""
선수 레지스트리 — 원천마다 다른 이름 표기를 한 사람(기준 신원)으로 묶는다.

원천: players_full(FBref·Sofascore 리그 출전자, 기준 표기) · TM 계약 명단(팀 전원 + tm_id) · TM 부상(tm_id) ·
위키 스쿼드 · ESPN 라인업·교체(리그+컵) · 선수 이벤트(골·도움) · 이적(영입).
2026-10-15 측정: 같은 팀 안에서도 ESPN 이름의 26%, 위키의 42% 가 기준 표기와 달랐다
('Alisson Becker'↔'Alisson', 'Josh King'↔'Joshua King', 'Frank Anguissa'↔'Andre-Frank Zambo Anguissa').
예전엔 화면마다 제각각 이름 맞추기(NameIndex·_espn_name·성+이니셜)를 해서 같은 선수가 어디선 잡히고 어디선 빠졌다.

규칙(같은 팀 후보 안, 점수가 가장 높고 2등과 동점이 아닐 때만): 정확 100 · 같은 tm_id 99 · 어순만 다름·붙여 쓰기 95 ·
한쪽 이름이 다른 쪽에 포함 85 · 성 같고 이름 호환(앞 3글자·애칭·유사) 80 · 성 같고 이니셜만('G. Magalhães') 70 ·
한 단어 이름이 상대 이름의 단어 60. 이름이 서로 다른 사람(Raúl ↔ Rubén García)은 성이 같아도 0.
수동 지정은 data/name_aliases.csv(squad, alias, canonical)가 가장 먼저.

출력: data/player_registry[_리그]_<시즌>.csv — squad, entity, canonical, tm_id, alias, source, score
      data/eval/name_audit.json — 원천별 연결률, 기준 명단 밖에서 실제로 뛴 '고아' 이름(확인 필요)
사용: python src/player_registry.py            # 현재·직전 시즌, 8개 리그
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
from unidecode import unidecode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leagues import LEAGUES, SEASON_START, data_path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NICK = {"charly": "carlos", "nico": "nicolas", "josh": "joshua", "danny": "daniel", "dan": "daniel", "alex": "alexander",
        "sasha": "alexander", "emi": "emiliano", "kike": "enrique", "pepe": "jose", "manu": "manuel", "fran": "francisco",
        "javi": "javier", "rafa": "rafael", "nacho": "ignacio", "dani": "daniel", "matty": "matthew", "matt": "matthew",
        "tom": "thomas", "tommy": "thomas", "ben": "benjamin", "joe": "joseph", "jon": "jonathan", "jonny": "jonathan",
        "mike": "michael", "mikey": "michael", "chris": "christopher", "nick": "nicholas", "will": "william",
        "billy": "william", "jamie": "james", "jim": "james", "andy": "andrew", "tony": "anthony", "sam": "samuel",
        "max": "maximilian", "freddie": "frederick", "ollie": "oliver", "zak": "zachary", "edu": "eduardo",
        "pablo": "pablo", "gabri": "gabriel", "gabi": "gabriel", "toni": "antonio", "juanma": "juan manuel"}
PARTICLES = {"van", "de", "der", "den", "da", "dos", "das", "do", "di", "del", "la", "le", "von", "el", "al", "bin", "ben"}


def norm(s) -> str:
    return " ".join(unidecode(str(s or "")).lower().replace("-", " ").replace(".", " ").replace("'", "").split())


def _core(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in PARTICLES] or tokens


def _first_ok(a: str, b: str) -> bool:
    """이름(first name) 호환 — 같음 · 앞 3글자 같고 한쪽이 다른 쪽으로 시작 · 애칭 · 철자 변형(Mykhaylo↔Mykhailo)."""
    if a == b:
        return True
    if len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a)):
        return True
    if a[:3] == b[:3] and len(a) >= 3 and len(b) >= 3:
        return True
    if NICK.get(a) == b or NICK.get(b) == a or (NICK.get(a) and NICK.get(a) == NICK.get(b)):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


def score(src: str, cand: str) -> int:
    a, b = norm(src), norm(cand)
    if not a or not b:
        return 0
    if a == b:
        return 100
    if a.replace(" ", "") == b.replace(" ", ""):              # 'Jay Da Silva' ↔ 'Jay Dasilva', 'Del Prato' ↔ 'Delprato'
        return 95
    ta, tb = _core(a.split()), _core(b.split())
    if sorted(ta) == sorted(tb):
        return 95
    sa, sb = set(ta), set(tb)
    if len(ta) >= 2 and len(tb) >= 2 and (sa <= sb or sb <= sa) and (ta[-1] == tb[-1] or len(sa & sb) >= 2):
        return 85
    if len(ta) >= 2 and len(tb) >= 2 and (ta[-1] == tb[-1] or (len(ta[-1]) >= 4 and ta[-1] in sb)
                                          or (len(tb[-1]) >= 4 and tb[-1] in sa)):
        fa, fb = ta[0], tb[0]
        if len(fa) == 1 or len(fb) == 1:
            return 70 if fa[0] == fb[0] else 0
        return 80 if _first_ok(fa, fb) else 0
    if len(ta) == 1 and len(ta[0]) >= 4 and ta[0] in sb:
        return 60
    if len(tb) == 1 and len(tb[0]) >= 4 and tb[0] in sa:
        return 60
    return 0


def best_match(name: str, cands: dict[str, str]) -> tuple[str | None, int]:
    """cands: {후보 이름: entity}. 1등 점수가 60 이상이고 2등(다른 entity)과 같지 않을 때만."""
    scored = sorted(((score(name, c), e) for c, e in cands.items()), key=lambda x: -x[0])
    if not scored or scored[0][0] < 60:
        return None, 0
    top, ent = scored[0]
    if any(s == top and e != ent for s, e in scored[1:]):
        return None, -top                                       # 동점 — 애매해서 붙이지 않음
    return ent, top


def _read(stem: str, lg: str, season: str, cols=None) -> pd.DataFrame | None:
    p = data_path(stem, lg, season)
    if not p.exists():
        return None
    try:
        return pd.read_csv(p, usecols=lambda c: cols is None or c in cols, low_memory=False)
    except (ValueError, OSError):
        return None


def _tmid(v) -> str:
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return ""


def _manual() -> dict[tuple[str, str], str]:
    p = ROOT / "data" / "name_aliases.csv"
    if not p.exists():
        return {}
    d = pd.read_csv(p, comment="#")
    return {(str(r.squad), norm(r.alias)): str(r.canonical) for r in d.itertuples()}


def build(lg: str, season: str) -> tuple[pd.DataFrame, dict]:
    ents: dict[str, dict] = {}                                  # entity → {squad, canonical, tm_id}
    names: dict[str, dict[str, str]] = defaultdict(dict)        # squad → {이름: entity}
    rows: list[dict] = []
    manual = _manual()

    def add_entity(eid, squad, canonical, tm_id, source):
        ents.setdefault(eid, {"squad": squad, "canonical": canonical, "tm_id": tm_id})
        names[squad].setdefault(canonical, eid)
        rows.append({"squad": squad, "entity": eid, "alias": canonical, "source": source, "score": 100})

    # 1) 기준: players_full(리그 출전자) — 표기는 이것을 따른다
    pf = _read("players_full", lg, season, {"player", "squad", "tm_id"})
    by_tm: dict[str, str] = {}
    if pf is not None:
        for r in pf.itertuples():
            t = _tmid(getattr(r, "tm_id", None))
            eid = f"tm{t}" if t else f"pf:{r.squad}:{norm(r.player)}"
            if t:
                by_tm[t] = eid
            add_entity(eid, r.squad, str(r.player), t, "players_full")

    # 2) TM 계약 명단(팀 전원) · TM 부상 — tm_id 로 먼저, 없으면 이름 규칙, 그래도 없으면 새 신원
    for stem, idcol in (("transfermarkt_contracts", "tm_id"), ("transfermarkt_injuries", "tm_player_id")):
        d = _read(stem, lg, season, {"player", "squad", idcol})
        if d is None:
            continue
        for r in d.itertuples():
            sq, nm, t = str(r.squad), str(r.player), _tmid(getattr(r, idcol, None))
            eid = by_tm.get(t) if t else None
            sc = 99 if eid else 0
            if not eid:
                eid, sc = best_match(nm, names.get(sq, {}))
            if not eid:
                eid = f"tm{t}" if t else f"tmn:{sq}:{norm(nm)}"
                if t:
                    by_tm[t] = eid
                add_entity(eid, sq, nm, t, stem)
                continue
            names[sq].setdefault(nm, eid)
            rows.append({"squad": sq, "entity": eid, "alias": nm, "source": stem, "score": sc})

    # 3) 그 밖의 원천 — 이름 규칙으로 별칭. 실제로 뛴 기록(라인업·교체·이벤트)인데 못 찾으면 '고아'로 새 신원
    audit = defaultdict(lambda: {"total": 0, "exact": 0, "rule": 0, "ambiguous": 0, "orphan": 0, "orphans": []})
    srcs = [("wiki_squads", ["player"]), ("espn_lineups", ["player"]), ("espn_lineups_cups", ["player"]),
            ("espn_subs", ["player_in", "player_out"]), ("espn_subs_cups", ["player_in", "player_out"]),
            ("match_events", ["player"])]
    played = {"espn_lineups", "espn_lineups_cups", "espn_subs", "espn_subs_cups", "match_events"}
    for stem, cols in srcs:
        d = _read(stem, lg, season)
        if d is not None and stem.startswith("espn_subs") and "squad" not in d.columns:
            from player_names import with_squad  # noqa: PLC0415
            d = with_squad(d, _read(stem.replace("espn_subs", "espn_lineups"), lg, season))
        if d is None or "squad" not in d.columns:
            continue
        if stem == "match_events" and "type" in d.columns:
            d = d[~d["type"].isin(["og", "none"])]               # 자책골은 상대 팀 선수
        if stem.startswith("espn_lineups") and "starter" in d.columns:
            starts = d[d["starter"].astype(str).str.lower().isin(["true", "1", "1.0"])].groupby(["squad", "player"]).size().to_dict()
        else:
            starts = {}
        seen = set()
        for c in cols:
            if c not in d.columns:
                continue
            for sq, nm in zip(d["squad"].astype(str), d[c].astype(str)):
                if sq in ("None", "nan"):
                    continue
                nm = re.split(r" because | due to ", nm)[0].strip()
                if not nm or nm == "nan" or (sq, nm) in seen:
                    continue
                seen.add((sq, nm))
                a = audit[stem]
                a["total"] += 1
                eid = manual.get((sq, norm(nm)))
                if eid:
                    eid = names.get(sq, {}).get(eid) or eid
                    sc = 100
                else:
                    eid, sc = best_match(nm, names.get(sq, {}))
                if eid:
                    a["exact" if sc == 100 else "rule"] += 1
                    names[sq].setdefault(nm, eid)
                    rows.append({"squad": sq, "entity": eid, "alias": nm, "source": stem, "score": sc})
                    continue
                if sc < 0:
                    a["ambiguous"] += 1
                if stem in played:
                    a["orphan"] += 1
                    n_st = int(starts.get((sq, nm), 0))
                    a["orphans"].append({"squad": sq, "name": nm, "starts": n_st})
                    add_entity(f"esp:{sq}:{norm(nm)}", sq, nm, "", stem)
    out = pd.DataFrame(rows)
    if not out.empty:
        meta = pd.DataFrame([{"entity": e, "canonical": v["canonical"], "tm_id": v["tm_id"]} for e, v in ents.items()])
        out = out.merge(meta, on="entity", how="left").drop_duplicates(["squad", "alias", "entity"])
        out = out[["squad", "entity", "canonical", "tm_id", "alias", "source", "score"]]
    for a in audit.values():
        a["orphans"] = sorted(a["orphans"], key=lambda x: -x["starts"])[:25]
    return out, dict(audit)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    report = {}
    for season in (f"{SEASON_START}_{SEASON_START + 1}", f"{SEASON_START - 1}_{SEASON_START}"):
        for lg in LEAGUES:
            reg, audit = build(lg, season)
            if reg.empty:
                continue
            reg.to_csv(data_path("player_registry", lg, season), index=False)
            report[f"{lg} {season}"] = audit
            linked = sum(a["exact"] + a["rule"] for a in audit.values())
            tot = sum(a["total"] for a in audit.values()) or 1
            orph = sum(a["orphan"] for a in audit.values())
            print(f"[registry] {lg} {season}: 신원 {reg['entity'].nunique()} · 별칭 {len(reg)} · 원천 이름 연결 {linked}/{tot}"
                  f"({linked / tot:.0%}) · 고아 {orph}")
    import datetime as dt  # noqa: PLC0415
    report["_meta"] = {"date": dt.date.today().isoformat(), "season": f"{SEASON_START}_{SEASON_START + 1}"}
    (ROOT / "data" / "eval").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "eval" / "name_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
