"""
팀 지식그래프(NETWORK 탭) — 한 팀을 중심으로 선수·클럽·국가·이적·출전 관계를 엮어 5개 렌즈와 근거 있는 인사이트를 만든다.

  LEADERSHIP  주장단(위키 스쿼드 표) + 영향력(출전 비중·연결 중심성·근속·경험·대표팀) → 리더십 코어, 오늘의 완장
  CHEMISTRY   실제로 함께 그라운드에 있던 시간(라인업·교체)으로 만든 선수 관계망 — 허브·듀오·삼각편대
  ORIGINS     스쿼드가 어떻게 만들어졌나 — 입단 연도 타임라인 · 영입 방식(유스·이적·임대·자유) · 출신 리그
  NATIONS     국적 → 국가(FIFA 랭킹·국기) · 2026 월드컵 명단
  LINKS       클럽 관계망 — 이적(영입·방출) · 떠난 선수가 지금 뛰는 클럽 · 이적설

운영(Render)에선 Neo4j(AuraDB 무료)가 잠들면 그래프가 비었다. 그래서 같은 스키마(PLAYS_FOR·TEAMMATE_OF·
REPRESENTS·TransferEvent·RUMORED_WITH)를 API 가 원천 CSV 로 그 자리에서 엮는다 — 외부 그래프 DB 없이 항상 동작.
인사이트는 그래프 경로를 근거(evidence)로 붙인 템플릿 문장이다(생성형 AI·유료 API 를 쓰지 않음).
"""
from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict

from unidecode import unidecode

ROLE_LABEL = {1: "C", 2: "VC", 3: "3C", 4: "4C"}
ROLE_KO = {1: "주장", 2: "부주장", 3: "3번째 주장", 4: "4번째 주장"}
ACQ_KO = {"academy": "유스", "transfer": "이적", "loan": "임대", "free": "자유계약", "return": "임대 복귀",
          "signed": "영입(이전)", "unknown": "미상"}


def norm(n) -> str:
    return " ".join(unidecode(str(n or "")).lower().replace("-", " ").replace(".", " ").split())


def pkey(n) -> tuple[str, str]:
    t = norm(n).split()
    return (t[-1], t[0][:1]) if t else ("", "")


class NameIndex:
    """전체 이름 → (성, 이름 첫 글자) → (성, 유일할 때) 순으로 찾는다 — 위키 'Vinícius Júnior' ↔ 'Vinicius Júnior'."""

    def __init__(self, names):
        self.full, self.pk, self.last = {}, defaultdict(list), defaultdict(list)
        for n in names:
            self.full.setdefault(norm(n), n)
            self.pk[pkey(n)].append(n)
            t = norm(n).split()
            if t:
                self.last[t[-1]].append(n)

    def find(self, name):
        k = norm(name)
        if k in self.full:
            return self.full[k]
        hits = self.pk.get(pkey(name), [])
        if len(hits) == 1:
            return hits[0]
        t = k.split()
        if len(t) == 1:                                   # 'Rodri' 처럼 한 단어 이름
            hits = self.last.get(t[0], [])
            return hits[0] if len(hits) == 1 else None
        return None


def _years_since(date_s, today: dt.date) -> float | None:
    try:
        d = dt.date.fromisoformat(str(date_s)[:10])
    except ValueError:
        return None
    return max(0.0, (today - d).days / 365.25)


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


# ── CHEMISTRY ─────────────────────────────────────────────────────────
def chemistry_graph(games: dict, roster_names: list[str], min_edge: float = 90.0, max_edges: int = 70) -> dict:
    """{nodes:[{name, minutes, degree, hub_rank}], edges:[{a,b,minutes,matches}], strength:{name: 0~1}}."""
    idx = NameIndex(roster_names)
    played: dict[str, float] = defaultdict(float)
    pair_m: dict[tuple[str, str], float] = defaultdict(float)
    pair_n: dict[tuple[str, str], int] = defaultdict(int)
    for g in games.values():
        on = {}
        for pl, (a, b) in g.items():
            nm = idx.find(pl) or pl
            on[nm] = (a, b)
            played[nm] += b - a
        names = sorted(on)
        for i, x in enumerate(names):
            for y in names[i + 1:]:
                o = min(on[x][1], on[y][1]) - max(on[x][0], on[y][0])
                if o > 0:
                    pair_m[(x, y)] += o
                    pair_n[(x, y)] += 1
    edges = [{"a": a, "b": b, "minutes": round(m), "matches": pair_n[(a, b)]}
             for (a, b), m in pair_m.items() if m >= min_edge]
    edges.sort(key=lambda e: -e["minutes"])
    edges = edges[:max_edges]
    deg: dict[str, float] = defaultdict(float)
    for e in edges:
        deg[e["a"]] += e["minutes"]
        deg[e["b"]] += e["minutes"]
    mx = max(deg.values(), default=1.0) or 1.0
    nodes = [{"name": n, "minutes": round(m), "degree": round(deg.get(n, 0) / mx, 3)}
             for n, m in sorted(played.items(), key=lambda x: -x[1]) if m >= 45]
    order = sorted(nodes, key=lambda n: -n["degree"])
    for i, n in enumerate(order):
        n["hub_rank"] = i + 1
    return {"nodes": nodes, "edges": edges, "strength": {n["name"]: n["degree"] for n in nodes},
            "minutes": {n["name"]: n["minutes"] for n in nodes}, "hub_rank": {n["name"]: n["hub_rank"] for n in nodes}}


# ── LEADERSHIP ────────────────────────────────────────────────────────
def leadership(players: list[dict], chem: dict, today: dt.date) -> dict:
    """주장단 + 영향력 코어. players 항목: name, captain_rank, minutes, age, joined, wc, injured, ..."""
    mins = chem.get("minutes", {})
    max_min = max([p.get("minutes") or 0 for p in players] + [1])
    scored = []
    for p in players:
        tenure = _years_since(p.get("joined"), today)
        comp = {
            "minutes": _clamp((p.get("minutes") or mins.get(p["name"], 0)) / max_min),
            "hub": chem.get("strength", {}).get(p["name"], 0.0),
            "tenure": _clamp((tenure or 0) / 6.0),
            "experience": _clamp(((p.get("age") or 0) - 21) / 10.0),
            "international": 1.0 if p.get("wc") else 0.0,
            "armband": {1: 1.0, 2: 0.75, 3: 0.5, 4: 0.4}.get(p.get("captain_rank") or 0, 0.0),
        }
        w = {"minutes": 0.28, "hub": 0.24, "tenure": 0.16, "experience": 0.10, "international": 0.10, "armband": 0.12}
        score = sum(comp[k] * w[k] for k in w)
        why = []
        if p.get("captain_rank"):
            why.append(ROLE_KO[p["captain_rank"]])
        if comp["hub"] >= 0.8:
            why.append("연결 허브")
        if comp["minutes"] >= 0.85:
            why.append("출전 최상위")
        if tenure is not None and tenure >= 4:
            why.append(f"입단 {int(tenure)}년차")
        if p.get("wc"):
            why.append("월드컵 명단")
        if (p.get("age") or 0) >= 30:
            why.append("베테랑")
        scored.append({**p, "influence": round(score * 100), "components": {k: round(v, 2) for k, v in comp.items()},
                       "tenure": None if tenure is None else round(tenure, 1), "why": why})
    scored.sort(key=lambda x: -x["influence"])
    caps = sorted([p for p in scored if p.get("captain_rank")], key=lambda p: p["captain_rank"])
    armband = next((p for p in caps if not p.get("injured") and p.get("in_squad", True)), None)
    return {"captains": [{**p, "label": ROLE_LABEL[p["captain_rank"]], "role_ko": ROLE_KO[p["captain_rank"]]}
                         for p in caps],
            "armband": armband["name"] if armband else None,
            "core": scored[:7], "influence": {p["name"]: p["influence"] for p in scored}}


# ── ORIGINS ───────────────────────────────────────────────────────────
_YOUTH = re.compile(r"\b(u1[5-9]|u2[0-3]|ii|b|youth|academy|reserves|jong|castilla|primavera|sub-?\d+)\b", re.I)


def acquisition(p: dict, tin: dict | None, team: str, today: dt.date) -> dict:
    """{acq, from_club, fee_text, fee_eur, year} — 최근 두 이적창 기록 우선, 없으면 입단일·나이로 추정."""
    joined = p.get("joined")
    year = None
    try:
        year = int(str(joined)[:4]) if joined else None
    except ValueError:
        year = None
    if tin:
        ft = str(tin.get("fee_text") or "").lower()
        club = str(tin.get("club") or "")
        fee = tin.get("fee_eur")
        fee = float(fee) if fee is not None and fee == fee else None
        if "end of loan" in ft or "loan return" in ft:
            acq = "return"
        elif "loan" in ft:
            acq = "loan"
        elif "free" in ft:
            acq = "free"
        elif fee and fee > 0:
            acq = "transfer"
        elif _YOUTH.search(club) or club.lower().startswith(team.lower()):
            acq = "academy"
        else:
            acq = "transfer"
        yr = year or (int(tin["season_id"]) if str(tin.get("season_id") or "").isdigit() else None)
        return {"acq": acq, "from_club": club or None, "fee_text": tin.get("fee_text"), "fee_eur": fee, "year": yr}
    age = p.get("age")
    if year and age:
        at_join = age - (today.year - year)
        if at_join <= 18.5:
            return {"acq": "academy", "from_club": None, "fee_text": None, "fee_eur": None, "year": year}
    prev = p.get("prev_squad")
    return {"acq": "signed" if year else "unknown",
            "from_club": prev if prev and prev != team else None, "fee_text": None, "fee_eur": None, "year": year}


def origins(players: list[dict], club_league) -> dict:
    by_year: dict[int, list[str]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    src: dict[str, dict] = {}
    for p in players:
        a = p.get("origin") or {}
        counts[a.get("acq", "unknown")] += 1
        if a.get("year"):
            by_year[a["year"]].append(p["name"])
        if a.get("acq") == "academy":
            lg = "ACADEMY"
        elif a.get("from_club"):
            lg = club_league(a["from_club"]) or "OTHER"
        else:
            continue
        s = src.setdefault(lg, {"league": lg, "n": 0, "fee_eur": 0.0, "players": []})
        s["n"] += 1
        s["fee_eur"] += a.get("fee_eur") or 0.0
        s["players"].append(p["name"])
    return {"timeline": [{"year": y, "players": by_year[y]} for y in sorted(by_year)],
            "acq": dict(counts), "sources": sorted(src.values(), key=lambda s: (-s["n"], -s["fee_eur"]))}


# ── NATIONS ───────────────────────────────────────────────────────────
def nations(players: list[dict]) -> dict:
    by: dict[str, dict] = {}
    for p in players:
        n = p.get("nation")
        if not n:
            continue
        c = by.setdefault(n["name"], {**n, "players": [], "wc": 0})
        c["players"].append(p["name"])
        c["wc"] += 1 if p.get("wc") else 0
    lst = sorted(by.values(), key=lambda c: (-len(c["players"]), c.get("rank") or 999))
    return {"countries": lst, "n": len(lst), "wc_total": sum(c["wc"] for c in lst)}


# ── LINKS ─────────────────────────────────────────────────────────────
def links(team: str, transfers: list[dict], alumni: list[dict], rumors: list[dict], canon, logo, league_of) -> dict:
    clubs: dict[str, dict] = {}

    def club(name: str) -> dict:
        c = canon(name) or name
        return clubs.setdefault(c, {"club": c, "logo": logo(c), "league": league_of(c), "in": [], "out": [],
                                    "alumni": [], "rumor_in": [], "rumor_out": []})

    for t in transfers:
        if not t.get("club") or norm(t["club"]) in ("without club", "retired", "unknown", "career break"):
            continue
        c = club(str(t["club"]))
        if canon(str(t["club"])) == team:
            continue
        item = {"player": t["player"], "fee_text": t.get("fee_text"), "photo": t.get("photo"), "window": t.get("window")}
        (c["in"] if t.get("direction") == "in" else c["out"]).append(item)
    for a in alumni:
        club(a["club"])["alumni"].append({"player": a["player"], "photo": a.get("photo"), "ovr": a.get("ovr")})
    for r in rumors:
        c = club(r["club"])
        (c["rumor_in"] if r["direction"] == "in" else c["rumor_out"]).append(
            {"player": r["player"], "prob": r.get("prob"), "photo": r.get("photo")})
    out = []
    for c in clubs.values():
        if c["club"] == team:
            continue
        w = 2.0 * (len(c["in"]) + len(c["out"])) + 1.5 * len(c["alumni"]) + 0.8 * (len(c["rumor_in"]) + len(c["rumor_out"]))
        if w <= 0:
            continue
        # 같은 선수가 이적·출신 둘 다에 잡히면(여름에 판 선수) 출신 쪽에서 뺀다
        sold = {norm(x["player"]) for x in c["out"]}
        c["alumni"] = [x for x in c["alumni"] if norm(x["player"]) not in sold]
        out.append({**c, "weight": round(w, 1)})
    out.sort(key=lambda c: -c["weight"])
    return {"clubs": out[:14], "n_clubs": len(out)}


# ── INSIGHTS ──────────────────────────────────────────────────────────
def _fee(v) -> str:
    if not v:
        return ""
    return f"€{v / 1e6:.0f}M" if v >= 1e6 else f"€{v / 1e3:.0f}K"


def _last(n) -> str:
    t = str(n or "").split()
    return t[-1] if t else str(n or "")


def insights(team: str, lead: dict, chem: dict, duos: list, orig: dict, nat: dict, lk: dict,
             players: list[dict]) -> list[dict]:
    out = []
    caps = lead.get("captains", [])
    if caps:
        c = caps[0]
        ev = [f"{x['label']} {x['name']}" for x in caps]
        if c.get("injured") and lead.get("armband") and lead["armband"] != c["name"]:
            out.append({"lens": "leadership", "icon": "©", "tone": "warn", "title": "완장 이동",
                        "text": f"주장 {c['name']} 결장({c.get('injury') or '부상'}) — 지금 완장은 {lead['armband']}",
                        "evidence": ev, "big": "C", "unit": "완장 이동", "who": [lead["armband"], c["name"]],
                        "line": f"{_last(c['name'])} 결장 → {_last(lead['armband'])}"})
        else:
            extra = []
            if c.get("tenure") is not None:
                extra.append(f"입단 {int(c['tenure'])}년차")
            rank = chem.get("hub_rank", {}).get(c["name"])
            if rank:
                extra.append(f"연결 중심성 팀 {rank}위")
            out.append({"lens": "leadership", "icon": "©", "tone": "info", "title": "주장단",
                        "text": f"주장 {c['name']}" + (f" · {', '.join(extra)}" if extra else "")
                                + (f" — 부주장 {caps[1]['name']}" if len(caps) > 1 else ""),
                        "evidence": ev, "who": [x["name"] for x in caps[:3]],
                        "big": str(int(c["tenure"])) if c.get("tenure") is not None else "C",
                        "unit": "년차 주장" if c.get("tenure") is not None else "주장",
                        "line": _last(c["name"]) + (f" · 부주장 {_last(caps[1]['name'])}" if len(caps) > 1 else "")})
    nodes = chem.get("nodes", [])
    if nodes:
        hub = max(nodes, key=lambda n: n["degree"])
        partners = sorted([e for e in chem["edges"] if hub["name"] in (e["a"], e["b"])], key=lambda e: -e["minutes"])
        strong = [e for e in partners if e["minutes"] >= 300]
        out.append({"lens": "chemistry", "icon": "◎", "tone": "good", "title": "연결 허브",
                    "text": f"{hub['name']} — {len(strong)}명과 300분 넘게 함께 뛰었다(팀에서 가장 많이 연결된 선수)",
                    "evidence": [f"{hub['name']} ─ {e['minutes']}분 ─ {e['b'] if e['a'] == hub['name'] else e['a']}"
                                 for e in partners[:3]],
                    "big": str(len(strong)), "unit": "명과 300분+", "who": [hub["name"]], "line": hub["name"]})
    if duos:
        d = duos[0]
        out.append({"lens": "chemistry", "icon": "⇄", "tone": "good", "title": "최고의 듀오",
                    "text": f"{d['a']['name']} · {d['b']['name']} — {d.get('minutes', 0)}분 함께({d.get('matches', 0)}경기)",
                    "evidence": [f"{d['a']['name']} ─ TEAMMATE ─ {d['b']['name']}"],
                    "big": f"{d.get('minutes', 0):,}", "unit": "분 함께", "who": [d["a"]["name"], d["b"]["name"]],
                    "line": f"{_last(d['a']['name'])} · {_last(d['b']['name'])} · {d.get('matches', 0)}경기"})
    acq = orig.get("acq", {})
    srcs = [s for s in orig.get("sources", []) if s["league"] not in ("ACADEMY", "OTHER")]
    recent = [p for p in players if (p.get("origin") or {}).get("year") and p["origin"]["year"] >= dt.date.today().year - 1
              and (p.get("origin") or {}).get("acq") in ("transfer", "loan", "free")]
    fee = sum((p["origin"].get("fee_eur") or 0) for p in recent)
    txt = f"유스 출신 {acq.get('academy', 0)}명 · 최근 1년 영입 {len(recent)}명" + (f"({_fee(fee)})" if fee else "")
    if srcs:
        txt += f" · 최다 공급 리그 {srcs[0]['league']} {srcs[0]['n']}명"
    line = f"유스 {acq.get('academy', 0)}명" + (f" · {_fee(fee)}" if fee else "") + (f" · 최다 {srcs[0]['league']}" if srcs else "")
    out.append({"lens": "origins", "icon": "⌂", "tone": "info", "title": "스쿼드 구성", "text": txt,
                "evidence": [f"{p['name']} ← {p['origin'].get('from_club') or '?'}" for p in recent[:3]],
                "big": str(len(recent)), "unit": "명 영입(1년)", "who": [p["name"] for p in recent[:4]], "line": line})
    tenured = sorted([p for p in players if p.get("tenure")], key=lambda p: -p["tenure"])
    if tenured:
        t0 = tenured[0]
        out.append({"lens": "origins", "icon": "⏳", "tone": "info", "title": "최장기 근속",
                    "text": f"{t0['name']} — {t0['tenure']:.0f}년째" + (f", {tenured[1]['name']} {tenured[1]['tenure']:.0f}년" if len(tenured) > 1 else ""),
                    "evidence": [f"{t0['name']} ─ JOINED {str(t0.get('joined'))[:4]} ─ {team}"],
                    "big": f"{t0['tenure']:.0f}", "unit": "년째", "who": [t0["name"]],
                    "line": f"{t0['name']} · {str(t0.get('joined'))[:4]} 입단"})
    cs = nat.get("countries", [])
    if cs:
        top = cs[0]
        out.append({"lens": "nations", "icon": "⚑", "tone": "info", "title": "국적 구성",
                    "text": f"{nat['n']}개국 · 최다 {top['name']} {len(top['players'])}명 · 2026 월드컵 명단 {nat['wc_total']}명",
                    "evidence": [f"{p} ─ REPRESENTS ─ {top['name']}" for p in top["players"][:3]],
                    "big": str(nat["n"]), "unit": "개국", "flag": top["name"],
                    "line": f"최다 {top['name']} {len(top['players'])} · 월드컵 {nat['wc_total']}명"})
    cl = lk.get("clubs", [])
    if cl:
        c = cl[0]
        parts = []
        if c["in"]:
            parts.append(f"영입 {len(c['in'])}")
        if c["out"]:
            parts.append(f"방출 {len(c['out'])}")
        if c["alumni"]:
            parts.append(f"출신 선수 {len(c['alumni'])}")
        if c["rumor_in"] or c["rumor_out"]:
            parts.append(f"이적설 {len(c['rumor_in']) + len(c['rumor_out'])}")
        n_link = len(c["in"]) + len(c["out"]) + len(c["alumni"]) + len(c["rumor_in"]) + len(c["rumor_out"])
        out.append({"lens": "links", "icon": "⛓", "tone": "info", "title": "가장 가까운 클럽",
                    "text": f"{c['club']} — {' · '.join(parts)}",
                    "big": str(n_link), "unit": "건 연결", "club": c["club"], "line": f"{c['club']} · {' · '.join(parts)}",
                    "evidence": list(dict.fromkeys(f"{team} ─ {x['player']} ─ {c['club']}"
                                                   for x in (c['in'] + c['out'] + c['alumni'])))[:3]})
    return out


# ── NATIONAL TEAM — 대표팀(2026 월드컵 명단) 동료가 어느 클럽에 흩어져 있나 ──────────────────────
def national_web(team: str, our_nations: dict[str, list[str]], wc_rows: list[dict], locate) -> dict:
    """our_nations: {나라: [우리 선수]}. locate(name) → {club, league, photo, ovr} | None.
    → {나라: {players: [{player, club, league, photo, ovr, ours}], clubs: [{club, n, players}], n_ours}}."""
    out = {}
    by_nat: dict[str, list[dict]] = defaultdict(list)
    for r in wc_rows:
        by_nat[r["nation"]].append(r)
    for nat, ours in our_nations.items():
        rows = by_nat.get(nat, [])
        if not rows:
            continue
        ps, clubs = [], defaultdict(list)
        for r in rows:
            loc = locate(r["player"]) or {}
            club = loc.get("club")
            is_ours = club == team
            ps.append({"player": loc.get("name") or r["player"], "pos": r.get("pos"), "club": club,
                       "league": loc.get("league"), "photo": loc.get("photo", ""), "ovr": loc.get("ovr"), "ours": is_ours})
            clubs[club or "OTHER"].append(loc.get("name") or r["player"])
        cl = sorted(({"club": c, "n": len(v), "players": v} for c, v in clubs.items()), key=lambda c: (c["club"] == "OTHER", -c["n"]))
        out[nat] = {"players": ps, "clubs": cl, "n_ours": sum(p["ours"] for p in ps)}
    return out


# ── TIES — 지난 시즌 라인업으로 본 '전 소속 동료' ──────────────────────────────────────────────
def lineup_pairs(lineups) -> tuple[dict, dict]:
    """ESPN 선발 라인업들 → ({클럽: Counter((a, b) → 함께 선발)}, {클럽: 선수 이름 목록})."""
    from collections import Counter
    pairs: dict[str, Counter] = defaultdict(Counter)
    names: dict[str, set] = defaultdict(set)
    for df in lineups:
        if df is None or df.empty:
            continue
        st = df[df["starter"].astype(str).str.lower().isin(["true", "1", "1.0"])]
        for (club, _eid), g in st.groupby(["squad", "event_id"]):
            ps = sorted(set(g["player"].astype(str)))
            names[club].update(ps)
            for i, a in enumerate(ps):
                for b in ps[i + 1:]:
                    pairs[club][(a, b)] += 1
    return pairs, {k: sorted(v) for k, v in names.items()}


def ties(team: str, players: list[dict], pairs: dict, names: dict, locate, min_starts: int = 5, per_player: int = 4) -> dict:
    """우리 선수의 지난 시즌 동료(함께 선발 min_starts 회+)가 지금 어디 있나.
    kind: former(영입생의 전 소속 동료) · alumni(작년 우리 팀 동료가 떠남) · reunion(다른 팀에서 함께 뛰다 지금 우리 팀에서 재회)."""
    out, reunions = [], []
    for p in players:
        s = p.get("prev_squad")
        if not s or s not in pairs:
            continue
        me = NameIndex(names.get(s, [])).find(p["name"])
        if not me:
            continue
        mates = sorted(((b if a == me else a, n) for (a, b), n in pairs[s].items() if me in (a, b) and n >= min_starts),
                       key=lambda x: -x[1])
        k = 0
        for mate, n in mates:
            loc = locate(mate)
            if not loc or norm(loc.get("name") or mate) == norm(p["name"]):
                continue
            now = loc.get("club")
            if s == team and now == team:
                continue
            kind = "reunion" if now == team else ("alumni" if s == team else "former")
            rec = {"ours": p["name"], "ours_photo": p.get("photo", ""), "mate": loc.get("name") or mate,
                   "mate_photo": loc.get("photo", ""), "mate_ovr": loc.get("ovr"), "from_club": s, "starts": n,
                   "now_club": now, "now_league": loc.get("league"), "kind": kind}
            if kind == "reunion":
                if not any({x["ours"], x["mate"]} == {rec["ours"], rec["mate"]} for x in reunions):
                    reunions.append(rec)
                continue
            out.append(rec)
            k += 1
            if k >= per_player:
                break
    # 같은 동료가 우리 선수 여럿과 묶이면(작년 우리 팀 동료가 떠난 경우) 사람 단위로 하나 — 가장 오래 함께 뛴 우리 선수 + 연결 수
    by_mate: dict[tuple[str, str], dict] = {}
    for t in out:
        k = (norm(t["mate"]), t["now_club"])
        cur = by_mate.get(k)
        if cur is None:
            by_mate[k] = {**t, "links": 1}
        else:
            cur["links"] += 1
            if t["starts"] > cur["starts"]:
                by_mate[k] = {**t, "links": cur["links"]}
    uniq = sorted(by_mate.values(), key=lambda t: -t["starts"])
    clubs: dict[str, dict] = {}
    for t in uniq:
        c = clubs.setdefault(t["now_club"], {"club": t["now_club"], "league": t["now_league"], "ties": [], "weight": 0})
        c["ties"].append(t)
        c["weight"] += t["starts"]
    cl = sorted(clubs.values(), key=lambda c: -c["weight"])
    return {"clubs": cl[:14], "n_ties": len(uniq), "n_clubs": len(cl), "reunions": reunions,
            "players": sorted({t["ours"] for t in uniq})}


# ── MANAGER — 커리어 · 같은 클럽을 거친 현직 감독 · 감독과 함께 온 선수 ─────────────────────────
def manager_graph(team: str, mgr: dict, careers: dict, current: dict, canon, logo, players: list[dict], season_start: int) -> dict:
    """mgr: {name, photo, nationality, appointed}. current: {감독: {team, league, photo}} (8개 리그 현직)."""
    name = mgr.get("name")
    car = careers.get(name or "", {})
    if not car:
        return {"available": False, "name": name}

    def key(c):
        return norm(canon(c) or c)

    def deco(spells):
        return [{**s, "canon": canon(s["club"]), "logo": logo(canon(s["club"]) or "")} for s in spells]
    managed, played = deco(car.get("managed", [])), deco(car.get("played", []))
    mine = {}
    for s in managed:
        mine.setdefault(key(s["club"]), ("managed", s["club"]))
    for s in played:
        mine.setdefault(key(s["club"]), ("played", s["club"]))
    net = []
    for other, info in current.items():
        if other == name:
            continue
        oc = careers.get(other, {})
        shared = []
        for kind, spells in (("managed", oc.get("managed", [])), ("played", oc.get("played", []))):
            for s in spells:
                k = key(s["club"])
                if k in mine and not any(x["club"] == mine[k][1] for x in shared):
                    shared.append({"club": mine[k][1], "mine": mine[k][0], "theirs": kind})
        if shared:
            net.append({"manager": other, **info, "shared": shared})
    net.sort(key=lambda x: (-len(x["shared"]), x["manager"]))
    # 직전 감독 클럽(지난 시즌에 맡던 곳)에서 지금 우리 팀으로 온 선수
    prev_clubs = {key(s["club"]) for s in managed
                  if (s.get("end") or season_start + 1) >= season_start and norm(canon(s["club"]) or s["club"]) != norm(team)}
    brought = [p["name"] for p in players if p.get("prev_squad") and key(p["prev_squad"]) in prev_clubs]
    return {"available": True, **mgr, "managed": managed, "played": played, "network": net[:16],
            "n_network": len(net), "brought": brought}


def insights_extra(team: str, nat_web: dict, ti: dict, mg: dict) -> list[dict]:
    out = []
    if nat_web:
        nat, w = max(nat_web.items(), key=lambda kv: (kv[1]["n_ours"], len(kv[1]["players"])))
        others = [c for c in w["clubs"] if c["club"] not in (team, "OTHER")]
        if others:
            top = others[0]
            out.append({"lens": "nations", "icon": "⚑", "tone": "info", "title": "대표팀 동료",
                        "text": f"{nat} 대표팀(월드컵 명단 {len(w['players'])}명) 중 우리 {w['n_ours']}명 — "
                                f"나머지는 {len(others)}개 클럽, 최다 {top['club']} {top['n']}명",
                        "evidence": [f"{p} ─ {nat} ─ {top['club']}" for p in top["players"][:3]],
                        "big": str(w["n_ours"]), "unit": f"명 {nat} 대표", "flag": nat, "club": top["club"],
                        "line": f"대표팀 동료 최다 {top['club']} {top['n']}명"})
    if ti and ti.get("clubs"):
        c = ti["clubs"][0]
        txt = f"지난 시즌 동료 {ti['n_ties']}명이 {ti['n_clubs']}개 클럽에 — 가장 많은 곳 {c['club']} {len(c['ties'])}명"
        if ti.get("reunions"):
            r = ti["reunions"][0]
            txt += f" · 재회: {r['ours']}·{r['mate']}({r['from_club']})"
        out.append({"lens": "ties", "icon": "↺", "tone": "info", "title": "전 소속 동료", "text": txt,
                    "big": str(ti["n_ties"]), "unit": "명 옛 동료", "club": c["club"],
                    "line": f"{ti['n_clubs']}개 클럽 · 최다 {c['club']} {len(c['ties'])}명",
                    "evidence": [f"{t['ours']} ─ {t['starts']}경기 함께({t['from_club']}) ─ {t['mate']} @ {t['now_club']}"
                                 for t in c["ties"][:3]]})
    if mg and mg.get("available"):
        clubs = list(dict.fromkeys(s["club"] for s in mg["managed"]))
        txt = f"{mg['name']} — 감독 {len(clubs)}개 클럽"
        if mg.get("n_network"):
            txt += f" · 같은 클럽을 거친 현직 감독 {mg['n_network']}명"
        if mg.get("brought"):
            txt += f" · 전 팀에서 함께 온 선수 {len(mg['brought'])}명"
        ev = [f"{mg['name']} ─ MANAGED ─ {c}" for c in clubs[-3:]]
        out.append({"lens": "manager", "icon": "♟", "tone": "info", "title": "감독 커리어", "text": txt, "evidence": ev,
                    "big": str(len(clubs)), "unit": "개 클럽 지휘",
                    "line": mg["name"] + (f" · 연결 감독 {mg['n_network']}명" if mg.get("n_network") else "")})
    return out
