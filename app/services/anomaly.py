"""
Anomaly Detection Service
Rule-based detection of suspicious meter reading patterns.

Baseline statistics use the median and MAD (median absolute deviation)
rather than the mean: the mean has a breakdown point of 0, so a single
extreme reading in the window masks later anomalies (and a gradual ramp
can poison the baseline). Median/MAD tolerate up to 50% contamination
(Leys et al. 2013). Consumption is normalized to a rate (units/day)
before comparison so irregular reading intervals don't look like spikes.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.reading import Reading
from app.models.alert import Alert


# Detection thresholds
SPIKE_MULTIPLIER = 1.5    # Rate must also exceed 1.5x median (guards tiny-MAD windows)
ROBUST_Z_THRESHOLD = 3.0  # Flag rates more than 3 robust deviations above median
MAD_SCALE = 1.4826        # Consistency constant: scaled MAD estimates sigma for normal data
MIN_SAMPLES = 5           # Minimum historical rates before SPIKE can trigger
ROLLING_WINDOW = 10       # Number of historical rates to compute the baseline


@dataclass
class DetectedAnomaly:
    """Represents a detected anomaly before it's persisted."""
    alert_type: str
    severity: str
    message: str


def as_utc(dt: datetime) -> datetime:
    """Attach UTC to naive datetimes (SQLite returns naive) for safe comparison."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def elapsed_days(start: datetime, end: datetime) -> float:
    """Elapsed time between two timestamps in (fractional) days."""
    return (as_utc(end) - as_utc(start)).total_seconds() / 86400


def get_consumption_rates(readings: list[Reading]) -> list[float]:
    """
    Convert consecutive readings into consumption rates (units/day).

    Args:
        readings: Recent readings, newest first.

    Returns:
        One rate per consecutive pair with valid consumption and a
        positive time gap. Zero rates are kept — excluding them would
        bias the baseline upward for intermittent consumers.
    """
    rates: list[float] = []
    for current, previous in zip(readings, readings[1:]):
        if current.consumption is None:
            continue
        days = elapsed_days(previous.recorded_at, current.recorded_at)
        if days <= 0:
            continue
        rates.append(float(current.consumption) / days)
    return rates


def detect_spike(rate: float, previous_rates: list[float]) -> DetectedAnomaly | None:
    """
    Detect a consumption-rate spike against a robust per-meter baseline.

    Rule: rate > median + 3 * (1.4826 * MAD) AND rate > 1.5x median,
    with at least MIN_SAMPLES historical rates -> HIGH severity.

    Real-world meaning: Sudden unusual surge - possible burst pipe,
    theft, or equipment fault.
    """
    if len(previous_rates) < MIN_SAMPLES:
        return None

    baseline = median(previous_rates)
    if baseline <= 0:
        return None

    mad = median(abs(r - baseline) for r in previous_rates)
    robust_sigma = MAD_SCALE * mad

    if robust_sigma > 0:
        exceeds_deviation = rate > baseline + ROBUST_Z_THRESHOLD * robust_sigma
    else:
        # All historical rates identical: fall back to the multiplier alone
        exceeds_deviation = True

    if exceeds_deviation and rate > baseline * SPIKE_MULTIPLIER:
        multiplier = round(rate / baseline, 1)
        return DetectedAnomaly(
            alert_type="SPIKE",
            severity="HIGH",
            message=(
                f"Consumption rate {rate:.1f}/day is {multiplier}x above "
                f"the meter's median rate of {baseline:.1f}/day"
            ),
        )

    return None


def detect_zero_reading(
    consumption,
    previous_consumption,
) -> DetectedAnomaly | None:
    """
    Detect zero consumption when previous was positive.

    Rule: consumption == 0 and previous > 0 -> MEDIUM severity

    Real-world meaning: Meter stopped reporting - possible device
    fault or disconnection.
    """
    if consumption is None:
        return None

    if consumption == 0 and previous_consumption is not None and previous_consumption > 0:
        return DetectedAnomaly(
            alert_type="ZERO_READING",
            severity="MEDIUM",
            message=f"Zero consumption detected after previous reading of {previous_consumption:.1f}. Possible device fault.",
        )

    return None


def detect_negative_delta(
    new_value,
    previous_value,
) -> DetectedAnomaly | None:
    """
    Detect negative delta (new reading < previous reading).

    Rule: new value < previous value -> HIGH severity

    Real-world meaning: Reading lower than last - meter tampering
    or rollover error.
    """
    if previous_value is None:
        return None

    if new_value < previous_value:
        delta = previous_value - new_value
        return DetectedAnomaly(
            alert_type="NEGATIVE_DELTA",
            severity="HIGH",
            message=f"Reading decreased by {delta:.1f} units (from {previous_value:.1f} to {new_value:.1f}). Possible tampering or meter rollover.",
        )

    return None


def detect_anomalies(
    meter_id: UUID,
    new_reading: Reading,
    db: Session,
) -> list[Alert]:
    """
    Run all anomaly detection checks on a new reading.

    Detection Pipeline:
    1. Fetch recent readings for the meter
    2. Compute robust baseline (median/MAD) of consumption rates
    3. Run three checks: SPIKE, ZERO_READING, NEGATIVE_DELTA
    4. Add Alert records to the session for any triggered rules

    The caller owns the transaction: alerts are added and flushed but
    NOT committed here, so a reading and its alerts persist atomically.

    Args:
        meter_id: ID of the meter being read
        new_reading: The newly submitted reading (flushed, not yet committed)
        db: Database session

    Returns:
        List of Alert objects added to the session
    """
    # Fetch previous readings (excluding the new one).
    # +1 so ROLLING_WINDOW rates can be derived from consecutive pairs.
    previous_readings = (
        db.query(Reading)
        .filter(
            Reading.meter_id == meter_id,
            Reading.id != new_reading.id,
        )
        .order_by(Reading.recorded_at.desc())
        .limit(ROLLING_WINDOW + 1)
        .all()
    )

    previous_reading = previous_readings[0] if previous_readings else None
    previous_value = previous_reading.value if previous_reading else None
    previous_consumption = previous_reading.consumption if previous_reading else None

    # Historical consumption rates (units/day), newest first
    previous_rates = get_consumption_rates(previous_readings)

    detected: list[DetectedAnomaly] = []

    # Check 1: Negative delta (most critical - check first)
    anomaly = detect_negative_delta(new_reading.value, previous_value)
    if anomaly:
        detected.append(anomaly)

    # Check 2: Spike detection (on the new reading's consumption rate)
    if new_reading.consumption is not None and new_reading.consumption > 0 and previous_reading:
        days = elapsed_days(previous_reading.recorded_at, new_reading.recorded_at)
        if days > 0:
            new_rate = float(new_reading.consumption) / days
            anomaly = detect_spike(new_rate, previous_rates)
            if anomaly:
                detected.append(anomaly)

    # Check 3: Zero reading
    anomaly = detect_zero_reading(new_reading.consumption, previous_consumption)
    if anomaly:
        detected.append(anomaly)

    # Add Alert records to the session (committed by the caller)
    alerts: list[Alert] = []
    for det in detected:
        alert = Alert(
            meter_id=meter_id,
            reading_id=new_reading.id,
            alert_type=det.alert_type,
            severity=det.severity,
            message=det.message,
        )
        db.add(alert)
        alerts.append(alert)

    if alerts:
        db.flush()

    return alerts
