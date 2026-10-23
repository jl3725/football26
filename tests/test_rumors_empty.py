"""TM 구단 루머 — '루머 없음' 진짜 페이지와 차단 페이지 구분(2026-10-23 Eredivisie·스위스 0건 빨간불)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import fetch_transfer_rumors as fr  # noqa: E402

EMPTY = """<html><head><title>Ajax Amsterdam - Club transfer rumours | Transfermarkt</title></head><body><main>
<div class="box"><h2 class="content-box-headline">Rumours about signings</h2>
<div class="tm-tabs">Club rumours</div><div>Compact Detailed Gallery</div><div class="empty">No information</div></div>
</main></body></html>"""
CHALLENGE = "<html><head><title>Just a moment...</title></head><body><div>Checking your browser</div></body></html>"
TABLE = """<html><body><div class="box"><h2>Rumours about signings</h2><table class="items"><tbody>
<tr><td>1</td><td><a href="#">X</a></td><td></td><td>24</td><td><a title="Roma">Roma</a></td><td>€20.00m</td><td>21/10/2026</td><td>40 %</td></tr>
</tbody></table></div></body></html>"""


def test_confirmed_empty_page() -> None:
    assert fr.confirmed_empty(EMPTY) is True
    assert fr.confirmed_empty(CHALLENGE) is False          # 차단·챌린지 → 예전처럼 실패
    assert fr.confirmed_empty(TABLE) is False              # 루머 표가 있으면 빈 페이지 아님
    assert len(fr._parse(TABLE, "Ajax")) == 1 and fr._parse(EMPTY, "Ajax") == []
