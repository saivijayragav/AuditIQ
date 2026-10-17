"""Tests for the two reconciliation gates: rounding and materiality."""
from __future__ import annotations

import pytest

from auditiq.reconciliation.materiality import (
    MATERIAL,
    MINOR,
    ROUNDING,
    TIED,
    WATCH,
    MaterialityError,
    build_config,
    classify,
    rounding_tolerance,
    variance_percent,
)


def test_rounding_tolerance_scales_with_unit():
    assert rounding_tolerance("absolute", 2) == pytest.approx(0.005)
    assert rounding_tolerance("thousands", 2) == pytest.approx(5.0)
    assert rounding_tolerance("lakhs", 2) == pytest.approx(500.0)
    assert rounding_tolerance("crores", 2) == pytest.approx(50_000.0)
    assert rounding_tolerance("crores", 0) == pytest.approx(5_000_000.0)


def test_materiality_is_required():
    with pytest.raises(MaterialityError):
        build_config(None)
    with pytest.raises(MaterialityError):
        build_config(0)


def test_materiality_must_exceed_tolerance():
    with pytest.raises(MaterialityError, match="exceed the rounding tolerance"):
        build_config(10_000, unit="crores")  # tolerance is 50,000 at 2 decimals


def test_performance_materiality_default_ratio():
    config = build_config(1_000_000, unit="absolute")
    assert config.performance_materiality == pytest.approx(750_000)
    assert config.pm_ratio == pytest.approx(0.75)


def test_classify_two_gates():
    config = build_config(1_000_000, unit="absolute")
    tol = config.tolerance
    assert classify(0, config) == (TIED, "none")
    assert classify(tol, config) == (ROUNDING, "none")
    assert classify(tol * 2, config) == (MINOR, "minor")
    assert classify(config.performance_materiality, config) == (WATCH, "watch")
    assert classify(config.materiality, config) == (MATERIAL, "material")
    assert classify(-config.materiality, config) == (MATERIAL, "material")


def test_variance_percent_suppressed_for_small_bases():
    config = build_config(1_000_000, unit="absolute")
    assert variance_percent(50_000, 5_000_000, config) == pytest.approx(1.0)
    assert variance_percent(50_000, 100_000, config) is None


def test_scope_filter():
    config = build_config(1_000_000, statements=("BS",))
    assert config.in_scope("Balance Sheet")
    assert not config.in_scope("Statement of Profit and Loss")
