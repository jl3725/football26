"""
일일 뉴스 수집 배치 — ESPN + Guardian/BBC RSS + Google News(팀별 현지어·영어 이적) → sqlite 누적 → 분류 → 번역 백필.

GitHub Actions cron이 2시간마다 실행하고 data/news.db를 repo에 커밋한다.
(link, team) 복합키로 중복 없이 누적되며, 새 기사만 first_seen=오늘으로 들어간다.
번역은 수집 중에 하지 않고, 끝난 뒤 번역 안 된 기사를 최신순으로 묶어 한 번에 보낸다
(공급자·무료 한도는 src/translate.py). 실패한 건 비워 두고 다음 실행이 다시 채운다.

수동 실행:
    python scripts/fetch_news_daily.py                 # EPL (기본)
    python scripts/fetch_news_daily.py --league LaLiga # ESPN esp.1 (Guardian/BBC 없이)
    python scripts/fetch_news_daily.py --all           # 전 리그
    python scripts/fetch_news_daily.py --backfill 2000 # 수집 없이 밀린 번역만
    python scripts/fetch_news_daily.py --check         # 최근 2일 번역률 50% 미만이면 종료코드 1
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ui.news import (  # noqa: E402
    fetch_espn_news, fetch_rss_news, team_articles, merge_news, newstags,
    fetch_es_wire, es_wire_for_team,
)
from news_db import (  # noqa: E402
    init_db, upsert_articles, stats, untranslated, set_translation, translation_stats, recent_heads, via_count, prune, head_key,
)
import news_sources as gn  # noqa: E402
from translate import translate_many, STATS  # noqa: E402

LEAGUES = ["EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1", "LigaPortugal", "Eredivisie", "BelgianProLeague"]


GN_PER_RUN = 6        # Google News — 팀당 한 번에 새 기사 이만큼(하루 상한 gn.DAILY_CAP)


def google_new(team: str, arts: list[dict], taken: set[str]) -> list[dict]:
    """Google 기사 중 이번 실행에 넣을 것 — 최근 7일 안에 다른 경로로 받은 제목·이번에 받은 제목 제외, 회당·하루 상한."""
    today = _days_ago(0)
    room = min(GN_PER_RUN, gn.DAILY_CAP - via_count(team, gn.VIA, today))
    if room <= 0:
        return []
    known = recent_heads(team, _days_ago(7)) | taken
    out = [a for a in arts if head_key(a["headline"]) not in known]
    return out[:room]


def run_league(league: str, br: gn.Breaker | None = None) -> tuple[int, int]:
    tags = newstags(league)
    espn = fetch_espn_news(league)
    wire = fetch_es_wire() if league == "LaLiga" else []   # AS·MD·Sport 리그 와이어 1회
    google = gn.fetch_league(league, tags, br) if br is not None and not br.open else {}
    print(f"[{league}] ESPN {len(espn)}건 · ES와이어 {len(wire)}건 · Google {sum(map(len, google.values()))}건 · {len(tags)}팀 처리…")
    new = tot = 0
    for i, team in enumerate(tags, 1):
        e = team_articles(espn, team, 12)
        r = fetch_rss_news(team)                    # EPL: Guardian/BBC · LaLiga: Marca 팀별
        w = es_wire_for_team(wire, team)            # LaLiga: AS/MD/Sport 팀명 매칭
        merged = merge_news(e, r + w, 20)
        g = google_new(team, google.get(team, []), {head_key(a["headline"]) for a in merged})
        n = upsert_articles(merged + g, team)       # 번역은 끝난 뒤 backfill 이 묶어서
        new += n; tot += len(merged) + len(g)
        print(f"  [{i:2}/{len(tags)}] {team:18} {len(merged):2}건 + Google {len(g)} (신규 {n})")
        time.sleep(0.3)
    return new, tot


BACKFILL_PER_RUN = 600   # 실행마다 번역 안 된 기사를 최신순으로 이만큼(Google 제목 포함 — 요약 없이 제목만이라 가볍다)


def _days_ago(n: int) -> str:
    from datetime import date, timedelta
    return (date.today() - timedelta(days=n)).isoformat()


def backfill(limit: int) -> int:
    """번역이 비었거나 원문이 들어간 기사를 최신순으로 번역해 채운다."""
    rows = untranslated(limit)
    if not rows:
        return 0
    texts = []
    for r in rows:
        texts += [r["headline"] or "", r["descr"] or ""]
    kos = translate_many(texts)
    done = sum(1 for i, r in enumerate(rows) if set_translation(r["link"], kos[2 * i], kos[2 * i + 1]))
    print(f"[translate] {done}/{len(rows)}건 번역 · 공급자별 {dict(STATS)}")
    return done


def check() -> int:
    """최근 2일 번역률 감시 — 워크플로가 커밋 뒤 마지막 단계로 돌려 실패를 드러낸다."""
    ts = translation_stats(_days_ago(2))
    print("번역률(2일):", ts)
    if ts["articles"] and ts["translated_pct"] is not None and ts["translated_pct"] < 50:
        print("[FAIL] 최근 2일 번역률 50% 미만 — 번역 공급자 확인 필요(GEMINI_API_KEY·구글 차단 여부)")
        return 1
    return 0


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    init_db()
    if "--check" in args:
        return check()
    if "--backfill" in args:                     # 수집 없이 밀린 번역만: --backfill [건수]
        i = args.index("--backfill")
        n = int(args[i + 1]) if len(args) > i + 1 and args[i + 1].isdigit() else 2000
        backfill(n)
        print("번역률(30일):", translation_stats(_days_ago(30)))
        return 0
    if "--all" in args:
        leagues = LEAGUES
    elif "--league" in args:
        leagues = [args[args.index("--league") + 1]]
    else:
        leagues = ["EPL"]
    tn = tt = 0
    br = None if "--no-google" in args else gn.Breaker()
    for lg in leagues:
        n, t = run_league(lg, br)
        tn += n; tt += t
    if br is not None:
        print(f"[google] 호출 {br.calls}회 · 오류 {br.errors[-5:]}" + (" · 연속 실패로 중단" if br.open else ""))
        print(f"[google] {gn.KEEP_DAYS}일 지난 기사 정리 {prune(gn.VIA, _days_ago(gn.KEEP_DAYS))}건")
    s = stats()
    print(f"\n완료 — 신규 {tn} / 처리 {tt} · DB 누적 {s['articles']}건 ({s['teams']}팀)")
    import news_tags   # 새 기사 선수 태깅(이름 전체 · 성+클럽) — 무료·결정적. 처음 실행 때 지난 기사 전부
    n_art, n_tag = news_tags.run()
    print(f"[news-tags] 기사 {n_art}건 · 선수 태그 {n_tag}개")
    import news_classify   # 종류(이적·부상·경기·인터뷰·구단 발표)·이적 단계·기자 — 규칙(전부) + AI(최근 이적 기사 일부)
    print("[news-classify]", news_classify.run())
    backfill(BACKFILL_PER_RUN)
    print("번역률(2일):", translation_stats(_days_ago(2)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
