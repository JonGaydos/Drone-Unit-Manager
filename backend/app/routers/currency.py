from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.deps import DBSession, CurrentUser, SupervisorUser
from app.models.currency_rule import CurrencyRule
from app.models.pilot import Pilot
from app.models.flight import Flight
from app.responses import responses

router = APIRouter(prefix="/api/currency", tags=["currency"])



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
    description: Optional[str] = None
    vehicle_model: Optional[str] = None
    required_hours: float
    period_days: int
    required_flights: Optional[int] = None
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


@router.get("/rules", response_model=list[RuleOut], responses=responses(401))
def list_rules(db: DBSession, user: CurrentUser):
    return db.query(CurrencyRule).order_by(CurrencyRule.name).all()


@router.post("/rules", response_model=RuleOut, responses=responses(401))
def create_rule(data: RuleCreate, db: DBSession, user: SupervisorUser):
    rule = CurrencyRule(**data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/rules/{rule_id}", response_model=RuleOut, responses=responses(401, 404))
def update_rule(rule_id: int, data: RuleUpdate, db: DBSession, user: SupervisorUser):
    rule = db.query(CurrencyRule).filter(CurrencyRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", responses=responses(401, 404))
def delete_rule(rule_id: int, db: DBSession, user: SupervisorUser):
    rule = db.query(CurrencyRule).filter(CurrencyRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"ok": True}


def _evaluate_currency(rules: list[CurrencyRule], flights: list[Flight]):
    """Evaluate currency for one pilot from an already-loaded flight list.

    Flights must have the Flight.vehicle relationship loaded so model-specific
    rules can be filtered in memory; the caller loads them once in bulk instead
    of running a query per pilot per rule.
    """
    rule_results = []
    today = date.today()
    for rule in rules:
        cutoff = today - timedelta(days=rule.period_days)
        model = rule.vehicle_model.lower() if rule.vehicle_model else None

        # In-period flights, matching the prior SQL filter: date >= cutoff, and
        # for model-specific rules an inner join on a matching vehicle model
        # (flights with no vehicle or a different model are excluded).
        flights_in_period = [
            f for f in flights
            if f.date and f.date >= cutoff
            and (model is None or (f.vehicle is not None and (f.vehicle.model or "").lower() == model))
        ]
        actual_flights = len(flights_in_period)
        actual_hours = sum((f.duration_seconds or 0) for f in flights_in_period) / 3600.0

        hours_met = actual_hours >= rule.required_hours
        flights_met = rule.required_flights is None or actual_flights >= rule.required_flights
        is_current = hours_met and flights_met

        # Currency expiry: walk newest -> oldest accumulating hours/flights.
        # The boundary flight is the one that first gets us to ALL minimums.
        # Currency lapses when THAT flight ages out of the period (its date
        # + period_days). The previous logic used the oldest flight in the
        # window, which is wrong when older flights are surplus.
        expires_date = None
        if is_current and flights_in_period:
            sorted_desc = sorted(
                flights_in_period,
                key=lambda f: f.date or date.min,
                reverse=True,
            )
            cum_hours = 0.0
            cum_flights = 0
            for f in sorted_desc:
                cum_hours += (f.duration_seconds or 0) / 3600.0
                cum_flights += 1
                hours_ok = cum_hours >= rule.required_hours
                flights_ok = rule.required_flights is None or cum_flights >= rule.required_flights
                if hours_ok and flights_ok and f.date:
                    expires_date = str(f.date + timedelta(days=rule.period_days))
                    break

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


def _pilot_currency(pilot: Pilot, rules: list[CurrencyRule], db: Session):
    """Evaluate currency for a single pilot against all active rules."""
    flights = db.query(Flight).options(joinedload(Flight.vehicle)).filter(
        Flight.pilot_id == pilot.id
    ).all()
    return _evaluate_currency(rules, flights)


@router.get("/status", responses=responses(401))
def get_all_currency_status(db: DBSession, user: CurrentUser):
    """Get currency status for all active pilots."""
    rules = db.query(CurrencyRule).filter(CurrencyRule.is_active.is_(True)).all()
    pilots = db.query(Pilot).filter(Pilot.status == "active").order_by(Pilot.last_name).all()

    # Load every active pilot's flights in one query (with vehicle, for
    # model-specific rules) and group by pilot, instead of a query per pilot
    # per rule.
    flights_by_pilot: dict[int, list[Flight]] = {}
    pilot_ids = [p.id for p in pilots]
    if pilot_ids:
        all_flights = db.query(Flight).options(joinedload(Flight.vehicle)).filter(
            Flight.pilot_id.in_(pilot_ids)
        ).all()
        for f in all_flights:
            flights_by_pilot.setdefault(f.pilot_id, []).append(f)

    results = []
    for pilot in pilots:
        rule_results = _evaluate_currency(rules, flights_by_pilot.get(pilot.id, []))
        overall_current = all(r["is_current"] for r in rule_results) if rule_results else True
        results.append({
            "pilot_id": pilot.id,
            "pilot_name": pilot.full_name,
            "is_current": overall_current,
            "rules": rule_results,
        })

    return results


class ReminderRequest(BaseModel):
    pilot_ids: Optional[list[int]] = None  # If None, all lapsed pilots
    custom_message: Optional[str] = None   # Optional intro text from supervisor


@router.post("/send-reminders", responses=responses(401, 503))
def send_currency_reminders(
    data: ReminderRequest,
    db: DBSession,
    admin: SupervisorUser,
):
    """Email currency reminders to lapsed pilots. If pilot_ids is provided,
    only those are notified; otherwise every active pilot lapsed on any rule
    is notified. Uses the configured SMTP server.

    Returns counts of emails sent vs. skipped (no email on file / SMTP off /
    already current)."""
    from app.constants import APP_TITLE
    from app.models.setting import Setting
    from app.services.email_digest import send_email
    from app.services.audit import log_action

    # SMTP must be configured + enabled
    smtp_enabled_row = db.query(Setting).filter(Setting.key == "smtp_enabled").first()
    if not smtp_enabled_row or smtp_enabled_row.value != "true":
        raise HTTPException(503, "SMTP is not enabled. Configure it in Settings → Integrations.")

    rules = db.query(CurrencyRule).filter(CurrencyRule.is_active.is_(True)).all()
    if not rules:
        raise HTTPException(400, "No active currency rules — nothing to remind about.")

    if data.pilot_ids:
        pilots = db.query(Pilot).filter(Pilot.id.in_(data.pilot_ids), Pilot.status == "active").all()
    else:
        pilots = db.query(Pilot).filter(Pilot.status == "active").all()

    org_name_row = db.query(Setting).filter(Setting.key == "org_name").first()
    org_name = org_name_row.value if org_name_row else APP_TITLE

    sent = 0
    skipped_no_email = 0
    skipped_current = 0
    failed = 0
    recipients_logged: list[str] = []

    for pilot in pilots:
        rule_results = _pilot_currency(pilot, rules, db)
        lapsed_rules = [r for r in rule_results if not r["is_current"]]
        if not lapsed_rules:
            skipped_current += 1
            continue
        if not pilot.email:
            skipped_no_email += 1
            continue

        # Compose HTML body
        rule_rows_html = "".join(
            f'<tr><td style="padding:6px 12px;border-bottom:1px solid #eee;">{r["rule_name"]}</td>'
            f'<td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:right;color:#c62828;">'
            f'{r["actual_hours"]}/{r["required_hours"]}h in {r["period_days"]}d</td></tr>'
            for r in lapsed_rules
        )
        intro = (data.custom_message or "").strip()
        intro_html = f'<p style="margin:0 0 16px;color:#555;">{intro}</p>' if intro else ""
        html = f"""<html><body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px;margin:0;">
<div style="max-width:600px;margin:0 auto;background:white;border-radius:8px;overflow:hidden;">
  <div style="background:#1a1a2e;color:white;padding:20px;text-align:center;">
    <h1 style="margin:0;font-size:20px;">{org_name}</h1>
    <p style="margin:4px 0 0;opacity:0.8;font-size:13px;">Flight Currency Reminder</p>
  </div>
  <div style="padding:24px;">
    <p style="margin:0 0 16px;">Hi {pilot.first_name or pilot.full_name},</p>
    {intro_html}
    <p style="margin:0 0 16px;color:#333;">
      Your flight currency status is below the minimum on the following rule{'s' if len(lapsed_rules) != 1 else ''}.
      Please log additional qualifying flights to regain currency.
    </p>
    <table style="border-collapse:collapse;width:100%;margin:8px 0 24px;border:1px solid #eee;">
      <thead><tr style="background:#fafafa;"><th style="padding:8px 12px;text-align:left;">Rule</th><th style="padding:8px 12px;text-align:right;">Progress</th></tr></thead>
      <tbody>{rule_rows_html}</tbody>
    </table>
    <p style="font-size:12px;color:#999;text-align:center;margin-top:24px;">
      Sent by Drone Unit Manager. Reply to this email or contact your supervisor with questions.
    </p>
  </div>
</div>
</body></html>"""

        ok = send_email(pilot.email, f"Flight currency reminder — {org_name}", html, db)
        if ok:
            sent += 1
            recipients_logged.append(f"{pilot.full_name} <{pilot.email}>")
        else:
            failed += 1

    log_action(db, admin.id, admin.display_name, "send_reminders", "currency",
               details=f"sent={sent}, skipped_no_email={skipped_no_email}, "
                       f"skipped_current={skipped_current}, failed={failed}; "
                       f"recipients={'; '.join(recipients_logged) if recipients_logged else 'none'}")
    db.commit()

    return {
        "sent": sent,
        "skipped_no_email": skipped_no_email,
        "skipped_current": skipped_current,
        "failed": failed,
    }


@router.get("/status/{pilot_id}", responses=responses(401, 404))
def get_pilot_currency_status(pilot_id: int, db: DBSession, user: CurrentUser):
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
