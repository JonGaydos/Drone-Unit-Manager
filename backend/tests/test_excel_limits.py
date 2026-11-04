"""Spreadsheet imports read one row at a time and refuse a file that is too big.

The Skydio and pilot importer refuses a file over its row limit outright and
imports nothing. The mapped importer keeps its own cap and reports the file as
cut short. Either way, a workbook that unpacks to more than the fixed limit is
refused before it is parsed.
"""

import io
import re
import zipfile
from datetime import date, datetime

import openpyxl
import pytest
from openpyxl.utils.exceptions import InvalidFileException

from app.models.certification import PilotCertification
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.services import excel_import, import_service
from app.services.excel_import import MAX_EXCEL_ROWS, import_excel, import_skydio_csv
from app.services.import_service import MAX_IMPORT_ROWS, MAX_UNPACKED_BYTES, ImportTooLarge, parse_file

EXCEL_URL = "/api/export/excel/import"
LOG_URL = "/api/export/flights/import/log"
PREVIEW_URL = "/api/import/preview"
COMMIT_URL = "/api/import/commit"
SHEET_XML = "xl/worksheets/sheet1.xml"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

SKYDIO_HEADERS = ["Flight ID", "Vehicle", "Pilot", "Takeoff", "Land", "Duration (seconds)",
                  "Takeoff Latitude", "Takeoff Longitude", "Takeoff Address", "Purpose", "Battery"]


def _workbook_bytes(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _skydio_row(i: int) -> list:
    return [f"abc-{i:04d}", "X10-1000", "Sam Field", datetime(2026, 3, 1 + i % 20, 12, 0), datetime(2026, 3, 1 + i % 20, 12, 30),
            1800, 28.5, -81.4, "1 Main St", "Training", f"BAT-{i}"]


def _pilot_info_rows() -> list[list]:
    """Six rows of banner and headers, then pilots, then the sheet's key."""
    filler = [["Roster"]] + [[None] for _ in range(5)]
    jane = ["Jane Doe", "Active", datetime(2026, 1, 5), "Pending", None, None, None, None,
            "Complete", None, None, None, None, "N/A", None, None, None, None,
            datetime(2025, 2, 1), datetime(2099, 2, 1)]
    ward = ["Lee Ward", "Inactive"]
    return filler + [jane, [None], ward, ["STATUS KEY: legend"]]


def _real_shaped_workbook(flights: int = 3) -> bytes:
    wb = openpyxl.Workbook()
    skydio = wb.active
    skydio.title = "Skydio"
    skydio.append(SKYDIO_HEADERS)
    for i in range(flights):
        skydio.append(_skydio_row(i))
    pilots = wb.create_sheet("Pilot Info")
    for row in _pilot_info_rows():
        pilots.append(row)
    wb.create_sheet("Notes").append(["ignored"])
    return _workbook_bytes(wb)


def _rows_only_workbook(rows: int, sheet: str = "Skydio") -> bytes:
    """A large sheet, written quickly."""
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet(sheet)
    ws.append(["Flight ID", "Vehicle", "Pilot"])
    for i in range(rows):
        ws.append([f"F{i}", "X10-1", "Sam Field"])
    return _workbook_bytes(wb)


def _with_sheet_xml(content: bytes, rewrite) -> bytes:
    """Copy a workbook, passing the first sheet's XML through rewrite."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            dst.writestr(item, rewrite(data) if item.filename == SHEET_XML else data)
    return out.getvalue()


def _bomb() -> bytes:
    """A small workbook-shaped file that unpacks past the limit."""
    chunk = b"\0" * (1024 * 1024)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        with zf.open(SHEET_XML, "w", force_zip64=True) as entry:
            for _ in range(MAX_UNPACKED_BYTES // len(chunk) + 1):
                entry.write(chunk)
    return out.getvalue()


def _upload(client, headers, url, name, body):
    return client.post(url, headers=headers, files={"file": (name, body, XLSX_MIME)})


def _nothing_imported(db) -> bool:
    return not (db.query(Flight).count() or db.query(Vehicle).count() or db.query(Pilot).count())


# 1. The row limit on the Skydio and pilot importer --------------------------

def test_excel_over_100000_rows_refused_nothing_imported(client, admin_headers, db):
    assert MAX_EXCEL_ROWS == 100_000

    resp = _upload(client, admin_headers, EXCEL_URL, "big.xlsx", _rows_only_workbook(MAX_EXCEL_ROWS + 1))

    assert resp.status_code == 413
    assert "100,000" in resp.json()["detail"]
    assert "nothing was imported" in resp.json()["detail"]
    assert _nothing_imported(db)


NOT_A_FILE = b"this is not a workbook or an archive"


@pytest.mark.parametrize("url,name", [
    (EXCEL_URL, "broken.xlsx"), (LOG_URL, "broken.xlsx"), (LOG_URL, "broken.zip")])
def test_a_file_that_is_not_a_zip_is_a_400(client, admin_headers, db, url, name):
    resp = _upload(client, admin_headers, url, name, NOT_A_FILE)

    assert resp.status_code == 400
    assert "not a valid Excel workbook or ZIP archive" in resp.json()["detail"]
    assert _nothing_imported(db)


@pytest.mark.parametrize("url", [EXCEL_URL, LOG_URL])
def test_a_workbook_openpyxl_refuses_is_a_400(client, admin_headers, db, monkeypatch, url):
    def refuse(_content):
        raise InvalidFileException("openpyxl does not support this file format")

    monkeypatch.setattr(excel_import, "open_workbook", refuse)

    resp = _upload(client, admin_headers, url, "odd.xlsx", NOT_A_FILE)

    assert resp.status_code == 400
    assert "not a valid Excel workbook or ZIP archive" in resp.json()["detail"]
    assert _nothing_imported(db)


def test_the_flight_log_route_refuses_it_the_same_way(client, admin_headers, db, monkeypatch):
    monkeypatch.setattr(excel_import, "MAX_EXCEL_ROWS", 2)

    resp = _upload(client, admin_headers, LOG_URL, "big.xlsx", _rows_only_workbook(3))

    assert resp.status_code == 413
    assert _nothing_imported(db)


def test_a_file_at_the_limit_imports(db, monkeypatch):
    monkeypatch.setattr(excel_import, "MAX_EXCEL_ROWS", 3)

    result = import_excel(db, _rows_only_workbook(3))

    assert result["flights_imported"] == 3


def test_the_limit_covers_the_sheets_together_and_writes_nothing(db, monkeypatch):
    """The pilot sheet is after the flight sheet, so it must be counted before
    the first flight is written."""
    monkeypatch.setattr(excel_import, "MAX_EXCEL_ROWS", 4)

    workbook = _real_shaped_workbook(flights=3)
    with pytest.raises(ImportTooLarge):
        import_excel(db, workbook)

    db.rollback()
    assert _nothing_imported(db)


def test_blank_formatted_rows_do_not_count(db, monkeypatch):
    """Excel can keep formatting on empty rows far below the data."""
    monkeypatch.setattr(excel_import, "MAX_EXCEL_ROWS", 2)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Skydio"
    ws.append(["Flight ID", "Vehicle", "Pilot"])
    ws.append(["F1", "X10-1", "Sam Field"])
    ws.append(["F2", "X10-1", "Sam Field"])
    for row in range(4, 40):
        ws.cell(row, 1).number_format = "0.00"
    assert ws.max_row == 39

    assert import_excel(db, _workbook_bytes(wb))["flights_imported"] == 2


def test_a_skydio_csv_over_the_limit_is_refused(client, admin_headers, db, monkeypatch):
    monkeypatch.setattr(excel_import, "MAX_EXCEL_ROWS", 2)
    csv_text = "Flight ID,Vehicle,Pilot,Takeoff\n" + "".join(
        f"F{i},X10-1,sam@example.com,2026-03-01 12:00:00\n" for i in range(3))

    resp = client.post(EXCEL_URL, headers=admin_headers, files={"file": ("big.csv", csv_text, "text/csv")})

    assert resp.status_code == 413
    assert _nothing_imported(db)


def test_a_skydio_csv_at_the_limit_imports(db, monkeypatch):
    monkeypatch.setattr(excel_import, "MAX_EXCEL_ROWS", 2)
    csv_text = "Flight ID,Vehicle,Pilot,Takeoff\n" + "".join(
        f"F{i},X10-1,sam@example.com,2026-03-01 12:0{i}:00\n" for i in range(2))

    assert import_skydio_csv(db, csv_text.encode())["flights_imported"] == 2


# 2. The unpacked size limit --------------------------------------------------

def _forbid_parsing(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the workbook was parsed")

    monkeypatch.setattr(openpyxl, "load_workbook", refuse)


@pytest.mark.parametrize("url", [EXCEL_URL, LOG_URL, PREVIEW_URL, COMMIT_URL])
def test_excel_unpacked_size_refused(client, admin_headers, db, monkeypatch, url):
    bomb = _bomb()
    assert len(bomb) < 2 * 1024 * 1024
    _forbid_parsing(monkeypatch)

    resp = _upload(client, admin_headers, url, "bomb.xlsx", bomb)

    assert resp.status_code == 413
    assert "unpacks" in resp.json()["detail"]
    assert _nothing_imported(db)


def test_the_unpacked_limit_is_well_above_a_full_size_workbook():
    """A sheet at the row limit, with wide rows of long values, still fits."""
    wide_row_bytes = 40 * 100
    assert MAX_EXCEL_ROWS * wide_row_bytes < MAX_UNPACKED_BYTES


def test_a_file_that_is_not_a_zip_is_left_for_the_parser_to_report(client, admin_headers):
    resp = _upload(client, admin_headers, PREVIEW_URL, "old.xls", b"\xd0\xcf\x11\xe0 not a zip")

    assert resp.status_code == 400
    assert "Could not parse file" in resp.json()["detail"]


# 3. Real-shaped sheets keep importing ----------------------------------------

def test_real_shaped_skydio_and_pilot_sheets_still_import(client, admin_headers, db):
    resp = _upload(client, admin_headers, EXCEL_URL, "skydio.xlsx", _real_shaped_workbook())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["flights_imported"] == 3
    assert body["errors"] == []
    assert body["vehicles_created"] == 1
    assert body["pilots_created"] == 3  # Sam from the flights, Jane and Lee from the roster
    assert body["certifications_created"] == len(excel_import._CERT_DEFS)
    assert body["cert_assignments"] == 2 * len(excel_import._CERT_DEFS)

    flight = db.query(Flight).filter(Flight.external_id == "ABC0000").one()
    assert flight.takeoff_time == datetime(2026, 3, 1, 12, 0)
    assert flight.landing_time == datetime(2026, 3, 1, 12, 30)
    assert flight.duration_seconds == 1800
    assert flight.takeoff_lat == pytest.approx(28.5)
    assert flight.purpose == "Training"
    assert flight.battery_serial == "BAT-0"
    assert flight.data_source == "excel_import"

    jane = db.query(Pilot).filter(Pilot.first_name == "Jane").one()
    lee = db.query(Pilot).filter(Pilot.first_name == "Lee").one()
    assert jane.status == "active"
    assert lee.status == "inactive"

    def certs(pilot):
        return {pc.certification_type.name: pc for pc in
                db.query(PilotCertification).filter(PilotCertification.pilot_id == pilot.id)}

    janes = certs(jane)
    assert janes["Skydio X2E Academy"].status == "complete"
    assert janes["Skydio X2E Academy"].issue_date == date(2026, 1, 5)
    assert janes["Skydio X2E Checkoff"].status == "pending"
    assert janes["NIST Level 1"].status == "complete"
    assert janes["DART Training"].status == "not_eligible"
    assert janes["FAA Part 107"].status == "active"
    assert janes["FAA Part 107"].issue_date == date(2025, 2, 1)
    assert janes["FAA Part 107"].expiration_date == date(2099, 2, 1)
    # A row that stops at its second column reads as blank to the right.
    assert certs(lee)["NIST Level 1"].status == "pending"
    assert certs(lee)["FAA Part 107"].status == "pending"


def test_row_numbers_in_errors_stay_true_across_blank_rows(db, monkeypatch):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Skydio"
    ws.append(["Flight ID", "Vehicle", "Pilot"])
    ws["A5"], ws["B5"], ws["C5"] = "F5", "X10-1", "Sam Field"

    def fail(*args, **kwargs):
        raise ValueError("no")

    monkeypatch.setattr(excel_import, "_process_skydio_row", fail)

    assert import_excel(db, _workbook_bytes(wb))["errors"][-1].startswith("Skydio row 5:")


def _claim_a_one_cell_sheet(content: bytes) -> bytes:
    """Some tools write a dimension tag that covers one cell, whatever the sheet holds."""
    def rewrite(xml: bytes) -> bytes:
        rewritten, count = re.subn(rb'<dimension ref="[^"]*"\s*/>', b'<dimension ref="A1"/>', xml)
        assert count == 1
        return rewritten

    return _with_sheet_xml(content, rewrite)


def test_a_wrong_dimension_tag_does_not_hide_cells(db):
    content = _claim_a_one_cell_sheet(_real_shaped_workbook())

    assert import_excel(db, content)["flights_imported"] == 3


def test_a_wrong_dimension_tag_does_not_hide_cells_in_the_mapped_import():
    content = _claim_a_one_cell_sheet(_real_shaped_workbook())

    headers, rows, _ = parse_file(content, "skydio.xlsx")

    assert headers == SKYDIO_HEADERS
    assert len(rows) == 3


# 4. The mapped importer ------------------------------------------------------

def _generic_workbook(rows: int) -> bytes:
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("Log")
    ws.append(["Date", "Title"])
    for i in range(rows):
        ws.append([datetime(2026, 1, 1), f"Row {i}"])
    return _workbook_bytes(wb)


def test_generic_import_stops_at_5000_while_reading(monkeypatch):
    converted = 0
    real = import_service._xlsx_row_to_dict

    def counting(row, headers):
        nonlocal converted
        converted += 1
        return real(row, headers)

    monkeypatch.setattr(import_service, "_xlsx_row_to_dict", counting)

    headers, rows, truncated = parse_file(_generic_workbook(MAX_IMPORT_ROWS + 500), "log.xlsx")

    assert MAX_IMPORT_ROWS == 5000
    assert headers == ["Date", "Title"]
    assert len(rows) == 5000
    assert truncated is True
    assert converted == MAX_IMPORT_ROWS + 1


def test_generic_import_at_5000_is_not_marked_cut_short():
    _, rows, truncated = parse_file(_generic_workbook(MAX_IMPORT_ROWS), "log.xlsx")

    assert len(rows) == 5000
    assert truncated is False


def test_generic_parse_matches_the_workbook_cell_for_cell():
    """Every header stays a key on every row, however short the row, and blank
    rows are skipped. Dates come out as text."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Date", None, "Title", "Notes"])
    ws.append([datetime(2026, 1, 2, 3, 4, 5), "ignored", "One", "n"])
    ws.append([None, None, None, None])
    ws.append([date(2026, 1, 3), None, "Two"])
    ws["A6"] = "2026-01-04"

    headers, rows, truncated = parse_file(_workbook_bytes(wb), "log.xlsx")

    assert headers == ["Date", "", "Title", "Notes"]
    assert rows == [
        {"Date": "2026-01-02 03:04:05", "Title": "One", "Notes": "n"},
        {"Date": "2026-01-03 00:00:00", "Title": "Two", "Notes": ""},
        {"Date": "2026-01-04", "Title": "", "Notes": ""},
    ]
    assert truncated is False


def test_an_empty_sheet_has_no_header_row(client, admin_headers):
    resp = _upload(client, admin_headers, PREVIEW_URL, "empty.xlsx", _workbook_bytes(openpyxl.Workbook()))

    assert resp.status_code == 400
    assert resp.json()["detail"] == "File has no header row"


def _zip_of(**entries) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


NOT_WORKBOOKS = {
    "plain_zip": lambda: _zip_of(**{"notes.txt": "hello"}),
    "empty_manifest": lambda: _zip_of(**{"[Content_Types].xml": "<Types/>"}),
    "broken_manifest": lambda: _zip_of(**{"[Content_Types].xml": "not xml"}),
    "broken_sheet": lambda: _with_sheet_xml(_rows_only_workbook(1), lambda _xml: "not xml"),
    "broken_cell": lambda: _with_sheet_xml(_rows_only_workbook(1), lambda xml: re.sub(
        rb'<c r="A2"[^>]*>.*?</c>', b'<c r="A2" t="n"><v>abc</v></c>', xml, count=1)),
}


@pytest.mark.parametrize("build", NOT_WORKBOOKS.values(), ids=NOT_WORKBOOKS.keys())
@pytest.mark.parametrize("url", [EXCEL_URL, LOG_URL])
def test_a_zip_that_is_not_a_workbook_is_a_400(client, admin_headers, db, url, build):
    resp = _upload(client, admin_headers, url, "archive.xlsx", build())

    assert resp.status_code == 400
    assert "not a valid Excel workbook or ZIP archive" in resp.json()["detail"]
    assert _nothing_imported(db)
