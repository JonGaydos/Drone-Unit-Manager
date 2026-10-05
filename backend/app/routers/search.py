"""Global cross-entity search powering the command palette (Ctrl+K)."""
from fastapi import APIRouter
from sqlalchemy import or_

from app.deps import DBSession, CurrentUser
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.flight import Flight
from app.services.pilot_contacts import hides_contacts

router = APIRouter(prefix="/api/search", tags=["search"])


def _search_pilots(db, like: str, limit: int, with_email: bool = True) -> list[dict]:
    """Pilots whose first/last name, or email when it may be shown, matches `like`."""
    results = []
    fields = [Pilot.first_name.ilike(like), Pilot.last_name.ilike(like)]
    if with_email:
        fields.append(Pilot.email.ilike(like))
    for p in db.query(Pilot).filter(or_(*fields)).limit(limit).all():
        name = f"{p.first_name or ''} {p.last_name or ''}".strip()
        email = p.email if with_email else None
        results.append({
            "type": "pilot",
            "title": name or (email or f"Pilot #{p.id}"),
            "subtitle": email or (p.status or ""),
            "url": f"/pilots/{p.id}",
        })
    return results


def _search_vehicles(db, like: str, limit: int) -> list[dict]:
    """Vehicles whose serial / nickname / model / manufacturer matches `like`."""
    results = []
    for v in db.query(Vehicle).filter(or_(
        Vehicle.serial_number.ilike(like),
        Vehicle.nickname.ilike(like),
        Vehicle.model.ilike(like),
        Vehicle.manufacturer.ilike(like),
    )).limit(limit).all():
        subtitle = f"{v.manufacturer or ''} {v.model or ''}".strip()
        results.append({
            "type": "vehicle",
            "title": v.nickname or v.serial_number or subtitle or f"Vehicle #{v.id}",
            "subtitle": subtitle or (v.serial_number or ""),
            "url": f"/fleet/vehicles/{v.id}",
        })
    return results


def _search_flights(db, like: str, limit: int) -> list[dict]:
    """Flights whose external id / case # / takeoff address / purpose matches `like`."""
    results = []
    for f in db.query(Flight).filter(or_(
        Flight.external_id.ilike(like),
        Flight.case_number.ilike(like),
        Flight.takeoff_address.ilike(like),
        Flight.purpose.ilike(like),
    )).order_by(Flight.date.desc()).limit(limit).all():
        title = f"Flight {f.date or ''}".strip()
        if f.purpose:
            title = f"{title} — {f.purpose}"
        results.append({
            "type": "flight",
            "title": title or f"Flight #{f.id}",
            "subtitle": f.takeoff_address or f.case_number or (f.external_id or "")[:12],
            "url": f"/flights/{f.id}",
        })
    return results


@router.get("")
def global_search(q: str, db: DBSession, user: CurrentUser, limit: int = 6):
    """Search pilots, vehicles, and flights. Returns typed results with a
    frontend URL each, for the global command palette."""
    query = (q or "").strip()
    if len(query) < 2:
        return {"query": query, "results": []}
    like = f"%{query}%"
    return {
        "query": query,
        "results": (
            _search_pilots(db, like, limit, with_email=not hides_contacts(user))
            + _search_vehicles(db, like, limit)
            + _search_flights(db, like, limit)
        ),
    }
