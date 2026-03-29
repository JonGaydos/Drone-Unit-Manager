"""Automatic flight tagging engine.

Analyzes flight metadata and telemetry data to generate descriptive tags
like "Night Flight", "High Speed", "Low Battery", etc.
"""

import math
from datetime import datetime


def compute_flight_tags(flight, telemetry_points: list = None) -> list[str]:
    """Analyze a flight and its telemetry to generate auto-tags.

    Args:
        flight: A Flight ORM instance with metadata fields.
        telemetry_points: Optional list of TelemetryPoint instances.

    Returns:
        List of tag strings describing notable flight characteristics.
    """
    tags = []

    # Night Flight — takeoff between 8pm and 6am (approximate)
    if flight.takeoff_time:
        hour = flight.takeoff_time.hour
        if hour >= 20 or hour < 6:
            tags.append("Night Flight")

    # Long Duration — over 30 minutes
    if flight.duration_seconds and flight.duration_seconds > 1800:
        tags.append("Long Duration")

    # High Speed — max speed over 15 m/s (~33 mph)
    if flight.max_speed_mps and flight.max_speed_mps > 15:
        tags.append("High Speed")

    # High Altitude — max altitude over 100m (~328ft)
    if flight.max_altitude_m and flight.max_altitude_m > 100:
        tags.append("High Altitude")

    # Extended Range — distance over 1000m from takeoff
    if flight.distance_m and flight.distance_m > 1000:
        tags.append("Extended Range")

    # Telemetry-based tags
    if telemetry_points:
        # Low Battery — any point below 20%
        for pt in telemetry_points:
            if pt.battery_pct is not None and pt.battery_pct < 20:
                tags.append("Low Battery")
                break

        # Rapid Descent — check for steep altitude drops (optional, based on data)
        if len(telemetry_points) > 10:
            max_alt = max((pt.altitude_m or 0) for pt in telemetry_points)
            if max_alt > 50:
                tags.append("Elevated Flight")

    return tags
