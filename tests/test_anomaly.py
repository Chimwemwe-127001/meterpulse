"""
Unit tests for the anomaly detection rules (pure functions, no DB).
"""
from decimal import Decimal

from app.services.anomaly import (
    detect_spike,
    detect_zero_reading,
    detect_negative_delta,
    MIN_SAMPLES,
)


class TestDetectSpike:
    def test_insufficient_samples_never_alerts(self):
        # Fewer than MIN_SAMPLES historical rates: even a huge value
        # must not alert (a single prior delta is not a baseline).
        assert detect_spike(1000.0, [10.0] * (MIN_SAMPLES - 1)) is None

    def test_no_alert_on_normal_rate(self):
        rates = [8.0, 10.0, 12.0, 9.0, 11.0]
        assert detect_spike(11.0, rates) is None

    def test_alerts_on_clear_spike(self):
        rates = [8.0, 10.0, 12.0, 9.0, 11.0]
        anomaly = detect_spike(30.0, rates)
        assert anomaly is not None
        assert anomaly.alert_type == "SPIKE"
        assert anomaly.severity == "HIGH"

    def test_median_baseline_resists_masking(self):
        # One extreme value in the window drags the MEAN to 48, so a
        # mean-based 1.5x rule (threshold 72) would miss a 60/day spike.
        # The median baseline (10) still catches it.
        contaminated = [10.0, 10.0, 10.0, 10.0, 200.0]
        anomaly = detect_spike(60.0, contaminated)
        assert anomaly is not None
        assert anomaly.alert_type == "SPIKE"

    def test_identical_history_falls_back_to_multiplier(self):
        # MAD == 0 (zero variance history): multiplier rule alone applies
        rates = [10.0] * MIN_SAMPLES
        assert detect_spike(14.0, rates) is None       # below 1.5x
        assert detect_spike(16.0, rates) is not None   # above 1.5x

    def test_zero_baseline_never_alerts(self):
        assert detect_spike(50.0, [0.0] * MIN_SAMPLES) is None


class TestDetectZeroReading:
    def test_zero_after_positive_alerts(self):
        anomaly = detect_zero_reading(Decimal("0"), Decimal("12.5"))
        assert anomaly is not None
        assert anomaly.alert_type == "ZERO_READING"
        assert anomaly.severity == "MEDIUM"

    def test_zero_after_zero_does_not_realert(self):
        assert detect_zero_reading(Decimal("0"), Decimal("0")) is None

    def test_none_consumption_ignored(self):
        assert detect_zero_reading(None, Decimal("5")) is None

    def test_positive_consumption_ignored(self):
        assert detect_zero_reading(Decimal("3"), Decimal("5")) is None


class TestDetectNegativeDelta:
    def test_decreasing_value_alerts(self):
        anomaly = detect_negative_delta(Decimal("90"), Decimal("100"))
        assert anomaly is not None
        assert anomaly.alert_type == "NEGATIVE_DELTA"
        assert anomaly.severity == "HIGH"

    def test_equal_value_does_not_alert(self):
        assert detect_negative_delta(Decimal("100"), Decimal("100")) is None

    def test_first_reading_does_not_alert(self):
        assert detect_negative_delta(Decimal("100"), None) is None
