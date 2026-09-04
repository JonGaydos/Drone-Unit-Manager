"""Which flights are the unit's own activity.

``pilot.status`` answers "is this person on the roster". It does not answer "is
this the unit's activity", and the two come apart in both directions:

* A pilot who leaves goes inactive, but the flights they flew were the unit's
  and must keep counting, or every historical total quietly shrinks when
  somebody resigns.
* A vendor rep or guest operator has a live account and flies real sorties on
  the unit's aircraft, but those were never the unit's own activity. This is
  not a rounding error: in one observed import a single vendor rep held 27% of
  the period's flights.

So counting is its own flag, set per pilot and overridable per flight, and it is
evaluated at query time rather than stamped onto rows at import. Flipping a
pilot's flag has to correct the flights they already flew, not just future ones.
"""

from sqlalchemy import or_, select

from app.models.flight import Flight
from app.models.pilot import Pilot


def counted_flight_clause():
    """SQL condition selecting flights that count towards the unit's numbers.

    A flight counts when it is not itself excluded and its pilot is not
    excluded. An unassigned flight counts: nobody has said it should not, and
    dropping unattributed airframe time would hide real activity.

    Written as a NOT IN against the excluded pilots rather than a join so it can
    be dropped into an existing aggregate without disturbing its joins, several
    of which are outer joins whose whole purpose is to keep zero rows visible.
    """
    excluded_pilots = select(Pilot.id).where(Pilot.counts_toward_totals.is_(False))
    return Flight.counts_toward_totals.is_(True) & or_(
        Flight.pilot_id.is_(None),
        Flight.pilot_id.notin_(excluded_pilots),
    )


def counted_only(query, include_all: bool = False):
    """Apply the rule to a query, unless the caller asked for everything.

    ``include_all`` is the escape hatch behind the "Include non-unit flights"
    report option.
    """
    return query if include_all else query.filter(counted_flight_clause())


def flight_counts(flight, pilot=None) -> bool:
    """The same rule in Python, for code holding objects rather than a query."""
    if not flight.counts_toward_totals:
        return False
    pilot = pilot if pilot is not None else getattr(flight, "pilot", None)
    return pilot is None or pilot.counts_toward_totals
