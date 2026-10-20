"""IDENTITY — 출처별 클럽 표기를 표준 이름과 잇는다(약어·머리글자·접두어·일반어), 애매하면 등록하지 않는다."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import identity as idn  # noqa: E402

PT = ["Académico de Viseu", "Benfica", "Marítimo", "Porto", "Sporting CP", "Vit. Guimarães", "Gil Vicente FC"]
NL = ["Ajax", "Cambuur", "Excelsior", "NEC Nijmegen", "PSV", "Sparta R.", "Willem II"]
BE = ["Club Brugge", "Cercle Brugge", "OH Leuven", "Sint-Truiden", "Union SG", "Kortrijk"]
ES = ["Racing Santander", "Real Sociedad", "Real Madrid", "Málaga"]


def test_matches_abbreviations_and_generic_words() -> None:
    cases = [("Vitória de Guimarães", PT, "Vit. Guimarães"), ("CS Marítimo", PT, "Marítimo"),
             ("Sparta Rotterdam", NL, "Sparta R."), ("N.E.C.", NL, "NEC Nijmegen"), ("Willem II Tilburg", NL, "Willem II"),
             ("Union St.Gilloise", BE, "Union SG"), ("Oud-Heverlee Leuven", BE, "OH Leuven"), ("St.Truiden", BE, "Sint-Truiden"),
             ("Club Brugge KV", BE, "Club Brugge"), ("Málaga CF", ES, "Málaga")]
    for src, canon, want in cases:
        best, s1, s2 = idn.best_match(src, canon)
        assert best == want and s1 >= idn.AUTO_MIN and s1 - s2 >= idn.MARGIN, (src, best, s1, s2)


def test_ambiguous_is_not_auto_registered() -> None:
    best, s1, s2 = idn.best_match("Real Racing Club", ES)
    assert not (s1 >= idn.AUTO_MIN and s1 - s2 >= idn.MARGIN)       # Racing Santander·Real Sociedad 사이 애매 → 확인 필요


def test_canonical_squad_uses_auto_aliases(tmp_path, monkeypatch) -> None:
    import squads
    p = tmp_path / "club_aliases_auto.csv"
    pd.DataFrame([{"league": "Eredivisie", "source_name": "Sparta Rotterdam", "canonical": "Sparta R.", "score": "0.9",
                   "sources": "fotmob_ratings", "first_seen": "2026-10-20"}]).to_csv(p, index=False)
    monkeypatch.setattr(squads, "_auto_aliases", lambda: {"Eredivisie": {"Sparta Rotterdam": "Sparta R."}})
    assert squads.canonical_squad("Sparta Rotterdam", "Eredivisie") == "Sparta R."
    assert squads.canonical_squad("Sparta Rotterdam", "EPL") == "Sparta Rotterdam"   # 리그별
    import datastore as ds
    df = pd.DataFrame({"squad": ["Sparta Rotterdam", "Ajax"], "player": ["A", "B"]})
    assert list(ds._canon_squads(df, "Eredivisie")["squad"]) == ["Sparta R.", "Ajax"]
