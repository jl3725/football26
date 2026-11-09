"""성 위치가 반대인 표기 — 'Kang-in Lee'(Sofascore·TM) ↔ 'Lee Kang-in'(선수 표). 2026-11-09 이강인·이재성·정우영 평점·TM id 끊김."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from short_name import swapped_order  # noqa: E402


def test_swapped_order_only_for_hyphenated_two_word_names() -> None:
    assert swapped_order("Kang-in Lee") == "Lee Kang-in"
    assert swapped_order("Woo-Yeong Jeong") == "Jeong Woo-Yeong"
    assert swapped_order("Lee Kang-in") == "Kang-in Lee"
    assert swapped_order("Bukayo Saka") is None and swapped_order("Virgil van Dijk") is None and swapped_order("") is None


def test_tm_contract_links_reversed_korean_name(tmp_path) -> None:
    import sync_transfermarkt_contracts as stc
    pf = tmp_path / "pf.csv"
    pd.DataFrame([{"squad": "Atlético Madrid", "player": "Lee Kang-in"},
                  {"squad": "Atlético Madrid", "player": "Antoine Griezmann"}]).to_csv(pf, index=False)
    ct = pd.DataFrame([
        {"squad": "Atlético Madrid", "player": "Kang-in Lee", "norm_key": stc.norm("Kang-in Lee"), "tm_id": 557149,
         "contract_until": "2031-06-30", "joined_date": "2026-07-25", "detected_at": "2026-11-08"},
        {"squad": "Atlético Madrid", "player": "Antoine Griezmann", "norm_key": stc.norm("Antoine Griezmann"), "tm_id": 125781,
         "contract_until": "2027-06-30", "joined_date": "2019-07-14", "detected_at": "2026-11-08"},
    ])
    stc.merge_contracts(pf, ct)
    out = pd.read_csv(pf).set_index("player")
    assert str(out.loc["Lee Kang-in", "tm_id"]).startswith("557149") and str(out.loc["Antoine Griezmann", "tm_id"]).startswith("125781")
