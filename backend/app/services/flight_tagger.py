"""Automatic flight tagging engine.

Analyzes flight metadata and telemetry data to generate descriptive tags
like "Night Flight", "High Speed", "Low Battery", etc.
"""

def _metadata_tags(flight) -> list[str]:
    """Generate tags from flight metadata fields."""
    tags = []
    if flight.takeoff_time:
        hour = flight.takeoff_time.hour
        if hour >= 20 or hour < 6:
            tags.append("Night Flight")
    if flight.duration_seconds and flight.duration_seconds > 1800:
        tags.append("Long Duration")
    if flight.max_speed_mps and flight.max_speed_mps > 15:
        tags.append("High Speed")
    if flight.max_altitude_m and flight.max_altitude_m > 100:
        tags.append("High Altitude")
    if flight.distance_m and flight.distance_m > 1000:
        tags.append("Extended Range")
    return tags


def _telemetry_tags(telemetry_points: list) -> list[str]:
    """Generate tags from telemetry data points."""
    tags = []
    for pt in telemetry_points:
        if pt.battery_pct is not None and pt.battery_pct < 20:
            tags.append("Low Battery")
            break
    if len(telemetry_points) > 10:
        max_alt = max((pt.altitude_m or 0) for pt in telemetry_points)
        if max_alt > 50:
            tags.append("Elevated Flight")
    return tags


def compute_flight_tags(flight, telemetry_points: list = None) -> list[str]:
    """Analyze a flight and its telemetry to generate auto-tags.

    Args:
        flight: A Flight ORM instance with metadata fields.
        telemetry_points: Optional list of TelemetryPoint instances.

    Returns:
        List of tag strings describing notable flight characteristics.
    """
    tags = _metadata_tags(flight)
    if telemetry_points:
        tags.extend(_telemetry_tags(telemetry_points))
    return tags
