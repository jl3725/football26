"""짧은 이름(src/short_name.py · 웹 lib/names.ts 같은 규칙) — 'van Dijk'·'Mac Allister' 가 'Dijk'·'Allister' 로 잘렸다(2026-10-27)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from short_name import surname  # noqa: E402

CASES = [("Virgil van Dijk", "van Dijk"), ("Alexis Mac Allister", "Mac Allister"), ("Kevin De Bruyne", "De Bruyne"),
         ("Ben White", "White"), ("Wissam Ben Yedder", "Ben Yedder"), ("Son Heung-min", "Son"), ("Kim Min-jae", "Kim"),
         ("Trent Alexander-Arnold", "Alexander-Arnold"), ("Vinícius Júnior", "Vinícius Júnior"), ("Bukayo Saka", "Saka"),
         ("Rodrygo", "Rodrygo"), ("Frenkie de Jong", "de Jong"), ("Marc-André ter Stegen", "ter Stegen"), ("Rafael da Silva", "da Silva"),
         ("—", "—"), ("", "")]


def test_surname_cases():
    for name, want in CASES:
        assert surname(name) == want, name


def test_same_rule_as_web():
    ts = (Path(__file__).resolve().parent.parent / "web" / "lib" / "names.ts").read_text(encoding="utf-8")
    import short_name as sn
    for w in sn.PARTICLES | sn.SUFFIX:
        assert f'"{w}"' in ts, f"웹 lib/names.ts 에 '{w}' 가 없다 — 두 규칙을 같이 고칠 것"
