"""A backup with telemetry must not hold the telemetry table.

Exporting with telemetry loaded every row as an ORM object, converted the lot
into a list of dicts, then built the whole JSON document as one string before
handing it to the zip. Three copies of the table at once. On an instance with
eight million points that is several gigabytes, and a container with no memory
limit takes the host down with it rather than merely failing.

The timeout fix that let a long export finish is what made this reachable:
before it, the proxy cut the request off long before the allocation completed.
"""

import json
import tracemalloc
import zipfile

from app.models.telemetry import TelemetryPoint
from app.routers.backup import build_backup_archive

TELEMETRY_FILE = "telemetry.json"


def _seed(telemetry_db, count, flight_id=1):
    telemetry_db.add_all([
        TelemetryPoint(flight_id=flight_id, timestamp_ms=i * 1000,
                       lat=28.5 + i / 1e6, lon=-81.4, altitude_m=float(i % 120),
                       speed_mps=float(i % 20), battery_pct=100 - (i % 100),
                       satellites=12, source="test")
        for i in range(count)])
    telemetry_db.commit()


def _telemetry_from(spooled):
    spooled.seek(0)
    with zipfile.ZipFile(spooled) as zf:
        return json.loads(zf.read(TELEMETRY_FILE))


# 1. It still produces the right archive -------------------------------------

def test_every_row_reaches_the_archive(db, telemetry_db):
    _seed(telemetry_db, 250)

    spooled, _ = build_backup_archive(db, include_telemetry=True)

    rows = _telemetry_from(spooled)
    assert len(rows) == 250
    assert rows[0]["timestamp_ms"] == 0
    assert rows[-1]["timestamp_ms"] == 249_000


def test_the_rows_carry_their_columns(db, telemetry_db):
    _seed(telemetry_db, 3)

    row = _telemetry_from(build_backup_archive(db, include_telemetry=True)[0])[0]

    assert row["flight_id"] == 1
    assert row["lat"] == 28.5
    assert row["source"] == "test"
    assert "altitude_m" in row


def test_no_telemetry_file_when_it_was_not_asked_for(db, telemetry_db):
    """The nightly job exports without telemetry, which is why it has been
    fine while the manual export was not."""
    _seed(telemetry_db, 10)

    spooled, _ = build_backup_archive(db, include_telemetry=False)

    spooled.seek(0)
    with zipfile.ZipFile(spooled) as zf:
        assert TELEMETRY_FILE not in zf.namelist()


def test_an_empty_telemetry_table_writes_an_empty_array(db, telemetry_db):
    """Not a truncated file, and not a crash on the comma placement."""
    spooled, _ = build_backup_archive(db, include_telemetry=True)

    assert _telemetry_from(spooled) == []


def test_the_manifest_counts_the_rows(db, telemetry_db):
    _seed(telemetry_db, 42)

    spooled, _ = build_backup_archive(db, include_telemetry=True)

    spooled.seek(0)
    with zipfile.ZipFile(spooled) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["tables"]["telemetry_points"] == 42


def test_an_entry_larger_than_two_gibibytes_can_be_written(db, telemetry_db, monkeypatch):
    """Streaming means the size is unknown when the entry header is written, and
    zipfile refuses to go past 2 GiB unless told in advance. writestr never hit
    this because it had the finished bytes to measure.

    A real instance passes that mark: the export this was found on holds 2.47 GB
    of telemetry. Rather than write two gigabytes here, the limit is lowered so
    the same refusal happens over a few hundred kilobytes.
    """
    import zipfile
    monkeypatch.setattr(zipfile, "ZIP64_LIMIT", 4096)
    _seed(telemetry_db, 2_000)

    spooled, _ = build_backup_archive(db, include_telemetry=True)

    assert len(_telemetry_from(spooled)) == 2_000


# 2. And it does not hold the table ------------------------------------------

def test_memory_does_not_scale_with_the_number_of_rows(db, telemetry_db):
    """The point of the whole change.

    Ten times the rows must not cost ten times the memory. Measured on this
    code, holding the table gives 19.8 MB at ten thousand rows and 101.6 MB at
    fifty thousand; streaming gives 16.9 MB and 17.4 MB. Extrapolating the
    first curve to the eight million points on a real instance is about 16 GB,
    which is what takes a host down rather than just failing the export.

    Fifty thousand is the smallest size where the two are clearly apart. At the
    two thousand this test first used, the fixed costs of building the rest of
    the archive drown the difference out, and it passed against the very code
    it was meant to catch.
    """
    _seed(telemetry_db, 5_000)
    tracemalloc.start()
    build_backup_archive(db, include_telemetry=True)
    _, small = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    telemetry_db.query(TelemetryPoint).delete()
    telemetry_db.commit()
    _seed(telemetry_db, 50_000)
    tracemalloc.start()
    build_backup_archive(db, include_telemetry=True)
    _, large = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    growth = large / max(small, 1)
    assert growth < 2, (
        f"ten times the rows cost {growth:.1f}x the memory "
        f"({small/1024/1024:.1f} MB -> {large/1024/1024:.1f} MB); "
        "the table is being held rather than streamed")
