"""
뉴스 본문 검색(RAG) — 기사 제목·요약을 무료 임베딩(Gemini gemini-embedding-001, 256차원)으로 Qdrant 'news' 컬렉션에 넣고,
Ask Scout search_news 도구가 질문 뜻으로 찾는다(출처·날짜·링크 그대로).

2026-11-06 사용자 '그래프 RAG 3~4단계' — news.db 는 '미래 RAG 말뭉치'라 적혀만 있었고(news_db.py), 선수 이름 태그로만 기사를
찾았다. '사카 부상 관련 보도 요약'·'아스날 미드필더 영입 관련 기사' 같은 질문은 이름 태그만으론 못 찾는다.

  대상 = 우리 선수가 태그된(how=full) 최근 DAYS 일 기사 중 이적·부상·인터뷰·공식 발표(경기 리포트·기타 제외).
  이미 넣은 기사는 건너뛰고, 한 번에 MAX_NEW 건까지(분당 한도라 BATCH 건씩 PAUSE 초 간격) — 429 면 한 번 기다렸다 다시, 또 걸리면
  거기서 멈추고 다음 실행이 잇는다.
  KEEP_DAYS(이적 기사는 KEEP_TRANSFER_DAYS) 지난 기사는 지운다. Qdrant·Gemini 는 REST(requests)로만 — 운영(Render)에 새 의존성 없이.

    python src/news_vectors.py [--days 30] [--max 400]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

COLLECTION = "news"
DIM = 256
MODEL = "gemini-embedding-001"
# 무료 등급 = 분당 약 100건(2026-11-06: 100건 한 묶음 뒤 바로 429, 1분 뒤 풀림) — 80건씩 62초 간격으로 운영 검색 몫을 남긴다
# 하루 한도도 있다(약 1,000건 — 11/07~08 첫 묶음부터 429) → 회당 400건 × 하루 2번 = 800, 나머지는 운영 Ask Scout 검색 몫
# 이적 기사는 1년 보관(2026-11-09 사용자 '예전 루머 기사가 날아가지 않게' — news.db 원문은 30일 뒤 지워져도 제목·링크로 찾게)
DAYS, KEEP_DAYS, KEEP_TRANSFER_DAYS, MAX_NEW, BATCH, PAUSE = 30, 45, 400, 400, 80, 62.0
KINDS = ("transfer", "injury", "interview", "official")
EX_SOURCE_DOWN = 75
_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{m}:batchEmbedContents"


class QuotaError(RuntimeError):
    pass


def _env() -> None:
    try:
        import scout_agent  # noqa: PLC0415 — .env 읽기(로컬)
        scout_agent._load_dotenv()
    except Exception:  # noqa: BLE001
        pass


def embed(texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Gemini 무료 임베딩 — 429 면 QuotaError."""
    import requests  # noqa: PLC0415
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY 없음")
    body = {"requests": [{"model": f"models/{MODEL}", "content": {"parts": [{"text": t[:2000]}]},
                          "outputDimensionality": DIM, "taskType": task} for t in texts]}
    r = requests.post(_GEMINI.format(m=MODEL), params={"key": key}, json=body, timeout=60)
    if r.status_code == 429:
        raise QuotaError(r.text[:160])
    r.raise_for_status()
    return [e["values"] for e in r.json()["embeddings"]]


def _q(method: str, path: str, body=None, timeout: int = 30):
    """Qdrant REST — QDRANT_URL · QDRANT_API_KEY."""
    import requests  # noqa: PLC0415
    base = os.getenv("QDRANT_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("QDRANT_URL 없음")
    h = {"api-key": os.getenv("QDRANT_API_KEY", "")} if os.getenv("QDRANT_API_KEY") else {}
    r = requests.request(method, f"{base}{path}", json=body, headers=h, timeout=timeout)
    if r.status_code == 404 and method == "GET":
        return None
    r.raise_for_status()
    return r.json().get("result")


def ensure_collection() -> None:
    if _q("GET", f"/collections/{COLLECTION}") is not None:
        return
    _q("PUT", f"/collections/{COLLECTION}", {"vectors": {"size": DIM, "distance": "Cosine"}})
    for field, kind in (("players", "keyword"), ("squads", "keyword"), ("kind", "keyword"), ("day", "integer")):
        _q("PUT", f"/collections/{COLLECTION}/index", {"field_name": field, "field_schema": kind})


def point_id(link: str) -> int:
    return int(hashlib.md5(link.encode("utf-8")).hexdigest()[:15], 16)


def candidates(db: Path, days: int = DAYS) -> list[dict]:
    """넣을 기사 — 선수 태그(full)·최근 days 일·이적·부상·인터뷰·공식. 기사 하나에 선수·팀 여러 명."""
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            f"""SELECT a.link, max(a.headline), max(a.headline_ko), max(a.descr), max(a.source), max(a.published),
                       max(a.first_seen), m.kind, m.stage, group_concat(DISTINCT p.player), group_concat(DISTINCT p.squad)
                FROM articles a JOIN article_players p ON p.link = a.link AND p.how = 'full'
                     JOIN article_meta m ON m.link = a.link
                WHERE a.first_seen >= ? AND m.kind IN ({",".join("?" * len(KINDS))})
                GROUP BY a.link ORDER BY max(a.first_seen) DESC""", (since, *KINDS)).fetchall()
    finally:
        con.close()
    out = []
    for link, head, head_ko, descr, src, pub, first, kind, stage, players, squads in rows:
        day = str(pub or first or "")[:10]
        try:
            d = int(day.replace("-", ""))
        except ValueError:
            continue
        out.append({"id": point_id(link), "link": link, "headline": head or "", "headline_ko": head_ko or "",
                    "descr": (descr or "")[:400], "source": src or "", "published": day, "day": d, "kind": kind or "",
                    "stage": stage or "", "players": [x for x in str(players or "").split(",") if x],
                    "squads": [x for x in str(squads or "").split(",") if x]})
    return out


def _text(a: dict) -> str:
    return "\n".join(x for x in (a["headline"], a["headline_ko"], a["descr"]) if x)


def existing(ids: list[int]) -> set[int]:
    have: set[int] = set()
    for i in range(0, len(ids), 500):
        got = _q("POST", f"/collections/{COLLECTION}/points", {"ids": ids[i:i + 500], "with_payload": False,
                                                               "with_vector": False}) or []
        have |= {int(p["id"]) for p in got}
    return have


def _cut(days: int) -> int:
    return int((dt.date.today() - dt.timedelta(days=days)).strftime("%Y%m%d"))


def prune(keep_days: int = KEEP_DAYS, keep_transfer_days: int = KEEP_TRANSFER_DAYS) -> None:
    """이적 기사가 아닌 것은 keep_days, 이적 기사는 keep_transfer_days 뒤 지운다."""
    _q("POST", f"/collections/{COLLECTION}/points/delete",
       {"filter": {"must": [{"key": "day", "range": {"lt": _cut(keep_days)}}],
                   "must_not": [{"key": "kind", "match": {"value": "transfer"}}]}})
    _q("POST", f"/collections/{COLLECTION}/points/delete",
       {"filter": {"must": [{"key": "day", "range": {"lt": _cut(keep_transfer_days)}}]}})


def index(days: int = DAYS, max_new: int = MAX_NEW, pause: float = PAUSE) -> dict:
    import news_store  # noqa: PLC0415
    db = news_store.ensure()
    if not db:
        return {"error": "news.db 없음"}
    cands = candidates(db, days)
    have = existing([a["id"] for a in cands])
    todo = [a for a in cands if a["id"] not in have][:max_new]
    done, stopped = 0, ""
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        try:
            try:
                vecs = embed([_text(a) for a in chunk])
            except QuotaError:
                time.sleep(pause)                          # 분당 한도 — 한 번 기다렸다 다시
                vecs = embed([_text(a) for a in chunk])
        except QuotaError as e:
            stopped = f"임베딩 한도(429) — 다음 실행이 이어 넣음 {str(e)[:60]}"
            break
        pts = [{"id": a["id"], "vector": v, "payload": {k: a[k] for k in ("link", "headline", "headline_ko", "source", "published",
                                                                          "day", "kind", "stage", "players", "squads")}}
               for a, v in zip(chunk, vecs)]
        _q("PUT", f"/collections/{COLLECTION}/points?wait=true", {"points": pts}, timeout=60)
        done += len(pts)
        if i + BATCH < len(todo):
            time.sleep(pause)
    return {"candidates": len(cands), "already": len(have), "new": done, "left": len(todo) - done, "stopped": stopped}


def search(query: str, players: list[str] | None = None, squad: str | None = None, kind: str | None = None,
           k: int = 8) -> dict:
    """질문 뜻으로 기사 찾기 — 선수·팀·종류 조건(있으면), 비면 조건 없이 다시."""
    _env()
    try:
        vec = embed([query], task="RETRIEVAL_QUERY")[0]
    except Exception as e:  # noqa: BLE001
        return {"error": f"임베딩 실패: {str(e)[:80]}"}
    must = []
    if players:
        must.append({"key": "players", "match": {"any": list(players)}})
    if squad:
        must.append({"key": "squads", "match": {"value": squad}})
    if kind:
        must.append({"key": "kind", "match": {"value": kind}})
    try:
        hits = _q("POST", f"/collections/{COLLECTION}/points/search",
                  {"vector": vec, "limit": k, "with_payload": True, **({"filter": {"must": must}} if must else {})}) or []
        if not hits and must:
            hits = _q("POST", f"/collections/{COLLECTION}/points/search", {"vector": vec, "limit": k, "with_payload": True}) or []
    except Exception as e:  # noqa: BLE001
        return {"error": f"Qdrant 실패: {str(e)[:80]}"}
    arts = [{**{x: (h.get("payload") or {}).get(x) for x in ("headline", "headline_ko", "source", "published", "link", "kind",
                                                             "stage", "players", "squads")}, "score": round(float(h.get("score", 0)), 3)}
            for h in hits]
    return {"query": query, "count": len(arts), "articles": arts}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=DAYS)
    ap.add_argument("--max", type=int, default=MAX_NEW)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _env()
    if not os.getenv("QDRANT_URL") or not os.getenv("GEMINI_API_KEY"):
        print("[news-vec] QDRANT_URL·GEMINI_API_KEY 없음 — 건너뜀")
        return 0
    try:
        ensure_collection()
        prune()
    except Exception as e:  # noqa: BLE001
        print(f"[news-vec] Qdrant 에 닿지 않음 — 원천 중단 {type(e).__name__}: {str(e)[:100]}")
        return EX_SOURCE_DOWN
    r = index(a.days, a.max)
    print(f"[news-vec] 대상 {r.get('candidates')} · 이미 {r.get('already')} · 새로 {r.get('new')} · 남음 {r.get('left')}"
          + (f" · {r['stopped']}" if r.get("stopped") else "") + (f" · {r['error']}" if r.get("error") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
