"""Run a real BRINC CSV through the importer against a throwaway database.

Nothing in the BRINC path changed this week, so this is a "does it still work
end to end" check rather than a regression diff: the module is byte-identical
to what production runs. What it can still catch is a shared helper moving
under it.

Geocoding is off, so this makes no network calls and touches nothing real.

    python backend/tests/tools/dry_run_brinc.py <file.csv>
"""
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

TMP = Path(tempfile.mkdtemp(prefix="brinc-dry-"))
import os
os.environ["DATA_DIR"] = str(TMP)
os.environ["DATABASE_URL"] = f"sqlite:///{TMP}/main.db"
os.environ["TELEMETRY_DATABASE_URL"] = f"sqlite:///{TMP}/telemetry.db"

from app.database import Base, engine, SessionLocal  # noqa: E402
from app.models.flight import Flight  # noqa: E402
from app.models.pilot import Pilot  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.services.brinc_import import import_brinc_csv, is_brinc_csv  # noqa: E402


def main(path):
    raw = Path(path).read_bytes()
    header = raw.decode("utf-8", errors="replace").splitlines()[0].split(",")
    print(f"file       {Path(path).name}  ({len(raw):,} bytes)")
    print(f"recognised as BRINC: {is_brinc_csv(header)}")

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # BRINC rows only import for airframes already in the fleet, so seed the
    # ones this file mentions. Without them every row is skipped as unmatched,
    # which exercises the reporting but not the import.
    drones = sorted({r.split(",")[5] for r in
                     raw.decode("utf-8", errors="replace").splitlines()[1:] if r.count(",") > 5})
    for i, serial in enumerate(drones, start=1):
        db.add(Vehicle(serial_number=f"LOCAL-{i}", provider_serial=serial,
                       manufacturer="BRINC", model="Lemur", status="active"))
    db.commit()
    print(f"seeded fleet: {drones}")

    result = import_brinc_csv(db, raw, geocode=False)

    print()
    for key in sorted(result):
        value = result[key]
        if isinstance(value, list) and len(value) > 6:
            print(f"  {key:28} {len(value)} items, first: {value[0]}")
        else:
            print(f"  {key:28} {value}")

    print()
    print(f"  flights now in the db        {db.query(Flight).count()}")
    print(f"  pilots created               {db.query(Pilot).count()}")
    print(f"  vehicles                     {db.query(Vehicle).count()}")

    flights = db.query(Flight).order_by(Flight.date).all()
    if flights:
        first, last = flights[0], flights[-1]
        print(f"  date range                   {first.date} .. {last.date}")
        durations = [f.duration_seconds for f in flights if f.duration_seconds]
        print(f"  durations                    min {min(durations)}s, max {max(durations)}s")
        print(f"  with a case number           {sum(1 for f in flights if f.case_number)}")
        print(f"  with coordinates             {sum(1 for f in flights if f.takeoff_lat)}")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) > 1 else (print(__doc__) or 2))
