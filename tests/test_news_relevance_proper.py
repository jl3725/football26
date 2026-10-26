"""뉴스 관련성 — 이름이 고유명사 꼴로 쓰였을 때만, 팀 기사에서 소문자로 흔한 이름 낱말은 뺀다(2026-10-26)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import news_relevance as nr  # noqa: E402


def test_common_phrase_not_a_mention():
    terms = nr.team_terms("Young Boys", ("BSC Young Boys",))
    assert not nr.mentions("Daytona Beach considers pond fencing after deaths of 2 young boys", terms)
    assert not nr.mentions("Camp leader who drugged and sexually abused boys loses bid", terms)
    assert nr.mentions("Young Boys knacken zähe St. Galler", terms)
    assert nr.mentions("Super League: BSC Young Boys gegen FC St. Gallen", terms)


def test_proper_name_with_short_particle_and_unicode():
    terms = nr.team_terms("Vit. Guimarães", ("Vitória de Guimarães",))
    assert nr.mentions("Vitória de Guimarães vence em casa", terms)
    t2 = nr.team_terms("Gençlerbirliği", ())
    assert nr.mentions("Konyaspor-Gençlerbirliği maçını kim yönetecek?", t2)
    assert not nr.mentions("Simon Jordan angers Newcastle fans", nr.team_terms("Angers", ()))


def test_common_words_from_team_feed():
    terms = nr.team_terms("Villarreal", ("Villarreal Club de Fútbol",))
    texts = ["El fútbol es así", "Villarreal gana", "fútbol base", "La Liga de fútbol", "más fútbol", "fútbol total", "Villarreal pierde"]
    weak = nr.common_words(texts, terms)
    assert "futbol" in weak and "villarreal" not in weak


def test_other_squad_women_youth_other_sports():
    yes = [("La Real femenina anuncia a su nuevo entrenador", "", ""),
           ("Eintracht Frankfurt: Boss Hellmann will Frauenfußball-Revolution", "", ""),
           ("Previa Liga F, Jornada 8: Athletic Club vs Sevilla FC", "", ""),
           ("Relief for Slegers as Russo rescues Arsenal against Tottenham in WSL", "", ""),
           ("Leeds United U21 manager Scott Gardner after 4-3 EFL Trophy win", "", ""),
           ("Il Como Primavera non sbaglia", "", ""),
           ("3-2: Schröder y el orgullo blanco reinan en un derbi loco", "", "https://www.mundodeportivo.com/futbol/femenino/20260830/1/x"),
           ("Relief for Slegers as Russo rescues Arsenal", "", "https://www.theguardian.com/football/2026/oct/24/tottenham-arsenal-wsl-match-report")]
    no = [("BBC Sport's Sam Harris explains the footage showing Nico Williams handball", "", ""),   # 축구의 핸드볼 반칙
          ("West Ham United bring in Norway U21 international winger Edvin Austbo", "", ""),       # 1군 선수 소개의 U21
          ("Iago Aspas tendrá su escultura en primavera", "", ""),                                 # 스페인어 '봄'
          ("Santa Clara é uma das 11 equipas invictas esta época", "", ""),                        # 포르투갈어 '팀' 여성명사
          ("Arsenal beat Chelsea", "", "https://www.bbc.co.uk/sport/football/articles/abc")]
    for h, r, link in yes:
        assert nr.other_squad(h, r, link), h
    for h, r, link in no:
        assert not nr.other_squad(h, r, link), h


def test_relevant_drops_women_even_if_tagged():
    row = {"headline": "Arsenal Women beat Chelsea", "descr": "", "published": "2099-01-01", "first_seen": "2099-01-01"}
    assert not nr.relevant(row, nr.team_terms("Arsenal", ()), tagged=True)
