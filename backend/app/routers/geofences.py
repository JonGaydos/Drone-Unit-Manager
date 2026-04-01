import math
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.deps import CurrentUser, DBSession, SupervisorUser
from app.models.geofence import Geofence
from app.services.audit import log_action
from app.responses import responses

router = APIRouter(prefix="/api/geofences", tags=["geofences"])



class GeofenceCreate(BaseModel):
    name: str
    description: Optional[str] = None
    zone_type: str  # no_fly, restricted, authorized, caution
    geometry_type: str  # circle, polygon
    center_lat: Optional[float] = None
    center_lon: Optional[float] = None
    radius_m: Optional[float] = None
    polygon_points: Optional[list] = None
    max_altitude_m: Optional[float] = None
    is_active: bool = True
    source: Optional[str] = None
    notes: Optional[str] = None


class GeofenceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    zone_type: Optional[str] = None
    geometry_type: Optional[str] = None
    center_lat: Optional[float] = None
    center_lon: Optional[float] = None
    radius_m: Optional[float] = None
    polygon_points: Optional[list] = None
    max_altitude_m: Optional[float] = None
    is_active: Optional[bool] = None
    source: Optional[str] = None
    notes: Optional[str] = None


def _serialize(g: Geofence) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "description": g.description,
        "zone_type": g.zone_type,
        "geometry_type": g.geometry_type,
        "center_lat": g.center_lat,
        "center_lon": g.center_lon,
        "radius_m": g.radius_m,
        "polygon_points": g.polygon_points,
        "max_altitude_m": g.max_altitude_m,
        "is_active": g.is_active,
        "source": g.source,
        "notes": g.notes,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


def _haversine_m(lat1, lon1, lat2, lon2):
    """Distance in meters between two lat/lon points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _point_in_polygon(lat, lon, polygon):
    """Ray-casting algorithm for point-in-polygon."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if ((yi > lon) != (yj > lon)) and (lat < (xj - xi) * (lon - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


@router.get("/check")
def check_geofences(

    db: DBSession,

    user: CurrentUser,

    lat: float = Query(...),

    lon: float = Query(...),
):
    """Check if a lat/lon point is inside any active geofence."""
    fences = db.query(Geofence).filter(Geofence.is_active.is_(True)).all()
    results = []
    for g in fences:
        inside = False
        if g.geometry_type == "circle" and g.center_lat is not None and g.center_lon is not None and g.radius_m:
            dist = _haversine_m(lat, lon, g.center_lat, g.center_lon)
            inside = dist <= g.radius_m
        elif g.geometry_type == "polygon" and g.polygon_points:
            inside = _point_in_polygon(lat, lon, g.polygon_points)
        if inside:
            results.append({
                "id": g.id,
                "name": g.name,
                "zone_type": g.zone_type,
                "max_altitude_m": g.max_altitude_m,
            })
    return {"lat": lat, "lon": lon, "inside_geofences": results, "count": len(results)}


@router.get("")
def list_geofences(
    db: DBSession,
    user: CurrentUser,
    zone_type: Optional[str] = None,
    active_only: bool = True):
    q = db.query(Geofence)
    if active_only:
        q = q.filter(Geofence.is_active.is_(True))
    if zone_type:
        q = q.filter(Geofence.zone_type == zone_type)
    return [_serialize(g) for g in q.order_by(Geofence.name).all()]


@router.get("/{geofence_id}", responses=responses(401, 404))
def get_geofence(geofence_id: int, db: DBSession, user: CurrentUser):
    g = db.query(Geofence).filter(Geofence.id == geofence_id).first()
    if not g:
        raise HTTPException(404, "Geofence not found")
    return _serialize(g)


@router.post("", status_code=201, responses=responses(401))
def create_geofence(data: GeofenceCreate, db: DBSession, user: SupervisorUser):
    g = Geofence(
        name=data.name,
        description=data.description,
        zone_type=data.zone_type,
        geometry_type=data.geometry_type,
        center_lat=data.center_lat,
        center_lon=data.center_lon,
        radius_m=data.radius_m,
        polygon_points=data.polygon_points,
        max_altitude_m=data.max_altitude_m,
        is_active=data.is_active,
        source=data.source,
        notes=data.notes,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    log_action(db, user.id, user.display_name, "create", "geofence", g.id, data.name)
    return _serialize(g)


@router.patch("/{geofence_id}", responses=responses(401, 404))
def update_geofence(geofence_id: int, data: GeofenceUpdate, db: DBSession, user: SupervisorUser):
    g = db.query(Geofence).filter(Geofence.id == geofence_id).first()
    if not g:
        raise HTTPException(404, "Geofence not found")
    update_data = data.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(g, key, val)
    db.commit()
    db.refresh(g)
    log_action(db, user.id, user.display_name, "update", "geofence", g.id, g.name, changes=update_data)
    return _serialize(g)


@router.delete("/{geofence_id}", responses=responses(401, 404))
def delete_geofence(geofence_id: int, db: DBSession, user: SupervisorUser):
    g = db.query(Geofence).filter(Geofence.id == geofence_id).first()
    if not g:
        raise HTTPException(404, "Geofence not found")
    log_action(db, user.id, user.display_name, "delete", "geofence", g.id, g.name)
    db.delete(g)
    db.commit()
    return {"ok": True}
