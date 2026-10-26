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
