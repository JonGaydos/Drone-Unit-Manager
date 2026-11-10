"""Global cross-entity search powering the command palette (Ctrl+K)."""
from fastapi import APIRouter
from sqlalchemy import or_

from app.deps import DBSession, CurrentUser
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.flight import Flight
from app.services.permissions import can
from app.services.pilot_contacts import hides_contacts

router = APIRouter(prefix="/api/search", tags=["search"])


def _search_pilots(db, text: str, limit: int, with_email: bool = True) -> list[dict]:
    """Pilots whose first/last name, or email when it may be shown, contains `text`."""
    results = []
    fields = [Pilot.first_name.icontains(text, autoescape=True), Pilot.last_name.icontains(text, autoescape=True)]
    if with_email:
        fields.append(Pilot.email.icontains(text, autoescape=True))
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


def _search_vehicles(db, text: str, limit: int) -> list[dict]:
    """Vehicles whose serial / nickname / model / manufacturer contains `text`."""
    results = []
    for v in db.query(Vehicle).filter(or_(
        Vehicle.serial_number.icontains(text, autoescape=True),
        Vehicle.nickname.icontains(text, autoescape=True),
        Vehicle.model.icontains(text, autoescape=True),
        Vehicle.manufacturer.icontains(text, autoescape=True),
    )).limit(limit).all():
        subtitle = f"{v.manufacturer or ''} {v.model or ''}".strip()
        results.append({
            "type": "vehicle",
            "title": v.nickname or v.serial_number or subtitle or f"Vehicle #{v.id}",
            "subtitle": subtitle or (v.serial_number or ""),
            "url": f"/fleet/vehicles/{v.id}",
        })
    return results


def _search_flights(db, text: str, limit: int) -> list[dict]:
    """Flights whose external id / case # / takeoff address / purpose contains `text`."""
    results = []
    for f in db.query(Flight).filter(or_(
        Flight.external_id.icontains(text, autoescape=True),
        Flight.case_number.icontains(text, autoescape=True),
        Flight.takeoff_address.icontains(text, autoescape=True),
        Flight.purpose.icontains(text, autoescape=True),
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
    frontend URL each, for the global command palette. Each group needs its
    feature's view permission."""
    query = (q or "").strip()
    if len(query) < 2:
        return {"query": query, "results": []}
    # icontains escapes % and _, so they match themselves rather than anything.
    results = []
    if can(db, user, "pilots.view"):
        results += _search_pilots(db, query, limit, with_email=not hides_contacts(db, user))
    if can(db, user, "fleet.view"):
        results += _search_vehicles(db, query, limit)
    if can(db, user, "flights.view"):
        results += _search_flights(db, query, limit)
    return {"query": query, "results": results}
