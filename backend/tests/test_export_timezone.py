"""CSV export renders UTC columns as-is and Local column in the configured zone."""
import csv
import io
from datetime import datetime

from app.models.flight import Flight
from app.models.setting import Setting


def test_export_utc_and_local_columns(client, db, admin_headers):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.add(Flight(external_id="F1", date=datetime(2026, 6, 24).date(),
                  takeoff_time=datetime(2026, 6, 24, 16, 26, 0),
                  landing_time=datetime(2026, 6, 24, 16, 31, 0)))
    db.commit()
    resp = client.get("/api/export/flights/csv", headers=admin_headers)
    assert resp.status_code == 200
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    row = next(r for r in rows if r["Flight ID"] == "F1")
    assert row["Takeoff"] == "2026-06-24 16:26"          # UTC, as stored
    assert row["Local Takeoff Time"] == "2026-06-24 11:26"  # CDT (UTC-5)
    assert row["Land"] == "2026-06-24 16:31"
