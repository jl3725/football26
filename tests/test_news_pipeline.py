"""뉴스 1단계 — Google News 검색어·스팸 거르기, 기사 분류(규칙·AI 검증), STORY 묶음."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import news_classify as nc  # noqa: E402
import news_sources as gn  # noqa: E402
import news_stories as ns  # noqa: E402


def test_google_query_and_filters() -> None:
    fr = gn.LOCALE["France"]
    # 한 단어 이름이 있으면 현지어 '축구' 낱말로 좁힌다(Lens → 사진·렌즈 기사)
    assert gn.query(["Lens", "RC Lens"], fr) == '("Lens" OR "RC Lens") football'
    assert gn.query(["Club Brugge"], gn.LOCALE["Belgium"]) == '("Club Brugge")'
    # 약자 표기('Vit. Guimarães')는 검색어에서 뺀다
    assert gn.names_for("Vitória de Guimaraes", "Vit. Guimarães", "Vitória SC") == ["Vitória de Guimaraes", "Vitória SC"]
    assert gn._strip_outlet("Arsenal agree deal - Sky Sports", "Sky Sports") == "Arsenal agree deal"
    # 불법 중계·여자팀·다른 종목은 받지 않는다
    assert not gn.keep("[LIVESTREAM]FREE!!] Troyes vs Lens Live Online Football Coverage", "Universidad")
    assert not gn.keep("Bugeja record: top scorer straniera Inter Women", "MilanoSportiva.com")
    assert not gn.keep("Vitória SC Voleibol", "zerozero.pt")
    assert gn.keep("RC Lens : la défense de Cahuzac se précise avant Bruges", "But! Football Club")


def test_rule_kind_and_stage_multilingual() -> None:
    assert nc.rule_kind("Arsenal injury update: Saliba latest return date") == "injury"
    assert nc.rule_kind("Club Brugge houdt been stijf voor Tresoldi: winters vertrek uitgesloten") == "transfer"
    assert nc.rule_stage("Club Brugge houdt been stijf voor Tresoldi: winters vertrek uitgesloten") == "denied"
    assert nc.rule_kind("Mingueza: acuerdo cerrado tras dejar el Celta") == "transfer"
    assert nc.rule_kind("Napoli Bodø/Glimt, le probabili formazioni della partita") == "match"
    assert nc.rule_kind("Brighton beat Crystal Palace as Gómez scores from range") == "match"
    assert nc.rule_kind('Hancko: "La final queda muy lejos"') == "interview"
    assert nc.rule_stage("Fabrizio Romano: here we go! Tresoldi to Milan") == "done"
    assert nc.rule_stage("Milan close to agreement for Tresoldi") == "agreed"
    assert nc.rule_stage("Milan open talks with Brugge over Tresoldi") == "talks"
    assert nc.rule_stage("Arsenal keen on Club Brugge striker") == "interest"
    assert nc.rule_stage("Brugge rejects Milan bid for Tresoldi") == "denied"
    # 경계: 'Le Fée' 는 이적료(fee)가 아니고 'Racing' 은 영입 경쟁(race)이 아니다
    assert nc.rule_kind("Enzo Le Fée makes amends from the spot") != "transfer"
    assert nc.rule_stage("Racing Club monitor the situation") == "interest"


def test_ai_journalists_must_be_in_text(monkeypatch) -> None:
    import llm
    rows = [{"link": "a", "headline": "Milan agree Tresoldi deal, per Fabrizio Romano", "descr": "", "source": "X", "kind": "transfer"},
            {"link": "b", "headline": "Bayern rout Leipzig | Andy Brassell", "descr": "", "source": "The Guardian", "kind": "other"}]
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: [
        {"i": 0, "kind": "transfer", "stage": "agreed", "journalists": ["Fabrizio Romano", "David Ornstein"]},
        {"i": 1, "kind": "match", "stage": "done", "journalists": ["Andy Brassell"]},
        {"i": 7, "kind": "transfer", "stage": "done", "journalists": []}])
    out = {r["link"]: r for r in nc.ai_labels(rows)}
    assert out["a"]["journalists"] == "Fabrizio Romano"        # 글에 없는 Ornstein 은 버린다
    assert out["a"]["stage"] == "agreed"
    assert out["b"]["kind"] == "match" and out["b"]["stage"] == "" and out["b"]["journalists"] == ""   # 경기 기사 필자는 기자 목록에 안 넣는다
    assert not nc._person_like("Get French Football News") and nc._person_like("Gianluca Di Marzio")


def test_story_cluster_across_languages() -> None:
    arts = [
        {"link": "1", "headline": "Milan step up pursuit of Club Brugge striker Tresoldi", "source": "LiveScore",
         "published": "2026-10-17", "kind": "transfer", "stage": "interest", "all_players": ["Nicolò Tresoldi"], "players": []},
        {"link": "2", "headline": "Club Brugge houdt been stijf voor Tresoldi", "source": "VoetbalPrimeur.be",
         "published": "2026-10-20", "kind": "transfer", "stage": "denied", "all_players": ["Nicolò Tresoldi"], "players": ["Nicolò Tresoldi"]},
        {"link": "3", "headline": "Milan close to agreement for Tresoldi", "source": "Football Italia",
         "published": "2026-10-18", "kind": "transfer", "stage": "agreed", "all_players": ["Nicolò Tresoldi"], "players": []},
        {"link": "4", "headline": "Mechele breaks nose against Genk", "source": "HLN", "published": "2026-10-19", "kind": "injury",
         "stage": "", "all_players": ["Brandon Mechele"], "players": ["Brandon Mechele"]},
    ]
    st = ns.cluster(arts, team_words={"Club Brugge"})
    assert len(st) == 1                                   # 매체 하나뿐인 부상 기사는 STORY 가 아니다
    s = st[0]
    assert set(s["links"]) == {"1", "2", "3"} and len(s["sources"]) == 3
    assert s["stage"] == "denied"                         # 맨 마지막 기사가 부인
    assert s["first"] == "2026-10-17" and s["last"] == "2026-10-20"
    arts[1]["stage"] = "talks"
    assert ns.cluster(arts, team_words={"Club Brugge"})[0]["stage"] == "agreed"   # 가장 앞선 단계
    # 같은 날 관심 기사와 부인 기사가 함께 있으면(순서 모름) 부인
    arts[1]["stage"] = "denied"
    arts.append({"link": "5", "headline": "Arsenal keen on Tresoldi", "source": "Mirror", "published": "2026-10-20",
                 "kind": "transfer", "stage": "interest", "all_players": ["Nicolò Tresoldi"], "players": []})
    assert ns.cluster(arts, team_words={"Club Brugge"})[0]["stage"] == "denied"


def test_betting_filtered() -> None:
    assert not gn.keep("Pronostic Bruges – RC Lens (21/10) : prono, cotes et compos", "But! Football Club")
    assert not gn.keep("KRC Genk - Standard Luik voorspelling - Odds & statistieken", "Wincomparator")
    assert not gn.keep("Club Brugge vs Lens prediction", "BetMines")


def test_join_idioms_and_draw_against_are_not_transfers() -> None:
    """'joins the drama·elite company' 는 이적이 아니고, 'draw against' 는 경기(2026-10-22 검수 — 경기 기사가 루머 '확정'으로)."""
    import news_classify as nc  # noqa: PLC0415
    assert nc.rule_kind("Mateo Chávez Joins the Drama: AZ Alkmaar Snatches Last-Minute Draw Against SC Cambuur") == "match"
    assert nc.rule_kind("Jurrien Timber joins elite company at Arsenal") == "other"
    assert nc.rule_kind("Wirtz joins Liverpool in £116m deal") == "transfer"
    assert nc.rule_kind("Leeds join the race for Bayern defender") == "transfer"
