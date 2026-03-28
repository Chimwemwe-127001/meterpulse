"""
Anomaly Detection Service
Rule-based detection of suspicious meter reading patterns.
"""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.reading import Reading
from app.models.alert import Alert


# Detection thresholds
SPIKE_MULTIPLIER = 1.5  # Alert if consumption > 1.5x rolling average
ROLLING_WINDOW = 10     # Number of readings to compute rolling average


@dataclass
class DetectedAnomaly:
    """Represents a detected anomaly before it's persisted."""
    alert_type: str
    severity: str
    message: str


def get_rolling_average(readings: list[Reading]) -> float | None:
    """
    Calculate rolling average consumption from previous readings.
    
    Args:
        readings: List of recent readings (newest first)
        
    Returns:
        Rolling average or None if insufficient data
    """
    consumptions = [
        r.consumption for r in readings 
        if r.consumption is not None and r.consumption > 0
    ]
    
    if not consumptions:
        return None
    
    return sum(consumptions) / len(consumptions)


def detect_spike(
    consumption: float,
    rolling_avg: float | None,
) -> DetectedAnomaly | None:
    """
    Detect consumption spike.
    
    Rule: consumption > 1.5x rolling average → HIGH severity
    
    Real-world meaning: Sudden unusual surge — possible burst pipe, 
    theft, or equipment fault.
    """
    if rolling_avg is None or rolling_avg <= 0:
        return None
    
    if consumption > rolling_avg * SPIKE_MULTIPLIER:
        multiplier = round(consumption / rolling_avg, 1)
        return DetectedAnomaly(
            alert_type="SPIKE",
            severity="HIGH",
            message=f"Consumption {consumption:.1f} is {multiplier}x above rolling average of {rolling_avg:.1f}",
        )
    
    return None


def detect_zero_reading(
    consumption: float | None,
    previous_consumption: float | None,
) -> DetectedAnomaly | None:
    """
    Detect zero consumption when previous was positive.
    
    Rule: consumption == 0 and previous > 0 → MEDIUM severity
    
    Real-world meaning: Meter stopped reporting — possible device 
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
    new_value: float,
    previous_value: float | None,
) -> DetectedAnomaly | None:
    """
    Detect negative delta (new reading < previous reading).
    
    Rule: new value < previous value → HIGH severity
    
    Real-world meaning: Reading lower than last — meter tampering 
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
    1. Fetch last N readings for the meter
    2. Compute rolling average consumption
    3. Run three checks: SPIKE, ZERO_READING, NEGATIVE_DELTA
    4. Create and persist Alert records for any triggered rules
    
    Args:
        meter_id: ID of the meter being read
        new_reading: The newly submitted reading (already committed)
        db: Database session
        
    Returns:
        List of created Alert objects
    """
    # Fetch previous readings (excluding the new one)
    previous_readings = (
        db.query(Reading)
        .filter(
            Reading.meter_id == meter_id,
            Reading.id != new_reading.id,
        )
        .order_by(Reading.recorded_at.desc())
        .limit(ROLLING_WINDOW)
        .all()
    )
    
    # Get the most recent previous reading
    previous_reading = previous_readings[0] if previous_readings else None
    previous_value = previous_reading.value if previous_reading else None
    previous_consumption = previous_reading.consumption if previous_reading else None
    
    # Calculate rolling average
    rolling_avg = get_rolling_average(previous_readings)
    
    # Run detection checks
    detected: list[DetectedAnomaly] = []
    
    # Check 1: Negative delta (most critical - check first)
    anomaly = detect_negative_delta(new_reading.value, previous_value)
    if anomaly:
        detected.append(anomaly)
    
    # Check 2: Spike detection
    if new_reading.consumption is not None and new_reading.consumption > 0:
        anomaly = detect_spike(new_reading.consumption, rolling_avg)
        if anomaly:
            detected.append(anomaly)
    
    # Check 3: Zero reading
    anomaly = detect_zero_reading(new_reading.consumption, previous_consumption)
    if anomaly:
        detected.append(anomaly)
    
    # Create Alert records
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
        db.commit()
        for alert in alerts:
            db.refresh(alert)
    
    return alerts
