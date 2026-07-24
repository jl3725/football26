from __future__ import annotations

from scripts.validate_data import validate


def test_all_core_data_contracts() -> None:
    errors, _warnings = validate(include_optional=False)
    assert errors == []
