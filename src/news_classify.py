"""
뉴스 기사 분류 — 종류 · 이적 단계 · 인용된 기자(news.db article_meta).

  kind     transfer(이적·계약) · injury(부상·결장) · match(프리뷰·결과·중계) · interview(발언) · official(구단 공식 매체) · other
  stage    이적 기사만 — interest(관심) < talks(협상·제안) < agreed(합의·메디컬) < done(확정·'here we go') · denied(부인)
  journalists  제목·요약에 이름이 나온 기자·인사이더(예: 'Fabrizio Romano')

1) 규칙(전부, 무료·결정적) — 8개 언어 낱말. 기자는 '학습한 기자 목록'(data/news_journalists.csv)과 이름 전체 일치.
2) AI(최근 2일 이적·인터뷰·기타 기사 일부, Gemini 무료 등급 하루 상한) — 종류·단계를 고치고 기자 이름을 찾는다.
   AI 가 낸 기자 이름은 기사 글에 실제로 있는 것만 받고, 받은 이름은 기자 목록에 쌓여 다음부터 규칙이 찾는다
   (손으로 쓴 기자 표 없음 — 언급이 쌓일수록 넓어진다).

    python src/news_classify.py            # 분류 안 된 기사 규칙 분류 + AI 보정
    python src/news_classify.py --no-ai
    python src/news_classify.py --all      # 규칙 분류 전부 다시(AI 결과는 유지)
"""
from __future__ import annotations

import csv
import datetime as dt
import re
import sys
from pathlib import Path

from unidecode import unidecode

sys.path.insert(0, str(Path(__file__).resolve().parent))
import news_db  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
JOURNALISTS = ROOT / "data" / "news_journalists.csv"
KINDS = ("transfer", "injury", "match", "interview", "official", "other")
STAGES = ("interest", "talks", "agreed", "done", "denied")
AI_DAILY = 36            # Gemini 호출/일(40건씩 묶음) — 번역·AI 요약과 무료 한도를 나눈다
AI_BATCH = 40
AI_PER_RUN = 3


def _fold(s) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", unidecode(str(s or "")).lower()).split())


def _rx(*words: str) -> re.Pattern:
    """접은 글(소문자·악센트 제거)에 맞추는 낱말 묶음 — 낱말 앞은 경계, 뒤는 열어 둔다(sign → signs·signing)."""
    return re.compile(r"\b(" + "|".join(words) + r")")


# 종류 — 위에서부터 먼저 맞는 것(부상 > 이적 > 경기 > 인터뷰)
INJURY = _rx("injur", "ruled out", "sidelined", "hamstring", "knee", "ankle", "muscle", "fitness", "out for", "return date",
             "knock", "surgery", "lesion", "lesio", "baja", "infortun", "stop per", "verletz", "ausfall", "faellt aus", "fallt aus",
             "blessure", "blesse", "forfait", "lesao", "lesionad", "geblesseerd", "breuk", "neusbreuk", "uitgevallen", "kruisband",
             "sakatl", "yaralan", "ameliyat", "skade", "skadet", "korsband", "wieder fit", "fit again", "back in training",
             "returns from", "de retour", "absent", "verzicht", "lange aus", "ligament", "dechir", "fare a meno", "selection boost",
             "terug voor", "ritrova")
# 이적 — 확실한 낱말(제목·요약 어디서든) / 애매한 낱말(제목에서만, 다른 뜻 표현을 지운 뒤).
# 예전엔 낱말 하나라도 있으면 이적이라 요약문의 'llegada'·'contrato'·'pursuit'·'departure' 로 경기·인터뷰 기사가 이적이 됐고
# (정밀도 0.78), 튀르키예어·덴마크어 낱말이 없어 쉬페르리그 기사 대부분이 '기타'였다(2026-10-23 평가 표본).
TRANSFER_STRONG = _rx("transfer", "signing", "signs for", "signed for", "swoop", "release clause", "here we go", "loan move", "loan deal",
                      "on loan", "permanent deal", "permanent move", r"fee (for|of|agreed)\b",
                      r"(agree|agreed|record|undisclosed|transfer|club-record|initial) fee\b", "fichaj", "fichar", "traspaso", "calciomercato", "mercato",
                      "trasferiment", "acquist", "cession", "prestito", "wechsel", "ablose", "leihe", "verleih", "neuzugang", "verpflicht",
                      "transfert", "recrue", "overgang", "transferencia", "emprestimo", "reforco", "contratac", "kiralik", "bonservis",
                      "imzala", "imza att", "takas", "lejeaftale", "udlej", "klubskifte", "skifter til", "contract extension", "new contract",
                      "new deal", "verlenging", "contractverlenging", "renova", "renueva", "renovac", "renovo", "rinnovo", "rinnova il",
                      "prolonge", "verlangert", "verlaengert", "forlaenger", "transfervrij", "free agent", "vrije transfer",
                      "kaufentscheidung", "kaufoption", "kaufpflicht", "assina pelo", "assina por", "assinou")
TRANSFER_WEAK = _rx("target", r"deal\b", "contract", r"exit\b", "departure", "salida", "llegada", "chegada", "saida", "joins",
                    "join ", "joining", "move to", "move for", "chase", "pursuit", "race for", "race to", "scout", "acuerdo", "accordo",
                    "akkoord", "acordo", "komst", "vertrek", "vertrag", "contrato", "kontrakt", "sozlesme", "bid", "loan", "sign ",
                    "signs", "signed", "linked", r"link\b", "na mira", "nel mirino", "im visier", "radarina", "gundeminde", "arrivee",
                    r"depart\b", "vise ", "teklif", "anlasma", "yollar ayrild", "ayrilik", "henter", "kober", "saelger",
                    "skifte", "abschied", "verbleib", "klopft", "an der angel", "interesse an", "blinda", "novo treinador",
                    "new manager", "new head coach", "yeni teknik direktor", "ny cheftraener", "huur", "pret ", "cedid", "cedut",
                    "departs", "release")
# 이적 낱말의 다른 뜻 — 지우고 본다: 'bid to follow up'(시도) · 'deal with'(대처) · 연장전(prolongamento·prolongation) ·
# 'fiducia rinnovata'(신뢰) · 'joins the cast·stars'(출연) · 대출·주식 · 'loan star'(임대 가서 활약하는 선수 기사)
NOT_TRANSFER = re.compile(r"\b(bid to (?!sign|land|bring|buy|secure|lure|keep|tie|re-sign)[a-z]+|deals? with|dealt with|loanee|"
                          r"prolongament\w*|prolongacion\w*|prolongation\w*|fiducia \w+|joins? (the )?(stars|cast|crew|board|"
                          r"band|show|line up of|celebrations)|housing loan|loan from|stock|shares|investing|loan star|"
                          r"city of culture)\b")
# 구단 사업 계약(용품·후원·중계·명명권) — 'verlängert'·'deal' 이 있어도 선수 이적이 아니다
# ('SV Ried verlängert mit hummel bis 2032 – Ausrüstervertrag', 2026-10-23)
BUSINESS_DEAL = re.compile(r"\b(ausruster\w*|sponsor\w*|kit (deal|supplier|partner)\w*|partnership|naming rights|"
                           r"broadcast\w* (deal|rights)|tv (deal|rights)|equipementier|patrocin\w*)\b")
MATCH = _rx("preview", "prediction", "team news", "lineup", "line up", "line-up", "player ratings", "ratings", "highlights",
            "where to watch", "how to watch", "live updates", "match report", "kick off", "kick-off", "result",
            "probabili formazioni", "pagelle", "dove vedere", "pronostic", "compos", "ou regarder", "horario", "donde ver",
            "alineacion", "cronica", "aufstellung", "vorbericht", "noten", "spielbericht", "samenvatting", "opstelling",
            "onde ver", "escalac", "antevisao", "uitslag", "voorbeschouwing", "win against", "win over", r"beats?\b",
            "beaten", "draw with", "draw against", "held to", "defeat", "victory", "victoria", "derrota", "empate", "vittoria", "sconfitta",
            "pareggio", "sieg", "niederlage", "remis", "victoire", "defaite", "vitoria", "zege", "nederlaag", "gelijkspel",
            "mac ", "maci", "macin", "galibiyet", "maglubiyet", "berabere", "karsilasma", "canli", "ilk 11", "skor",
            "kamp", "sejr", "nederlag", "uafgjort", "startopstilling", "holdopstilling", "liveticker", "live ticker", "live-ticker",
            "spieltag", "unentschieden", r"wins?\b", "thrilling", "comeback", "hat-trick", "hat trick", "brace", "rout", "thrash",
            "edge past", "cruise", "stun", "goleada", "golazo", "elimina", "eliminat", "knock out", "knocked out", "into the last",
            "clash", "scores", r"goal\b", "goals", "team selection", "vorm spiel", "spiel in", "live score", "match summary",
            "formazione", "giornata", "classifica", "biglietti", "torneo", "trionfo", "disfatta", "vittorios", "empata", "golo",
            "em direto", "ao vivo", "diffuse", "s incline", r"loss\b", "loses", "lost to", "onze", "op rapport")
VS = re.compile(r"\b(vs?|v|contre|contra|gegen|tegen)\b|\d+\s*[-–:]\s*\d+|(?<=[a-z]) x (?=[a-z])")
INTERVIEW = _rx("says", "said", "insists", "admits", "reveals", "explains", "claims", "warns", "responds", "praises",
                "slams", "hails", "press conference", "interview", "declar", "dice ", "afferma", "ammette", "sagt", "erklart",
                "declare", "affirme", "explique", "diz ", "afirma", "admite", "zegt", "vertelt", "persconferentie",
                "acikladi", "konustu", "dedi", "sozleri", "roportaj", "siger", "fortaeller", "meint", "betont")
QUOTE = re.compile(r"^[\"'“‘«„]|:\s*[\"'“‘«„]")

# 이적 단계 — 부인 > 확정(강) > 합의 > 확정(약) > 협상 > 관심
DENIED = _rx("deny", "denies", "denied", "rules out", "ruled out a move", "no interest", "not for sale", "rejects", "rejected",
             "turns down", "smentit", "desmient", "descart", "dementi", "dément", "dement", "afgewezen", "ontkent", "nega ",
             "uitgesloten", "ausgeschlossen", "escluso", "exclu")
DONE_STRONG = _rx("here we go", "official", "confirmed", "confirms", "completed", "completes", "unveil", "oficial",
                  "ufficiale", "offiziell", "officiel", "officieel", "e un nuovo giocatore", "nouveau joueur", r"rond\b")
AGREED = _rx("agree", "agreement", "personal terms", "medical", "verbal", "close to", "closing in", "set to", "on the verge",
             "imminent", "nears", "edge closer", "accordo", "acuerdo", "akkoord", "acordo", "einig", "visite mediche",
             "reconocimiento", "medizincheck", "visite medicale", "keuring", "ya tiene", "cerca de", "vicino", "proche")
DONE_WEAK = _rx("signs", "signed", "joins", "joined", "seals", "sealed", "firma con", "ficha por", "tekent", "getekend",
                "assina", "assinou", "rejoint", "unterschreibt", "wechselt zu")
TALKS = _rx("talks", "negotiat", "bid", "offer", "approach", "opening", "proposal", "trattativ", "negociac", "oferta",
            "offerta", "angebot", "verhandl", "offre", "proposta", "bod ", "onderhandel", "gesprek", "contatti", "contact",
            "gorusme", "teklif", "forhandl", "tilbud")
INTEREST = _rx("interest", "target", r"eyes?\b", r"eyeing", "monitor", "track", "chase", r"race\b", "keen", "consider", "scout", "linked",
               "want", r"plans?\b", "shortlist", "pursuit", "admire", "interes", "seguito", "obiettivo", "osserv", "beobacht",
               "piste", "cible", "alvo", "volgt", "op het oog", "in beeld", "sondeo", "sondaggio", "radar")


def _is_official(source: str, teams: str) -> bool:
    """구단 자체 매체 — 매체 이름(접은 글, 도메인 꼬리 제거)이 기사 팀 이름 그 자체."""
    import news_relevance as nr  # noqa: PLC0415
    import teammeta as tm  # noqa: PLC0415
    src = _fold(re.sub(r"\.(com|es|it|de|fr|pt|nl|be|co\.uk|net|org)$", "", str(source or "").strip(), flags=re.I))
    if not src:
        return False
    import news_sources  # noqa: PLC0415
    for t in str(teams or "").split(","):
        t = t.strip()
        if not t:
            continue
        names = (tm.team_fullname(t), *news_sources.cached_local_names(t))   # 'Standard de Liège' 매체 = 그 구단
        if src in {_fold(t), *map(_fold, names)}:
            return True
        if src in set(nr.team_terms(t, names)) and len(src.split()) >= 2:
            return True
    return False


# 'joins the drama·party·list …' 는 이적이 아니다 — 'Mateo Chávez Joins the Drama: AZ Snatches Last-Minute Draw Against
# SC Cambuur' 가 이적 '확정'으로 루머 판정·KG 주장에 들어갔다(2026-10-22 검수)
JOIN_IDIOM = re.compile(r"\bjoin(s|ed|ing)? (in )?(the )?(drama|party|list|club of|race to|fun|chorus|conversation|fight|"
                        r"celebrations?|exodus|ranks of|elite|history books)\b")


def _transfer_hit(f: str, strong_only: bool = False) -> bool:
    g = NOT_TRANSFER.sub(" ", JOIN_IDIOM.sub(" ", f))
    if BUSINESS_DEAL.search(g):
        return False
    if TRANSFER_STRONG.search(g):
        return True
    return not strong_only and bool(TRANSFER_WEAK.search(g))


def _kind_of(text: str, strong_only: bool = False) -> str:
    f = _fold(text)
    if INJURY.search(f):
        return "injury"
    if _transfer_hit(f, strong_only):
        return "transfer"
    if MATCH.search(f) or VS.search(str(text or "").lower()):
        return "match"
    if INTERVIEW.search(f) or QUOTE.search(str(text or "")):
        return "interview"
    return "other"


def rule_kind(headline: str, descr: str = "", source: str = "", teams: str = "") -> str:
    """제목으로 정하고, 제목만으론 '기타'일 때 요약까지 본다. 구단 자체 매체는 official."""
    if _is_official(source, teams):
        return "official"
    k = _kind_of(headline)
    # 요약까지 볼 땐 이적은 확실한 낱말만 — 요약의 'llegada'·'contrato'·'pursuit' 로 경기 기사가 이적이 됐다
    return k if k != "other" or not descr else _kind_of(f"{headline} {descr}", strong_only=True)


def rule_stage(text: str) -> str:
    f = _fold(text)
    for st, rx in (("denied", DENIED), ("done", DONE_STRONG), ("agreed", AGREED), ("done", DONE_WEAK),
                   ("talks", TALKS), ("interest", INTEREST)):
        if rx.search(f):
            return st
    return ""


# ── 학습한 기자 목록 ─────────────────────────────────────────────────────────────
def load_journalists() -> dict[str, dict]:
    if not JOURNALISTS.exists():
        return {}
    with JOURNALISTS.open(encoding="utf-8") as fh:
        return {r["name"]: r for r in csv.DictReader(fh) if r.get("name")}


def save_journalists(j: dict[str, dict]) -> None:
    JOURNALISTS.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(j.values(), key=lambda r: (-int(r.get("mentions") or 0), r["name"]))
    with JOURNALISTS.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["name", "mentions", "first_seen", "last_seen", "outlets"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})


def find_journalists(text: str, known: dict[str, dict]) -> list[str]:
    """학습한 기자 이름 전체가 글에 나오면(접은 글, 낱말 경계)."""
    f = f" {_fold(text)} "
    return [n for n in known if f" {_fold(n)} " in f]


def rule_meta(row: dict, known: dict[str, dict]) -> dict:
    head, descr = str(row.get("headline") or ""), str(row.get("descr") or "")
    text = f"{head} {descr}"
    kind = rule_kind(head, descr, row.get("source") or "", row.get("teams") or "")
    stage = (rule_stage(head) or rule_stage(text)) if kind == "transfer" else ""
    js = find_journalists(text, known)
    # 블루스카이 게시물은 글쓴이가 곧 그 정보의 기자(src/news_wires.py — 기자 계정만 받는다)
    if str(row.get("via") or "") == "bsky" and row.get("author") and row["author"] not in js:
        js = [row["author"], *js]
    return {"link": row["link"], "kind": kind, "stage": stage, "journalists": "|".join(js), "by": "rule"}


# ── AI 보정 ─────────────────────────────────────────────────────────────────────
SYSTEM = ("You label football news headlines. Use only the given text. "
          "journalists = names of reporters/insiders explicitly cited in the text as the source of the information "
          "(e.g. 'per Fabrizio Romano', 'David Ornstein reports'); never players, coaches, club officials or agents. "
          "Return JSON only.")
PROMPT = """Label each item.
kind: transfer (transfer, loan, contract, rumour), injury (injury, fitness, absence), match (preview, report, lineup, ratings, where to watch),
interview (mainly quotes from a player/coach), other.
stage (only when kind=transfer): interest, talks, agreed, done, denied, or "" if unclear.
Return a JSON array: [{{"i": <index>, "kind": "...", "stage": "...", "journalists": ["..."]}}]

{items}"""


_NOT_PERSON = re.compile(r"\b(football|futbol|calcio|news|sport|sports|club|united|city|times|daily|mail|press|media|"
                         r"radio|tv|fc|cf|ac|official|transfer|mercato|gazzetta|marca)\b")


def _person_like(name: str) -> bool:
    """2~4 낱말, 각 낱말 대문자로 시작, 매체·클럽 낱말 없음('Get French Football News' 같은 매체명을 거른다)."""
    ws = str(name or "").split()
    return 2 <= len(ws) <= 4 and all(w[:1].isupper() for w in ws if len(w) > 3) and not _NOT_PERSON.search(_fold(name))


def ai_labels(rows: list[dict]) -> list[dict]:
    """Gemini 한 번 — 고친 분류(검증 통과분만). 키 없음·한도 소진이면 []."""
    import llm  # noqa: PLC0415
    items = "\n".join(f"{i}. [{r.get('source') or ''}] {r.get('headline') or ''}"
                      + (f" — {str(r.get('descr'))[:200]}" if r.get("descr") else "") for i, r in enumerate(rows))
    out = llm.generate_json(PROMPT.format(items=items), SYSTEM)
    if not isinstance(out, list):
        return []
    res = []
    for o in out:
        try:
            r = rows[int(o.get("i"))]
        except (TypeError, ValueError, IndexError, AttributeError):
            continue
        kind = str(o.get("kind") or "").lower()
        if kind not in KINDS or kind == "official":
            continue
        stage = str(o.get("stage") or "").lower() if kind == "transfer" else ""
        stage = stage if stage in STAGES else ""
        text = f" {_fold(str(r.get('headline') or '') + ' ' + str(r.get('descr') or ''))} "
        js = [str(n).strip() for n in (o.get("journalists") or []) if isinstance(n, str)]
        # 기자 = 이적 기사에서 인용된 사람 이름만(경기 기사 필자·해설자 발언은 빼고), 글에 이름 전체가 있고 사람 이름 꼴
        js = [n for n in js if kind == "transfer" and _person_like(n) and f" {_fold(n)} " in text]
        keep_kind = r.get("kind") if r.get("kind") == "official" else kind
        res.append({"link": r["link"], "kind": keep_kind, "stage": stage, "journalists": "|".join(dict.fromkeys(js)),
                    "by": "ai", "_source": r.get("source") or ""})
    return res


RULE_VER = "2026-10-23"   # 분류 규칙을 바꾸면 날짜를 올린다 — 다음 실행이 규칙 분류(by=rule)를 한 번 다시(AI 결과는 그대로)


def _rule_ver_changed() -> bool:
    with news_db._conn() as c:   # noqa: SLF001
        c.execute("CREATE TABLE IF NOT EXISTS meta_kv (k TEXT PRIMARY KEY, v TEXT)")
        row = c.execute("SELECT v FROM meta_kv WHERE k='rule_ver'").fetchone()
        if row and row[0] == RULE_VER:
            return False
        c.execute("INSERT OR REPLACE INTO meta_kv VALUES ('rule_ver', ?)", (RULE_VER,))
        return True


def run(ai: bool = True, redo: bool = False) -> dict:
    news_db.init_db()
    known = load_journalists()
    if redo or _rule_ver_changed():
        with news_db._conn() as c:   # noqa: SLF001 — AI 결과는 남기고 규칙 분류만 다시
            c.execute("DELETE FROM article_meta WHERE by='rule'")
    todo = news_db.unclassified(limit=200000)
    news_db.set_meta([rule_meta(r, known) for r in todo])
    out = {"rule": len(todo), "ai": 0, "journalists_new": 0}
    if not ai:
        return out
    import llm  # noqa: PLC0415
    if not llm.available():
        return out
    llm.start("news_cls", AI_DAILY)
    since = (dt.date.today() - dt.timedelta(days=2)).isoformat()
    today = dt.date.today().isoformat()
    for _ in range(AI_PER_RUN):
        if llm.remaining() <= 0:
            break
        rows = news_db.for_ai(since, ("transfer", "interview", "other", "official"), AI_BATCH)
        if not rows:
            break
        labels = ai_labels(rows)
        if not labels:        # 실패한 묶음은 다음 실행이 다시(같은 기사로 무한 반복하지 않게 by=rule 유지, 이번 실행은 멈춤)
            break
        done = {x["link"] for x in labels}
        # 답이 빠진 기사는 규칙 분류를 확정(by=ai_skip)해 다음 묶음에 다시 오지 않게
        skipped = [{**r, "by": "ai_skip"} for r in rows if r["link"] not in done]
        for x in labels:
            for n in filter(None, x["journalists"].split("|")):
                j = known.setdefault(n, {"name": n, "mentions": 0, "first_seen": today, "outlets": ""})
                if not int(j.get("mentions") or 0):
                    out["journalists_new"] += 1
                j["mentions"] = int(j.get("mentions") or 0) + 1
                j["last_seen"] = today
                outs = [o for o in str(j.get("outlets") or "").split("|") if o]
                if x["_source"] and x["_source"] not in outs:
                    j["outlets"] = "|".join((outs + [x["_source"]])[-6:])
        news_db.set_meta(labels + skipped)
        out["ai"] += len(labels)
    out["llm"] = llm.finish()
    if out["journalists_new"] or out["ai"]:
        save_journalists(known)
    return out


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(ai="--no-ai" not in sys.argv, redo="--all" in sys.argv))
