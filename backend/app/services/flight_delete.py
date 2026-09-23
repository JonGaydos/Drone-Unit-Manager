"""Deleting flights along with what points at them.

Every path that removes flights (the flights page, bulk delete, and the sync
cleanups) goes through here, so none of them can leave incidents, plans,
checklists, media, photo links or telemetry pointing at a flight id that
SQLite may later hand to a new flight.
"""

from app.models.flight import Flight


def purge_flight_references(db, ids: list[int]) -> None:
    """Detach or remove rows that reference the given flights."""
    if not ids:
        return
    from app.models.incident import Incident
    from app.models.checklist import ChecklistCompletion
    from app.models.flight_approval import FlightPlan
    from app.models.media import MediaFile
    from app.models.photo import PhotoFlight
    db.query(Incident).filter(Incident.flight_id.in_(ids)).update({Incident.flight_id: None}, synchronize_session=False)
    db.query(ChecklistCompletion).filter(ChecklistCompletion.flight_id.in_(ids)).update({ChecklistCompletion.flight_id: None}, synchronize_session=False)
    db.query(FlightPlan).filter(FlightPlan.linked_flight_id.in_(ids)).update({FlightPlan.linked_flight_id: None}, synchronize_session=False)
    db.query(MediaFile).filter(MediaFile.flight_id.in_(ids)).delete(synchronize_session=False)
    db.query(PhotoFlight).filter(PhotoFlight.flight_id.in_(ids)).delete(synchronize_session=False)


def purge_flight_telemetry(ids: list[int]) -> None:
    """Remove telemetry for the given flights. Call AFTER the main commit: the
    telemetry lives in its own database and cannot share that transaction."""
    if not ids:
        return
    from app.models.telemetry import TelemetryPoint
    from app.database import TelemetrySessionLocal
    tdb = TelemetrySessionLocal()
    try:
        tdb.query(TelemetryPoint).filter(TelemetryPoint.flight_id.in_(ids)).delete(synchronize_session=False)
        tdb.commit()
    finally:
        tdb.close()


def delete_flights(db, flights: list[Flight]) -> list[int]:
    """Delete ``flights`` and clear their references in the main database.

    Returns the deleted ids; the caller commits, then passes them to
    purge_flight_telemetry.
    """
    ids = [f.id for f in flights]
    purge_flight_references(db, ids)
    for flight in flights:
        db.delete(flight)
    return ids
