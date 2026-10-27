

def test_acronym_club_names_need_capitals():
    # 언론은 'NEC Nijmegen'을 'NEC', 덴마크 'OB' 는 약자로 쓴다 — 약자는 원문도 전부 대문자일 때만(독일어 'Ob'·영어 'if' 와 섞이지 않게)
    import news_relevance as nr
    nec = nr.team_terms("NEC Nijmegen", ("N.E.C.",))
    assert nr.mentions("Bekijk de samenvatting van NEC - FC Groningen", nec)
    ob = nr.team_terms("OB", ("Odense Boldklub",))
    assert nr.mentions("OB vinder over Brøndby", ob) and not nr.mentions("Ob er det sidste kampe?", ob)
    assert "ak" not in nr.team_terms("Grazer AK", ()) and "if" not in nr.team_terms("Brøndby IF", ())   # 클럽 형태 약자는 아님


def test_saint_abbreviation_kept_in_search_names():
    import news_sources as ns
    assert ns.names_for("St. Gallen", "FC St. Gallen", "Vit. Guimarães", "Sparta R.") == ["St. Gallen", "FC St. Gallen"]
    assert "Denmark" in ns.NO_EDITION       # 구글 뉴스에 덴마크판이 없다 — 영어판 + 리그 한정어
