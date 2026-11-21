"""The fleet's vehicle models, merged by normalized name."""

from collections import Counter

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.vehicle import Vehicle


def normalize_model(name: str | None) -> str:
    """Collapse whitespace, trim and casefold; None gives an empty string."""
    return " ".join((name or "").split()).casefold()


def fleet_models(db: Session) -> list[dict]:
    """One entry per normalized model: the most common spelling (ties to the
    alphabetically first), the count of non-retired aircraft and of retired."""
    rows = (
        db.query(Vehicle.model, Vehicle.status, func.count(Vehicle.id))
        .group_by(Vehicle.model, Vehicle.status)
        .all()
    )
    spellings: dict[str, Counter] = {}
    counts: dict[str, list[int]] = {}
    for model, status, n in rows:
        key = normalize_model(model)
        if not key:
            continue
        spelling = " ".join(model.split())
        spellings.setdefault(key, Counter())[spelling] += n
        tally = counts.setdefault(key, [0, 0])
        tally[1 if status == "retired" else 0] += n
    result = []
    for key, spelled in spellings.items():
        name = min(spelled.items(), key=lambda item: (-item[1], item[0]))[0]
        result.append({"name": name, "aircraft": counts[key][0], "retired": counts[key][1]})
    return sorted(result, key=lambda m: m["name"].casefold())
