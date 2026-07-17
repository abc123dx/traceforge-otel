from __future__ import annotations

import pytest

from traceforge.costs import CostModel, CostModelError


def test_exact_prefix_and_wildcard_resolution() -> None:
    model = CostModel.from_dict(
        {
            "models": {
                "exact": {"input_per_1m": 1, "output_per_1m": 2},
                "vendor/fast-*": {"input_per_1m": 3, "output_per_1m": 4},
                "*": {"input_per_1m": 5, "output_per_1m": 6},
            }
        }
    )

    assert model.estimate("exact", 1_000_000, 0) == 1
    assert model.estimate("vendor/fast-v2", 1_000_000, 0) == 3
    assert model.estimate("other", 0, 1_000_000) == 6


def test_rejects_negative_rates() -> None:
    with pytest.raises(CostModelError, match="不能为负数"):
        CostModel.from_dict({"models": {"bad": {"input_per_1m": -1, "output_per_1m": 2}}})
