from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.currency_rule import CurrencyRule
from app.models.pilot import Pilot
from app.models.flight import Flight
from app.models.user import User
from app.routers.auth import get_current_user, require_supervisor
from sqlalchemy import func

router = APIRouter(prefix="/api/currency", tags=["currency"])


# ── Schemas ──────────────────────────────────────────────────────────────

class RuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    vehicle_model: Optional[str] = None
    required_hours: float
    period_days: int
    required_flights: Optional[int] = None
    is_active: bool = True


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    vehicle_model: Optional[str] = None
    required_hours: Optional[float] = None
    period_days: Optional[int] = None
    required_flights: Optional[int] = None
    is_active: Optional[bool] = None


class RuleOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    vehicle_model: Optional[str]
    required_hours: float
    period_days: int
    required_flights: Optional[int]
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ── CRUD ─────────────────────────────────────────────────────────────────

@router.get("/rules", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(CurrencyRule).order_by(CurrencyRule.name).all()


@router.post("/rules", response_model=RuleOut)
def create_rule(data: RuleCreate, db: Session = Depends(get_db), user: User = Depends(require_supervisor)):
    rule = CurrencyRule(**data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/rules/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, data: RuleUpdate, db: Session = Depends(get_db), user: User = Depends(require_supervisor)):
    rule = db.query(CurrencyRule).filter(CurrencyRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(require_supervisor)):
    rule = db.query(CurrencyRule).filter(CurrencyRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"ok": True}


# ── Currency Status ──────────────────────────────────────────────────────

def _pilot_currency(pilot: Pilot, rules: list[CurrencyRule], db: Session):
    """Evaluate currency for a single pilot against all active rules."""
    rule_results = []
    for rule in rules:
        cutoff = datetime.utcnow() - timedelta(days=rule.period_days)

        q = db.query(Flight).filter(
            Flight.pilot_id == pilot.id,
            Flight.date >= cutoff.date(),
        )
        # If the rule is model-specific, filter flights by that vehicle model
        if rule.vehicle_model:
            from app.models.vehicle import Vehicle
            q = q.join(Vehicle, Flight.vehicle_id == Vehicle.id).filter(
                func.lower(Vehicle.model) == rule.vehicle_model.lower()
            )

        flights_in_period = q.all()
        actual_flights = len(flights_in_period)
        actual_hours = sum((f.duration_seconds or 0) for f in flights_in_period) / 3600.0

        hours_met = actual_hours >= rule.required_hours
        flights_met = True
        if rule.required_flights is not None:
            flights_met = actual_flights >= rule.required_flights

        is_current = hours_met and flights_met

        # Estimate expiry: find earliest flight that, once it falls outside window, would lapse currency
        # Simplification: currency expires period_days after the oldest qualifying flight
        expires_date = None
        if is_current and flights_in_period:
            sorted_flights = sorted(flights_in_period, key=lambda f: f.date or cutoff.date())
            # Currency will expire when the oldest flight ages out of the window
            oldest_date = sorted_flights[0].date
            if oldest_date:
                expires_date = str(oldest_date + timedelta(days=rule.period_days))

        rule_results.append({
            "rule_id": rule.id,
            "rule_name": rule.name,
            "vehicle_model": rule.vehicle_model,
            "required_hours": rule.required_hours,
            "actual_hours": round(actual_hours, 2),
            "required_flights": rule.required_flights,
            "actual_flights": actual_flights,
            "is_current": is_current,
            "expires_date": expires_date,
            "period_days": rule.period_days,
        })

    return rule_results


@router.get("/status")
def get_all_currency_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get currency status for all active pilots."""
    rules = db.query(CurrencyRule).filter(CurrencyRule.is_active.is_(True)).all()
    pilots = db.query(Pilot).filter(Pilot.status == "active").order_by(Pilot.last_name).all()

    results = []
    for pilot in pilots:
        rule_results = _pilot_currency(pilot, rules, db)
        overall_current = all(r["is_current"] for r in rule_results) if rule_results else True
        results.append({
            "pilot_id": pilot.id,
            "pilot_name": pilot.full_name,
            "is_current": overall_current,
            "rules": rule_results,
        })

    return results


@router.get("/status/{pilot_id}")
def get_pilot_currency_status(pilot_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get currency status for a single pilot."""
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail="Pilot not found")

    rules = db.query(CurrencyRule).filter(CurrencyRule.is_active.is_(True)).all()
    rule_results = _pilot_currency(pilot, rules, db)
    overall_current = all(r["is_current"] for r in rule_results) if rule_results else True

    return {
        "pilot_id": pilot.id,
        "pilot_name": pilot.full_name,
        "is_current": overall_current,
        "rules": rule_results,
    }
